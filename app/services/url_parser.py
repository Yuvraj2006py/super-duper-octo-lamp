import html
import json
import re
from typing import Any

import httpx


QUESTION_KEYS = {
    "question",
    "questiontext",
    "question_text",
    "questionlabel",
    "prompt",
    "label",
    "fieldlabel",
    "helptext",
}

QUESTION_PREFIX = re.compile(
    r"^(why|how|what|describe|tell us|tell me|please describe|please share|"
    r"are you|do you|will you|can you|have you|where|when|explain)\b",
    re.IGNORECASE,
)

QUESTION_BAN_PATTERNS = [
    re.compile(r"\b(cookie|privacy|site map|accessibility|skip to|terms of use)\b", re.IGNORECASE),
    re.compile(r"\b(sign in|log in|create account|alert)\b", re.IGNORECASE),
    re.compile(r"\b(linkedin|facebook|instagram|youtube|x.com)\b", re.IGNORECASE),
]

BLOCK_TAGS = (
    "p",
    "div",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "tr",
    "section",
    "article",
    "label",
    "legend",
)


def detect_platform(url: str) -> str:
    lowered = (url or "").lower()
    if "myworkdayjobs.com" in lowered or ".wd" in lowered:
        return "workday"
    if "greenhouse.io" in lowered:
        return "greenhouse"
    if "lever.co" in lowered or "jobs.lever.co" in lowered:
        return "lever"
    if "smartrecruiters.com" in lowered:
        return "smartrecruiters"
    return "generic"


def _extract_title(html_text: str) -> str:
    og_title = re.search(
        r"<meta[^>]+property=['\"]og:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        html_text,
        flags=re.IGNORECASE,
    )
    if og_title:
        return html.unescape(og_title.group(1)).strip()

    title_match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not title_match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()


def _strip_html_to_text(html_text: str) -> str:
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
    for tag in BLOCK_TAGS:
        cleaned = re.sub(rf"</{tag}>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


def _normalize_question(text: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    value = re.sub(r"\s+", " ", value).strip(" -•\t")
    return value


def _looks_like_question(text: str) -> bool:
    value = _normalize_question(text)
    if len(value) < 12 or len(value) > 320:
        return False
    lowered = value.lower()
    if any(pattern.search(lowered) for pattern in QUESTION_BAN_PATTERNS):
        return False
    if value.endswith("?"):
        return True
    return bool(QUESTION_PREFIX.match(value))


def _dedupe(values: list[str], *, max_items: int) -> list[str]:
    out: list[str] = []
    seen = set()
    for value in values:
        norm = _normalize_question(value)
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_items:
            break
    return out


def _extract_questions_from_text(text: str) -> list[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidates: list[str] = []
    for line in lines:
        if _looks_like_question(line):
            candidates.append(line)
            continue
        if line.lower().startswith("question:"):
            tail = line.split(":", 1)[1].strip() if ":" in line else line
            if _looks_like_question(tail) or len(tail) >= 12:
                candidates.append(tail)
    return _dedupe(candidates, max_items=15)


def _extract_questions_from_labels(html_text: str) -> list[str]:
    candidates: list[str] = []
    label_matches = re.findall(r"<label[^>]*>(.*?)</label>", html_text, flags=re.IGNORECASE | re.DOTALL)
    legend_matches = re.findall(r"<legend[^>]*>(.*?)</legend>", html_text, flags=re.IGNORECASE | re.DOTALL)
    aria_matches = re.findall(r"aria-label=['\"]([^'\"]+)['\"]", html_text, flags=re.IGNORECASE)
    placeholder_matches = re.findall(r"placeholder=['\"]([^'\"]+)['\"]", html_text, flags=re.IGNORECASE)

    for raw in [*label_matches, *legend_matches, *aria_matches, *placeholder_matches]:
        value = _normalize_question(raw)
        if _looks_like_question(value):
            candidates.append(value)
    return _dedupe(candidates, max_items=20)


def _collect_question_strings_from_json(data: Any, *, out: list[str], parent_key: str = "") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            key_norm = re.sub(r"[^a-z0-9]+", "", key.lower())
            if isinstance(value, str):
                if key_norm in QUESTION_KEYS or "question" in key_norm:
                    out.append(value)
                elif parent_key and "question" in parent_key and len(value) <= 320:
                    out.append(value)
            _collect_question_strings_from_json(value, out=out, parent_key=key_norm)
        return

    if isinstance(data, list):
        for item in data:
            _collect_question_strings_from_json(item, out=out, parent_key=parent_key)


def _extract_questions_from_json_scripts(html_text: str) -> list[str]:
    candidates: list[str] = []

    for block in re.findall(
        r"<script[^>]+type=['\"]application/ld\+json['\"][^>]*>([\s\S]*?)</script>",
        html_text,
        flags=re.IGNORECASE,
    ):
        raw = block.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        _collect_question_strings_from_json(data, out=candidates)

    next_data = re.search(
        r"<script[^>]+id=['\"]__NEXT_DATA__['\"][^>]*>([\s\S]*?)</script>",
        html_text,
        flags=re.IGNORECASE,
    )
    if next_data:
        raw = next_data.group(1).strip()
        try:
            data = json.loads(raw)
            _collect_question_strings_from_json(data, out=candidates)
        except Exception:
            pass

    filtered = [value for value in candidates if _looks_like_question(value)]
    return _dedupe(filtered, max_items=20)


def _extract_required_documents(text: str) -> list[str]:
    lowered = text.lower()
    docs: list[str] = []
    if re.search(r"\b(required|must|submit|include|attach)\b[^.\n]{0,60}\bcover letter\b", lowered):
        docs.append("cover_letter")
    if re.search(r"\bcover letter\b[^.\n]{0,60}\b(required|must|submit|include|attach)\b", lowered):
        docs.append("cover_letter")
    if re.search(r"\b(required|must|submit|include|attach)\b[^.\n]{0,60}\btranscript\b", lowered):
        docs.append("transcript")
    if re.search(r"\btranscript\b[^.\n]{0,60}\b(required|must|submit|include|attach)\b", lowered):
        docs.append("transcript")
    return _dedupe(docs, max_items=5)


def extract_job_payload_from_html(
    *,
    source_url: str,
    html_text: str,
    final_url: str,
    status_code: int,
    external_id: str | None = None,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    user_questions: list[str] | None = None,
) -> dict[str, Any]:
    platform = detect_platform(source_url)
    raw_text = _strip_html_to_text(html_text)
    text_questions = _extract_questions_from_text(raw_text)
    html_questions = _extract_questions_from_labels(html_text)
    json_questions = _extract_questions_from_json_scripts(html_text)
    provided_questions = user_questions or []
    all_questions = _dedupe(
        [*provided_questions, *json_questions, *html_questions, *text_questions],
        max_items=20,
    )

    payload: dict[str, Any] = {
        "external_id": external_id or source_url,
        "url": source_url,
        "platform": platform,
        "title": title or _extract_title(html_text),
        "company": company,
        "location": location,
        "raw_text": raw_text,
        "application_questions": all_questions,
        "required_documents": _extract_required_documents(raw_text),
        "source_metadata": {
            "status_code": status_code,
            "final_url": final_url,
            "platform": platform,
            "question_sources": {
                "provided": len([q for q in provided_questions if _normalize_question(q)]),
                "json_scripts": len(json_questions),
                "labels": len(html_questions),
                "text_lines": len(text_questions),
            },
        },
    }
    return payload


def fetch_and_extract_job_payload(
    *,
    url: str,
    timeout_seconds: int = 45,
    external_id: str | None = None,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    user_questions: list[str] | None = None,
) -> dict[str, Any]:
    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobAssistantMVP/1.0)"},
    )
    return extract_job_payload_from_html(
        source_url=url,
        html_text=response.text,
        final_url=str(response.url),
        status_code=response.status_code,
        external_id=external_id,
        title=title,
        company=company,
        location=location,
        user_questions=user_questions,
    )
