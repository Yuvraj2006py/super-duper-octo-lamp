import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import crud
from app.db.models import Job
from app.services.audit import audit_event
from app.services.url_parser import detect_platform


PROMPT_KEYWORDS = {
    "question",
    "questiontext",
    "question_text",
    "label",
    "prompt",
    "name",
    "title",
}


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return normalized[:255] if normalized else "field"


def _extract_strings_from_json(data: Any, out: list[str], parent_key: str = "") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            key_norm = _normalize_key(str(key))
            if isinstance(value, str):
                text = _normalize_space(value)
                if not text:
                    continue
                if key_norm in PROMPT_KEYWORDS or "question" in key_norm or "label" in key_norm:
                    out.append(text)
                elif parent_key and ("question" in parent_key or "label" in parent_key):
                    out.append(text)
            else:
                _extract_strings_from_json(value, out, key_norm)
        return

    if isinstance(data, list):
        for item in data:
            _extract_strings_from_json(item, out, parent_key)


def _extract_script_prompts(raw_text: str) -> list[str]:
    if not raw_text:
        return []
    try:
        parsed = json.loads(raw_text)
    except Exception:
        return []

    prompts: list[str] = []
    _extract_strings_from_json(parsed, prompts)

    deduped: list[str] = []
    seen = set()
    for prompt in prompts:
        key = prompt.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(prompt)
        if len(deduped) >= 30:
            break
    return deduped


def normalize_form_capture(
    *,
    platform: str,
    fields: list[dict[str, Any]],
    scripts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for idx, field in enumerate(fields):
        key_source = str(field.get("name") or field.get("id") or field.get("ariaLabel") or f"field_{idx + 1}")
        field_key = _normalize_key(key_source)
        label = _normalize_space(
            str(
                field.get("label")
                or field.get("ariaLabel")
                or field.get("placeholder")
                or field.get("name")
                or field.get("id")
                or f"Field {idx + 1}"
            )
        )
        field_type = _normalize_key(str(field.get("type") or field.get("tag") or "unknown")) or "unknown"

        normalized.append(
            {
                "field_key": f"form_{field_key}_{idx + 1}",
                "label": label[:512] if label else None,
                "type": field_type[:50],
                "required": bool(field.get("required", False)),
                "platform": platform,
                "metadata": {
                    "tag": field.get("tag"),
                    "name": field.get("name"),
                    "id": field.get("id"),
                    "placeholder": field.get("placeholder"),
                    "aria_label": field.get("ariaLabel"),
                    "options": field.get("options") or [],
                },
            }
        )

    for idx, script in enumerate(scripts):
        raw_text = str(script.get("text") or "").strip()
        if not raw_text:
            continue
        prompts = _extract_script_prompts(raw_text)
        if not prompts:
            continue

        source = str(script.get("source") or f"script_{idx + 1}")
        normalized.append(
            {
                "field_key": f"script_{_normalize_key(source)}_{idx + 1}",
                "label": f"Structured script ({source})",
                "type": "script_json",
                "required": False,
                "platform": platform,
                "metadata": {
                    "source": source,
                    "prompt_candidates": prompts,
                },
            }
        )

    deduped: list[dict[str, Any]] = []
    seen = set()
    for row in normalized:
        key = str(row.get("field_key", "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def fetch_form_capture(
    *,
    url: str,
    storage_state_path: Path,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is required for form fetching. Install playwright and browsers.") from exc

    if not storage_state_path.exists():
        raise FileNotFoundError(f"Storage state file not found: {storage_state_path}")

    def _try_dismiss_cookie_banners(page) -> None:
        import re as _re

        patterns = [
            _re.compile(r"accept all", _re.IGNORECASE),
            _re.compile(r"accept", _re.IGNORECASE),
            _re.compile(r"i agree", _re.IGNORECASE),
            _re.compile(r"agree", _re.IGNORECASE),
        ]
        # Workday (and some hosted career sites) expose a stable automation id.
        for sel in [
            "button[data-automation-id='legalNoticeAcceptButton']",
            "#onetrust-accept-btn-handler",
        ]:
            try:
                btn = page.locator(sel)
                if btn.count() > 0:
                    btn.first.click(timeout=1500, force=True)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        for pat in patterns:
            try:
                btn = page.get_by_role("button", name=pat)
                if btn.count() > 0:
                    btn.first.click(timeout=1500, force=True)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    def _try_click_apply(page) -> tuple[bool, dict[str, Any], Any]:
        """Return (clicked, detail, resulting_page)."""
        import re as _re

        apply_text = _re.compile(r"\bapply\b", _re.IGNORECASE)
        anti_patterns = [
            _re.compile(r"\bapply filters\b", _re.IGNORECASE),
            _re.compile(r"\bfilter\b", _re.IGNORECASE),
            _re.compile(r"\btime left to apply\b", _re.IGNORECASE),
            _re.compile(r"\bend date\b", _re.IGNORECASE),
            _re.compile(r"\bhours left to apply\b", _re.IGNORECASE),
        ]

        candidates: list[tuple[str, Any]] = []

        # Prefer explicit apply CTAs / apply routes.
        for sel in [
            "a[data-automation-id='adventureButton']",
            "a[href*='/apply']",
            "a[href*='apply']",
        ]:
            candidates.append((f"css:{sel}", page.locator(sel)))

        # Generic buttons/links/role=button containing Apply.
        candidates.append(("role:button:apply", page.get_by_role("button", name=apply_text)))
        candidates.append(("role:link:apply", page.get_by_role("link", name=apply_text)))
        candidates.append(("css:button:has-text(apply)", page.locator("button", has_text=apply_text)))
        candidates.append(("css:a:has-text(apply)", page.locator("a", has_text=apply_text)))
        candidates.append(("css:[role=button]:has-text(apply)", page.locator("[role='button']", has_text=apply_text)))

        # Fallback: known Workday-style automation ids, restricted to clickable tags.
        for sel in [
            "a[data-automation-id='apply']",
            "a[data-automation-id='applyNow']",
            "a[data-automation-id*='apply']",
            "button[data-automation-id='apply']",
            "button[data-automation-id='applyNow']",
            "button[data-automation-id*='apply']",
            "[role='button'][data-automation-id*='apply']",
        ]:
            candidates.append((f"css:{sel}", page.locator(sel)))

        # As a last resort, locate any text node match and click nearest clickable ancestor via JS.
        # We only do this if it looks like a single prominent CTA.
        try:
            text_count = page.locator("text=/\\bapply\\b/i").count()
        except Exception:
            text_count = 0

        for desc, locator in candidates:
            try:
                count = locator.count()
            except Exception:
                continue
            if count < 1:
                continue

            for idx in range(min(count, 5)):
                node = locator.nth(idx)
                try:
                    if not node.is_visible():
                        continue
                    node.scroll_into_view_if_needed(timeout=1500)
                    text = ""
                    try:
                        text = (node.inner_text(timeout=500) or "").strip()
                    except Exception:
                        text = ""
                    if any(p.search(text) for p in anti_patterns):
                        continue

                    href = ""
                    try:
                        href = (node.get_attribute("href") or "").strip()
                    except Exception:
                        href = ""
                    # Prefer direct navigation when an explicit apply URL is present.
                    if href and "/apply" in href and "/apply" not in (page.url or ""):
                        try:
                            page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
                            if wait_ms > 0:
                                page.wait_for_timeout(wait_ms)
                            try:
                                page.wait_for_load_state("networkidle", timeout=timeout_ms)
                            except Exception:
                                pass
                            return True, {"selector": desc, "idx": idx, "popup": False, "text": text, "text_count": text_count, "method": "goto", "href": href}, page
                        except Exception:
                            pass

                    # Popup/tab handling.
                    try:
                        with page.expect_popup(timeout=3000) as popup_info:
                            node.click(timeout=3000)
                        popup = popup_info.value
                        popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                        if wait_ms > 0:
                            popup.wait_for_timeout(wait_ms)
                        return True, {"selector": desc, "idx": idx, "popup": True, "text": text, "text_count": text_count}, popup
                    except Exception:
                        node.click(timeout=3000)
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                        except Exception:
                            pass
                        try:
                            page.wait_for_load_state("networkidle", timeout=timeout_ms)
                        except Exception:
                            pass
                        if wait_ms > 0:
                            page.wait_for_timeout(wait_ms)
                        return True, {"selector": desc, "idx": idx, "popup": False, "text": text, "text_count": text_count}, page
                except Exception:
                    continue

        if text_count == 1:
            try:
                page.evaluate(
                    """
                    () => {
                      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                      let node;
                      while ((node = walker.nextNode())) {
                        const t = (node.textContent || '').trim();
                        if (/\\bapply\\b/i.test(t)) {
                          const el = node.parentElement;
                          const target = el ? el.closest('a,button,[role="button"]') : null;
                          if (target) { target.click(); return true; }
                        }
                      }
                      return false;
                    }
                    """
                )
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
                if wait_ms > 0:
                    page.wait_for_timeout(wait_ms)
                return True, {"selector": "js:text-walker", "popup": False, "text_count": text_count}, page
            except Exception:
                pass

        return False, {"attempted": True, "text_count": text_count}, page

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        _try_dismiss_cookie_banners(page)

        # Trigger lazy content, then attempt Apply.
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(300)
        except Exception:
            pass

        apply_clicked, apply_detail, page = _try_click_apply(page)

        # If we didn't land on any interactive form fields, try opening the sign-in modal/step.
        # This is common for Workday-hosted pages where /apply leads to an auth wall first.
        try:
            interactive_count = page.locator(
                "input, select, textarea, [role='textbox'], [role='combobox'], [role='checkbox'], [role='radio'], [contenteditable='true']"
            ).count()
        except Exception:
            interactive_count = 0

        if interactive_count == 0:
            try:
                _try_dismiss_cookie_banners(page)
                # Workday utility sign-in button is stable on many hosted sites.
                signin = page.locator("button[data-automation-id='utilityButtonSignIn']")
                if signin.count() > 0:
                    signin.first.click(timeout=3000)
                else:
                    import re as _re
                    page.get_by_role("button", name=_re.compile(r"sign in|log in", _re.IGNORECASE)).first.click(timeout=3000)
                page.wait_for_timeout(max(wait_ms, 2000))
            except Exception:
                pass

        # Best-effort: many ATS pages (including Workday) only render the application form
        # after clicking an Apply CTA. This must not bypass bot protections.
        extracted = page.evaluate(
            """
            () => {
              const labelForId = new Map();
              document.querySelectorAll('label[for]').forEach((label) => {
                const id = label.getAttribute('for');
                if (id) {
                  labelForId.set(id, (label.textContent || '').trim());
                }
              });

              const fields = [];
              const nodes = document.querySelectorAll(
                'input, select, textarea, [role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"], [contenteditable="true"]'
              );
              nodes.forEach((el, idx) => {
                const tag = (el.tagName || '').toLowerCase();
                const explicitType = tag === 'input' ? ((el.getAttribute('type') || 'text').toLowerCase()) : tag;
                const role = el.getAttribute('role') || '';
                const type = role || explicitType;
                const id = el.getAttribute('id') || '';
                const name = el.getAttribute('name') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const ownLabel = el.closest('label') ? ((el.closest('label').textContent || '').trim()) : '';
                const mappedLabel = id && labelForId.has(id) ? labelForId.get(id) : '';
                const label = ownLabel || mappedLabel || ariaLabel || placeholder || name || id || `field_${idx + 1}`;

                const options = [];
                if (tag === 'select') {
                  el.querySelectorAll('option').forEach((opt) => {
                    const text = (opt.textContent || '').trim();
                    if (text) {
                      options.push(text);
                    }
                  });
                }

                fields.push({
                  tag,
                  type,
                  id,
                  name,
                  label,
                  placeholder,
                  ariaLabel,
                  required: !!el.required || (el.getAttribute('aria-required') === 'true'),
                  options,
                });
              });

              const scripts = [];
              document.querySelectorAll('script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__').forEach((el, idx) => {
                const text = (el.textContent || '').trim();
                if (!text) {
                  return;
                }
                scripts.push({
                  source: el.id || el.getAttribute('type') || `script_${idx + 1}`,
                  text: text.slice(0, 120000),
                });
              });

              return {
                final_url: window.location.href,
                title: document.title || '',
                fields,
                scripts,
              };
            }
            """
        )
        extracted["apply_clicked"] = apply_clicked
        extracted["apply_detail"] = apply_detail

        # Also extract from all frames (Workday frequently uses iframes for application steps).
        frame_fields: list[dict[str, Any]] = []
        frame_scripts: list[dict[str, Any]] = []
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                frame_data = frame.evaluate(
                    """
                    () => {
                      const labelForId = new Map();
                      document.querySelectorAll('label[for]').forEach((label) => {
                        const id = label.getAttribute('for');
                        if (id) { labelForId.set(id, (label.textContent || '').trim()); }
                      });
                      const fields = [];
                      const nodes = document.querySelectorAll('input, select, textarea, [role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"], [contenteditable="true"]');
                      nodes.forEach((el, idx) => {
                        const tag = (el.tagName || '').toLowerCase();
                        const explicitType = tag === 'input' ? ((el.getAttribute('type') || 'text').toLowerCase()) : tag;
                        const role = el.getAttribute('role') || '';
                        const type = role || explicitType;
                        const id = el.getAttribute('id') || '';
                        const name = el.getAttribute('name') || '';
                        const placeholder = el.getAttribute('placeholder') || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const ownLabel = el.closest('label') ? ((el.closest('label').textContent || '').trim()) : '';
                        const mappedLabel = id && labelForId.has(id) ? labelForId.get(id) : '';
                        const label = ownLabel || mappedLabel || ariaLabel || placeholder || name || id || `field_${idx + 1}`;
                        const options = [];
                        if (tag === 'select') {
                          el.querySelectorAll('option').forEach((opt) => {
                            const text = (opt.textContent || '').trim();
                            if (text) { options.push(text); }
                          });
                        }
                        fields.push({ tag, type, id, name, label, placeholder, ariaLabel, required: !!el.required || (el.getAttribute('aria-required') === 'true'), options });
                      });
                      const scripts = [];
                      document.querySelectorAll('script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__').forEach((el, idx) => {
                        const text = (el.textContent || '').trim();
                        if (!text) { return; }
                        scripts.push({ source: el.id || el.getAttribute('type') || `script_${idx + 1}`, text: text.slice(0, 120000) });
                      });
                      return { fields, scripts };
                    }
                    """
                )
                for field in frame_data.get("fields") or []:
                    field["frame_url"] = frame.url
                    frame_fields.append(field)
                for script in frame_data.get("scripts") or []:
                    script["frame_url"] = frame.url
                    frame_scripts.append(script)
            except Exception:
                continue

        if frame_fields:
            extracted["fields"] = [*(extracted.get("fields") or []), *frame_fields]
        if frame_scripts:
            extracted["scripts"] = [*(extracted.get("scripts") or []), *frame_scripts]

        context.close()
        browser.close()

    return extracted


def fetch_and_normalize_form_fields(
    *,
    url: str,
    platform: str | None = None,
    storage_state_path: Path | None = None,
    timeout_ms: int | None = None,
    wait_ms: int | None = None,
    headless: bool | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    inferred_platform = (platform or detect_platform(url)).strip().lower() or "generic"
    state_path = storage_state_path or settings.form_storage_state_path

    capture = fetch_form_capture(
        url=url,
        storage_state_path=state_path,
        timeout_ms=timeout_ms or settings.form_fetch_timeout_ms,
        wait_ms=wait_ms if wait_ms is not None else settings.form_fetch_wait_ms,
        headless=settings.form_browser_headless if headless is None else headless,
    )

    normalized_fields = normalize_form_capture(
        platform=inferred_platform,
        fields=capture.get("fields") or [],
        scripts=capture.get("scripts") or [],
    )

    return {
        "platform": inferred_platform,
        "final_url": capture.get("final_url") or url,
        "title": capture.get("title") or "",
        "fields": normalized_fields,
        "raw_field_count": len(capture.get("fields") or []),
        "script_count": len(capture.get("scripts") or []),
        "apply_clicked": bool(capture.get("apply_clicked", False)),
        "apply_detail": capture.get("apply_detail") or {},
    }


def fetch_and_store_job_form_fields(
    db: Session,
    *,
    job: Job,
    actor_id: str,
) -> dict[str, Any]:
    if not job.url:
        raise ValueError("Job has no URL; cannot fetch form fields")

    result = fetch_and_normalize_form_fields(url=job.url, platform=job.platform)
    inserted = crud.replace_application_form_fields(
        db,
        job_id=str(job.id),
        fields=result["fields"],
    )

    if result.get("platform") and result.get("platform") != job.platform:
        job.platform = result["platform"]

    audit_event(
        db,
        actor_type="agent",
        actor_id=actor_id,
        action="form_fetched",
        entity_type="job",
        entity_id=str(job.id),
        payload={
            "platform": result.get("platform"),
            "final_url": result.get("final_url"),
            "raw_field_count": result.get("raw_field_count"),
            "script_count": result.get("script_count"),
            "apply_clicked": result.get("apply_clicked"),
            "apply_detail": result.get("apply_detail"),
        },
    )
    audit_event(
        db,
        actor_type="agent",
        actor_id=actor_id,
        action="fields_cataloged",
        entity_type="job",
        entity_id=str(job.id),
        payload={
            "platform": result.get("platform"),
            "catalog_count": len(inserted),
        },
    )

    db.flush()
    return {
        "platform": result.get("platform"),
        "final_url": result.get("final_url"),
        "catalog_count": len(inserted),
        "raw_field_count": result.get("raw_field_count"),
        "script_count": result.get("script_count"),
        "apply_clicked": result.get("apply_clicked"),
    }
