import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.url_parser import detect_platform


CAPTCHA_PATTERNS = [
    re.compile(r"\bcaptcha\b", re.IGNORECASE),
    re.compile(r"\bi am not a robot\b", re.IGNORECASE),
    re.compile(r"\bverify you are human\b", re.IGNORECASE),
]

SUBMIT_BUTTON_PATTERNS = [
    re.compile(r"submit application", re.IGNORECASE),
    re.compile(r"submit", re.IGNORECASE),
    re.compile(r"apply", re.IGNORECASE),
]

WORKDAY_FINAL_SUBMIT_PATTERNS = [
    re.compile(r"submit application", re.IGNORECASE),
    re.compile(r"submit", re.IGNORECASE),
]

NEXT_BUTTON_PATTERNS = [
    re.compile(r"save and continue", re.IGNORECASE),
    re.compile(r"continue", re.IGNORECASE),
    re.compile(r"next", re.IGNORECASE),
    re.compile(r"review", re.IGNORECASE),
]

SIGN_IN_BUTTON_PATTERNS = [
    re.compile(r"sign in", re.IGNORECASE),
    re.compile(r"log in", re.IGNORECASE),
]

def _pick_best_pdf(*, directory: Path, prefer_keywords: list[str]) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None
    candidates: list[Path] = []
    for p in directory.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() != ".pdf":
            continue
        candidates.append(p)
    if not candidates:
        return None
    lowered = {p: p.name.lower() for p in candidates}
    for kw in prefer_keywords:
        hits = [p for p in candidates if kw in lowered[p]]
        if hits:
            return max(hits, key=lambda x: x.stat().st_size)
    return max(candidates, key=lambda x: x.stat().st_size)


def _resolve_resume_pdf_path(settings) -> Path | None:
    if settings.resume_pdf_path.exists():
        return settings.resume_pdf_path
    return _pick_best_pdf(directory=Path("resume"), prefer_keywords=["resume", "cv"])


def _resolve_transcript_pdf_path(settings) -> Path | None:
    if settings.transcript_pdf_path.exists():
        return settings.transcript_pdf_path
    return _pick_best_pdf(directory=Path("resume"), prefer_keywords=["transcript"])


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _general_meta(profile: dict[str, Any]) -> dict[str, Any]:
    return profile.get("general_meta", {}) or {}


def _work_auth_answer(question: str, profile: dict[str, Any]) -> str | None:
    lowered = _norm(question)
    gm = _general_meta(profile)
    auth = gm.get("work_authorization", {}) or {}
    if "authorized" in lowered and "work" in lowered:
        if "canada" in lowered:
            if bool(auth.get("canada_authorized", False)):
                if bool(auth.get("requires_sponsorship_canada", False)):
                    return "Yes, I am authorized to work in Canada and may require sponsorship."
                return "Yes, I am authorized to work in Canada and do not require sponsorship."
            return "No, I am not currently authorized to work in Canada."
        if "us" in lowered or "united states" in lowered:
            if bool(auth.get("us_authorized", False)):
                if bool(auth.get("requires_sponsorship_us", False)):
                    return "Yes, I am authorized to work in the United States and may require sponsorship."
                return "Yes, I am authorized to work in the United States and do not require sponsorship."
            return "No, I am not currently authorized to work in the United States."

    if "sponsor" in lowered or "sponsorship" in lowered or "visa" in lowered:
        if "canada" in lowered:
            return "Yes." if bool(auth.get("requires_sponsorship_canada", False)) else "No."
        if "us" in lowered or "united states" in lowered:
            return "Yes." if bool(auth.get("requires_sponsorship_us", False)) else "No."
    return None


def _meta_answer_for_prompt(prompt: str, profile: dict[str, Any]) -> tuple[str | None, str | None]:
    lowered = _norm(prompt)
    gm = _general_meta(profile)

    # Common auth fields (Workday sign-in walls).
    if "email" in lowered and "password" not in lowered:
        personal = profile.get("personal_info", {}) or {}
        email = str(personal.get("email") or "").strip()
        if email:
            return email, "profile.personal_info.email"

    auth_answer = _work_auth_answer(prompt, profile)
    if auth_answer:
        return auth_answer, "general_meta.work_authorization"

    if "year" in lowered and ("university" in lowered or "school" in lowered or "college" in lowered):
        value = str(gm.get("university_year") or "").strip()
        if value:
            return value, "general_meta.university_year"

    if "gpa" in lowered:
        value = str(gm.get("gpa") or "").strip()
        if value:
            return value, "general_meta.gpa"

    if "availability" in lowered or "available" in lowered or "start" in lowered:
        terms = gm.get("availability_terms", [])
        if isinstance(terms, list) and terms:
            return ", ".join([str(t).strip() for t in terms if str(t).strip()]), "general_meta.availability_terms"

    return None, None


def _answer_from_drafts(prompt: str, drafts: dict[str, Any]) -> tuple[str | None, str | None]:
    lowered = _norm(prompt)

    for pair in drafts.get("question_answer_pairs", []) or []:
        if not isinstance(pair, dict):
            continue
        question = _norm(str(pair.get("question") or ""))
        answer = str(pair.get("answer") or "").strip()
        if not question or not answer:
            continue
        if question == lowered or question in lowered or lowered in question:
            return answer, "draft.question_answer_pairs"

    for key, answer in (drafts.get("short_answers") or {}).items():
        key_norm = _norm(str(key).replace("_", " "))
        answer_text = str(answer or "").strip()
        if not answer_text:
            continue
        if key_norm and (key_norm in lowered or lowered in key_norm):
            return answer_text, "draft.short_answers"

    return None, None


def build_field_payload(
    *,
    form_fields: list[Any],
    drafts: dict[str, Any],
    user_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    settings = get_settings()

    for field in form_fields:
        if isinstance(field, dict):
            label = str(field.get("label") or "")
            metadata = field.get("metadata") or {}
            field_key = str(field.get("field_key") or "")
            field_type = str(field.get("type") or "unknown")
            required = bool(field.get("required", False))
        else:
            label = str(getattr(field, "label", "") or "")
            metadata = getattr(field, "metadata_json", {}) or {}
            field_key = str(getattr(field, "field_key", "") or "")
            field_type = str(getattr(field, "type", "unknown") or "unknown")
            required = bool(getattr(field, "required", False))

        # Honeypot: never fill. (Workday commonly uses name=website + "robots only" label.)
        name = str(metadata.get("name") or "").strip().lower()
        if "robots only" in _norm(label) or (name == "website" and "robot" in _norm(label)):
            payload.append(
                {
                    "field_key": field_key,
                    "label": label,
                    "type": field_type,
                    "required": required,
                    "value": "",
                    "source": "honeypot.skip",
                    "metadata": metadata,
                }
            )
            continue

        field_type_norm = str(field_type or "unknown").lower()
        # Passwords: fill at runtime from env var, never persist the secret.
        if field_type_norm == "password" or "password" in _norm(label):
            payload.append(
                {
                    "field_key": field_key,
                    "label": label,
                    "type": field_type,
                    "required": required,
                    "value": "<redacted>",
                    "runtime_value_env": "WORKDAY_PASSWORD",
                    "source": "secret.env.WORKDAY_PASSWORD",
                    "metadata": {**metadata, "sensitive": True},
                }
            )
            continue

        # File uploads: attach local assets when requested by the form.
        if field_type_norm == "file" or str(metadata.get("input_type") or "").lower() == "file":
            lowered = _norm(label)
            file_value = ""
            file_source = ""

            if "transcript" in lowered:
                candidate = _resolve_transcript_pdf_path(settings)
                if candidate:
                    file_value = str(candidate)
                    file_source = "resolved.transcript_pdf"
            elif "resume" in lowered or "cv" in lowered:
                candidate = _resolve_resume_pdf_path(settings)
                if candidate:
                    file_value = str(candidate)
                    file_source = "resolved.resume_pdf"

            payload.append(
                {
                    "field_key": field_key,
                    "label": label,
                    "type": field_type,
                    "required": required,
                    "value": file_value,
                    "source": file_source or ("missing.required_file" if required else "fallback.empty"),
                    "metadata": {**metadata, "sensitive": True},
                }
            )
            continue

        answer, source = _meta_answer_for_prompt(label, user_profile)

        if not answer:
            answer, source = _answer_from_drafts(label, drafts)

        if not answer:
            if required:
                answer = "N/A"
                source = "fallback.required"
            else:
                answer = ""
                source = "fallback.empty"

        payload.append(
            {
                "field_key": field_key,
                "label": label,
                "type": field_type,
                "required": required,
                "value": answer,
                "source": source,
                "metadata": metadata,
            }
        )

    return payload


def _has_captcha(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in CAPTCHA_PATTERNS)


def _submit_button_selector() -> str:
    return "button[type='submit'], input[type='submit'], button, [role='button']"


def _pick_submit_button(page):
    nodes = page.locator(_submit_button_selector())
    count = nodes.count()
    for idx in range(count):
        node = nodes.nth(idx)
        text = (node.inner_text(timeout=500) or "").strip()
        value_attr = (node.get_attribute("value") or "").strip()
        blob = f"{text} {value_attr}".strip()
        if not blob:
            continue
        for pattern in SUBMIT_BUTTON_PATTERNS:
            if pattern.search(blob):
                return node
    return nodes.first if count > 0 else None


def _pick_button(page, patterns: list[re.Pattern], selectors: list[str] | None = None):
    selectors = selectors or []
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            continue

    nodes = page.locator(_submit_button_selector())
    try:
        count = nodes.count()
    except Exception:
        count = 0
    for idx in range(count):
        node = nodes.nth(idx)
        try:
            if not node.is_visible():
                continue
        except Exception:
            continue
        text = ""
        try:
            text = (node.inner_text(timeout=500) or "").strip()
        except Exception:
            text = ""
        value_attr = ""
        try:
            value_attr = (node.get_attribute("value") or "").strip()
        except Exception:
            value_attr = ""
        blob = f"{text} {value_attr}".strip()
        if not blob:
            continue
        for pattern in patterns:
            if pattern.search(blob):
                return node
    return None


def _try_dismiss_cookie_banners(page) -> None:
    for sel in [
        "button[data-automation-id='legalNoticeAcceptButton']",
        "#onetrust-accept-btn-handler",
    ]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.click(timeout=1500, force=True)
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _list_visible_button_text(surface, *, limit: int = 30) -> list[str]:
    out: list[str] = []
    try:
        nodes = surface.locator(_submit_button_selector())
        count = nodes.count()
    except Exception:
        return out
    for idx in range(min(count, limit)):
        node = nodes.nth(idx)
        try:
            if not node.is_visible():
                continue
        except Exception:
            continue
        text = ""
        try:
            text = (node.inner_text(timeout=300) or "").strip()
        except Exception:
            text = ""
        val = ""
        try:
            val = (node.get_attribute("value") or "").strip()
        except Exception:
            val = ""
        blob = re.sub(r"\s+", " ", f"{text} {val}".strip())
        if blob and blob not in out:
            out.append(blob[:140])
    return out


def _extract_dom_fields(page) -> list[dict[str, Any]]:
    try:
        data = page.evaluate(
            """
            () => {
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                if (!style) return true;
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                const rect = el.getBoundingClientRect();
                return (rect.width > 0 && rect.height > 0);
              };

              const labelForId = new Map();
              document.querySelectorAll('label[for]').forEach((label) => {
                const id = label.getAttribute('for');
                if (id) labelForId.set(id, (label.textContent || '').trim());
              });

              const fields = [];
              const nodes = document.querySelectorAll(
                'input, select, textarea, [role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"], [contenteditable="true"]'
              );
              let n = 0;
              nodes.forEach((el) => {
                if (!isVisible(el)) return;
                const tag = (el.tagName || '').toLowerCase();
                const explicitType = tag === 'input' ? ((el.getAttribute('type') || 'text').toLowerCase()) : tag;
                const role = el.getAttribute('role') || '';
                const inputType = role || explicitType;
                const id = el.getAttribute('id') || '';
                const name = el.getAttribute('name') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const ownLabel = el.closest('label') ? ((el.closest('label').textContent || '').trim()) : '';
                const mappedLabel = id && labelForId.has(id) ? labelForId.get(id) : '';
                const label = ownLabel || mappedLabel || ariaLabel || placeholder || name || id || '';
                if (!label) return;

                const options = [];
                if (tag === 'select') {
                  el.querySelectorAll('option').forEach((opt) => {
                    const text = (opt.textContent || '').trim();
                    if (text) options.push(text);
                  });
                }

                n += 1;
                fields.push({
                  field_key: `dom_${id || name || inputType}_${n}`,
                  label,
                  type: inputType,
                  required: !!el.required || (el.getAttribute('aria-required') === 'true'),
                  metadata: {
                    tag,
                    role,
                    id,
                    name,
                    placeholder,
                    aria_label: ariaLabel,
                    options,
                    input_type: inputType,
                  }
                });
              });

              return fields;
            }
            """
        )
        return list(data or [])
    except Exception:
        return []


def _fill_field(page, item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}
    value = str(item.get("value") or "")
    runtime_env = str(item.get("runtime_value_env") or "").strip()
    if runtime_env:
        runtime_value = os.environ.get(runtime_env, "")
        value = str(runtime_value or "")
    if not value and not item.get("required"):
        return True

    field_type = str(item.get("type") or "").lower()
    field_id = str(metadata.get("id") or "").strip()
    field_name = str(metadata.get("name") or "").strip()
    aria_label = str(metadata.get("aria_label") or metadata.get("ariaLabel") or "").strip()

    locator = None
    if field_id:
        locator = page.locator(f"#{field_id}")
    elif field_name:
        locator = page.locator(f"[name='{field_name}']")
    elif aria_label:
        locator = page.locator(f"[aria-label='{aria_label}']")

    if locator is None or locator.count() == 0:
        label = str(item.get("label") or "").strip()
        if label:
            try:
                locator = page.get_by_label(label)
            except Exception:
                locator = None
        if locator is None or locator.count() == 0:
            return False

    target = locator.first
    try:
        if field_type == "file" or str(metadata.get("input_type") or "").lower() == "file":
            if not value:
                return not bool(item.get("required", False))
            target.set_input_files(value)
            return True
        if field_type == "select":
            options = metadata.get("options") or []
            chosen = value
            if options:
                for opt in options:
                    if _norm(value) in _norm(str(opt)) or _norm(str(opt)) in _norm(value):
                        chosen = str(opt)
                        break
            target.select_option(label=chosen)
            return True

        target.fill(value)
        return True
    except Exception:
        return False


def submit_with_playwright(
    *,
    url: str,
    payload: list[dict[str, Any]],
    storage_state_path: Path,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
    dry_run: bool,
    allow_final_submit: bool,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is required for form submission. Install playwright and browsers.") from exc

    if not storage_state_path.exists():
        raise FileNotFoundError(f"Storage state file not found: {storage_state_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)

        if _has_captcha(page.content()):
            context.close()
            browser.close()
            return {
                "status": "blocked",
                "reason": "captcha_detected_before_fill",
                "response_url": page.url,
                "filled_count": 0,
            }

        filled = 0
        for item in payload:
            if _fill_field(page, item):
                filled += 1

        if dry_run:
            response = {
                "status": "dry_run_ok",
                "response_url": page.url,
                "filled_count": filled,
            }
            context.close()
            browser.close()
            return response

        if not allow_final_submit:
            response = {
                "status": "failed",
                "reason": "final_submit_disabled",
                "response_url": page.url,
                "filled_count": filled,
            }
            context.close()
            browser.close()
            return response

        submit_btn = _pick_submit_button(page)
        if submit_btn is None:
            context.close()
            browser.close()
            return {
                "status": "failed",
                "reason": "submit_button_not_found",
                "response_url": page.url,
                "filled_count": filled,
            }

        submit_btn.click(timeout=5000)
        page.wait_for_timeout(max(wait_ms, 2000))

        content = page.content()
        if _has_captcha(content):
            context.close()
            browser.close()
            return {
                "status": "blocked",
                "reason": "captcha_detected_after_submit",
                "response_url": page.url,
                "filled_count": filled,
            }

        final_url = page.url
        success_markers = [
            "thank you",
            "application submitted",
            "submission received",
            "successfully submitted",
        ]
        lowered = content.lower()
        submitted = any(marker in lowered for marker in success_markers) or final_url != url

        response = {
            "status": "submitted" if submitted else "failed",
            "reason": None if submitted else "submission_confirmation_not_detected",
            "response_url": final_url,
            "filled_count": filled,
        }
        context.close()
        browser.close()
        return response


def submit_with_playwright_workday(
    *,
    url: str,
    drafts: dict[str, Any],
    user_profile: dict[str, Any],
    storage_state_path: Path,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
    dry_run: bool,
    allow_final_submit: bool,
    max_steps: int,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is required for form submission. Install playwright and browsers.") from exc

    if not storage_state_path.exists():
        raise FileNotFoundError(f"Storage state file not found: {storage_state_path}")

    steps: list[dict[str, Any]] = []

    def _has_login_wall_any(page) -> bool:
        def _has_pw(surface) -> bool:
            try:
                pw = surface.locator("input[type='password']")
                return pw.count() > 0 and pw.first.is_visible()
            except Exception:
                return False

        if _has_pw(page):
            return True
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            if _has_pw(fr):
                return True
        return False

    def _try_open_sign_in(page) -> bool:
        # Workday hosted apply pages often require opening a sign-in modal first.
        try:
            btn = page.locator("button[data-automation-id='utilityButtonSignIn']")
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=4000)
                page.wait_for_timeout(max(wait_ms, 1500))
                return True
        except Exception:
            pass
        try:
            btn = _pick_button(page, SIGN_IN_BUTTON_PATTERNS)
            if btn is not None:
                btn.click(timeout=4000)
                page.wait_for_timeout(max(wait_ms, 1500))
                return True
        except Exception:
            pass
        return False

    def _extract_fields_best_surface(page):
        # Return (surface, surface_label, fields)
        best_surface = page
        best_label = "page"
        best_fields = _extract_dom_fields(page)
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                frame_fields = _extract_dom_fields(fr)
            except Exception:
                frame_fields = []
            if len(frame_fields) > len(best_fields):
                best_surface = fr
                best_label = f"frame:{(fr.url or '')[:120]}"
                best_fields = frame_fields
        return best_surface, best_label, best_fields

    def _try_click_apply(page) -> None:
        for sel in [
            "a[data-automation-id='adventureButton']",
            "a[href*='/apply']",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    href = (loc.first.get_attribute("href") or "").strip()
                    if href and "/apply" in href and "/apply" not in (page.url or ""):
                        page.goto(href, wait_until="domcontentloaded", timeout=timeout_ms)
                    else:
                        loc.first.click(timeout=3000)
                    page.wait_for_timeout(max(wait_ms, 1500))
                    return
            except Exception:
                continue

        btn = _pick_button(page, [re.compile(r"\\bapply\\b", re.IGNORECASE)])
        if btn is not None:
            try:
                btn.click(timeout=3000)
                page.wait_for_timeout(max(wait_ms, 1500))
            except Exception:
                pass
        # Fall back: synthesize /apply URL (common on Workday hosted sites).
        try:
            cur = page.url or url
            if "/apply" not in cur:
                base, q = (cur.split("?", 1) + [""])[:2]
                base = base.rstrip("/")
                apply_url = f"{base}/apply"
                if q:
                    apply_url = f"{apply_url}?{q}"
                page.goto(apply_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(wait_ms, 1500))
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        _try_dismiss_cookie_banners(page)
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(250)
        except Exception:
            pass
        _try_click_apply(page)
        _try_dismiss_cookie_banners(page)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        # Ensure we're on the /apply flow before attempting "submit"/"next".
        if "/apply" not in (page.url or ""):
            _try_click_apply(page)
            _try_dismiss_cookie_banners(page)

        if _has_captcha(page.content()):
            context.close()
            browser.close()
            return {"status": "blocked", "reason": "captcha_detected", "response_url": page.url, "steps": steps}

        # Login wall: capture fields/answers and (optionally) submit sign-in.
        if not _has_login_wall_any(page):
            # If no login inputs visible and we have no fields, try opening the sign-in modal.
            surface0, surface0_label, fields0 = _extract_fields_best_surface(page)
            if len(fields0) == 0:
                _try_open_sign_in(page)

        if _has_login_wall_any(page):
            surface, surface_label, fields = _extract_fields_best_surface(page)
            login_payload = build_field_payload(form_fields=fields, drafts=drafts, user_profile=user_profile)
            filled = 0
            for item in login_payload:
                if _fill_field(surface, item):
                    filled += 1
            steps.append(
                {
                    "step": "login",
                    "url": page.url,
                    "surface": surface_label,
                    "filled_count": filled,
                    "fields": [
                        {
                            "label": i.get("label"),
                            "required": bool(i.get("required")),
                            "type": i.get("type"),
                            "value": "<redacted>" if (i.get("metadata") or {}).get("sensitive") else i.get("value"),
                            "source": i.get("source"),
                        }
                        for i in login_payload
                    ],
                }
            )

            if dry_run:
                context.close()
                browser.close()
                return {
                    "status": "dry_run_ok",
                    "reason": "login_wall_detected",
                    "response_url": page.url,
                    "steps": steps,
                }

            # Try sign-in in both page + active surface.
            sign_in = _pick_button(
                page,
                SIGN_IN_BUTTON_PATTERNS,
                selectors=["button[data-automation-id='signInSubmitButton']", "button[type='submit']"],
            ) or _pick_button(
                surface,
                SIGN_IN_BUTTON_PATTERNS,
                selectors=["button[data-automation-id='signInSubmitButton']", "button[type='submit']"],
            )
            if sign_in is None:
                context.close()
                browser.close()
                return {
                    "status": "failed",
                    "reason": "sign_in_button_not_found",
                    "response_url": page.url,
                    "steps": steps,
                }
            sign_in.click(timeout=5000)
            page.wait_for_timeout(max(wait_ms, 2000))
            _try_dismiss_cookie_banners(page)

        # Multi-step navigation.
        for idx in range(max_steps):
            if "/apply" not in (page.url or ""):
                # We're likely still on the job description page; try again.
                _try_click_apply(page)
                _try_dismiss_cookie_banners(page)
                page.wait_for_timeout(max(wait_ms, 1000))

            if _has_captcha(page.content()):
                context.close()
                browser.close()
                return {
                    "status": "blocked",
                    "reason": "captcha_detected",
                    "response_url": page.url,
                    "steps": steps,
                }

            surface, surface_label, fields = _extract_fields_best_surface(page)
            step_payload = build_field_payload(form_fields=fields, drafts=drafts, user_profile=user_profile)
            filled = 0
            for item in step_payload:
                if _fill_field(surface, item):
                    filled += 1

            steps.append(
                {
                    "step": idx + 1,
                    "url": page.url,
                    "surface": surface_label,
                    "filled_count": filled,
                    "fields": [
                        {
                            "label": i.get("label"),
                            "required": bool(i.get("required")),
                            "type": i.get("type"),
                            "value": "<redacted>" if (i.get("metadata") or {}).get("sensitive") else i.get("value"),
                            "source": i.get("source"),
                        }
                        for i in step_payload
                    ],
                }
            )

            submit_btn = _pick_button(
                page,
                WORKDAY_FINAL_SUBMIT_PATTERNS,
                selectors=["button[data-automation-id='bottom-navigation-submit-button']", "button[data-automation-id*='submit']"],
            ) or _pick_button(
                surface,
                WORKDAY_FINAL_SUBMIT_PATTERNS,
                selectors=["button[data-automation-id='bottom-navigation-submit-button']", "button[data-automation-id*='submit']"],
            )
            if submit_btn is not None:
                if dry_run:
                    context.close()
                    browser.close()
                    return {
                        "status": "dry_run_ready_to_submit",
                        "reason": "submit_visible",
                        "response_url": page.url,
                        "steps": steps,
                    }
                if not allow_final_submit:
                    context.close()
                    browser.close()
                    return {
                        "status": "failed",
                        "reason": "final_submit_disabled",
                        "response_url": page.url,
                        "steps": steps,
                    }
                submit_btn.click(timeout=5000)
                page.wait_for_timeout(max(wait_ms, 2500))
                content = page.content()
                if _has_captcha(content):
                    context.close()
                    browser.close()
                    return {
                        "status": "blocked",
                        "reason": "captcha_detected_after_submit",
                        "response_url": page.url,
                        "steps": steps,
                    }

                lowered = content.lower()
                success_markers = [
                    "thank you",
                    "application submitted",
                    "submission received",
                    "successfully submitted",
                ]
                submitted = any(marker in lowered for marker in success_markers)
                context.close()
                browser.close()
                return {
                    "status": "submitted" if submitted else "failed",
                    "reason": None if submitted else "submission_confirmation_not_detected",
                    "response_url": page.url,
                    "steps": steps,
                }

            if len(fields) == 0:
                context.close()
                browser.close()
                return {
                    "status": "failed",
                    "reason": "no_interactive_fields_detected",
                    "response_url": page.url,
                    "steps": steps,
                    "debug": {
                        "page_buttons": _list_visible_button_text(page),
                        "surface_buttons": _list_visible_button_text(surface) if surface is not page else [],
                    },
                }

            next_btn = _pick_button(
                page,
                NEXT_BUTTON_PATTERNS,
                selectors=["button[data-automation-id='bottom-navigation-next-button']", "button[data-automation-id*='next']", "button[data-automation-id*='continue']"],
            ) or _pick_button(
                surface,
                NEXT_BUTTON_PATTERNS,
                selectors=["button[data-automation-id='bottom-navigation-next-button']", "button[data-automation-id*='next']", "button[data-automation-id*='continue']"],
            )
            if next_btn is None:
                context.close()
                browser.close()
                return {
                    "status": "failed",
                    "reason": "next_button_not_found",
                    "response_url": page.url,
                    "steps": steps,
                    "debug": {
                        "page_buttons": _list_visible_button_text(page),
                        "surface_buttons": _list_visible_button_text(surface) if surface is not page else [],
                    },
                }
            try:
                next_btn.click(timeout=5000)
            except Exception:
                try:
                    next_btn.click(timeout=5000, force=True)
                except Exception:
                    context.close()
                    browser.close()
                    return {
                        "status": "failed",
                        "reason": "next_click_failed",
                        "response_url": page.url,
                        "steps": steps,
                    }

            page.wait_for_timeout(max(wait_ms, 2000))
            _try_dismiss_cookie_banners(page)

        context.close()
        browser.close()
        return {
            "status": "failed",
            "reason": "max_steps_exceeded",
            "response_url": page.url,
            "steps": steps,
        }


def perform_submission(
    *,
    url: str,
    payload: list[dict[str, Any]],
    platform: str | None = None,
    drafts: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
    mode: str,
    retries: int,
    dry_run: bool,
    storage_state_path: Path,
    timeout_ms: int,
    wait_ms: int,
    headless: bool,
    allow_final_submit: bool = False,
    max_steps: int = 12,
) -> dict[str, Any]:
    attempts = max(1, int(retries) + 1)
    last: dict[str, Any] = {
        "status": "failed",
        "reason": "not_attempted",
        "response_url": url,
        "filled_count": 0,
        "attempts": 0,
    }

    for attempt in range(1, attempts + 1):
        if mode == "mock":
            blocked = any("captcha" in _norm(str(item.get("label") or "")) for item in payload)
            if blocked:
                last = {
                    "status": "blocked",
                    "reason": "mock_captcha_pattern",
                    "response_url": url,
                    "filled_count": 0,
                    "attempts": attempt,
                }
                break

            last = {
                "status": "dry_run_ok" if dry_run else "failed",
                "reason": None if dry_run else "mock_mode_does_not_submit",
                "response_url": url,
                "filled_count": sum(1 for item in payload if str(item.get("value") or "").strip()),
                "attempts": attempt,
            }
            break

        inferred_platform = (platform or detect_platform(url)).strip().lower() or "generic"
        if inferred_platform == "workday":
            result = submit_with_playwright_workday(
                url=url,
                drafts=drafts or {},
                user_profile=user_profile or {},
                storage_state_path=storage_state_path,
                timeout_ms=timeout_ms,
                wait_ms=wait_ms,
                headless=headless,
                dry_run=dry_run,
                allow_final_submit=allow_final_submit,
                max_steps=max_steps,
            )
        else:
            result = submit_with_playwright(
                url=url,
                payload=payload,
                storage_state_path=storage_state_path,
                timeout_ms=timeout_ms,
                wait_ms=wait_ms,
                headless=headless,
                dry_run=dry_run,
                allow_final_submit=allow_final_submit,
            )
        result["attempts"] = attempt
        last = result

        status = str(result.get("status") or "failed")
        if status in {"submitted", "blocked", "dry_run_ok", "dry_run_ready_to_submit"}:
            break

    return last


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def default_submission_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "mode": settings.form_submit_mode,
        "retries": settings.form_submit_retries,
        "dry_run": settings.form_submit_dry_run,
        "storage_state_path": settings.form_storage_state_path,
        "timeout_ms": settings.form_fetch_timeout_ms,
        "wait_ms": settings.form_fetch_wait_ms,
        "headless": settings.form_browser_headless,
        "allow_final_submit": settings.form_allow_final_submit,
        "max_steps": settings.form_max_steps,
    }
