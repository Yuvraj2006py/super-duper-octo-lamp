import re
from datetime import datetime
from typing import Any

SENIORITY_TERMS = [
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
]

DOCUMENT_REQUIRED_PATTERNS = {
    "cover_letter": [
        re.compile(r"\bcover letter\b.*\b(required|must|submit|include|attach)\b", re.IGNORECASE),
        re.compile(r"\b(required|must|submit|include|attach)\b.*\bcover letter\b", re.IGNORECASE),
    ],
    "transcript": [
        re.compile(r"\btranscript\b.*\b(required|must|submit|include|attach)\b", re.IGNORECASE),
        re.compile(r"\b(required|must|submit|include|attach)\b.*\btranscript\b", re.IGNORECASE),
    ],
}

QUESTION_LINE_PATTERNS = [
    re.compile(r"^\s*question\s*:\s*(.+)$", re.IGNORECASE),
    re.compile(r"^\s*(?:[-*]|\d+\.)\s*(.+\?)\s*$"),
]

UNAVAILABLE_PATTERNS = [
    re.compile(r"\bjob (?:you['’]re|you are) looking for is no longer available\b", re.IGNORECASE),
    re.compile(r"\bposition has been filled\b", re.IGNORECASE),
    re.compile(r"\bposte .* a été pourvu\b", re.IGNORECASE),
    re.compile(r"\bno longer available\b", re.IGNORECASE),
    re.compile(r"\bworkday is currently unavailable\b", re.IGNORECASE),
    re.compile(r"\bmaintenance page\b", re.IGNORECASE),
]


def _sanitize_scalar(value: str | None, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip(" -|:\t")
    if not text:
        return None
    if len(text) <= max_len:
        return text

    # Prefer cutting at a natural boundary before hard truncation.
    boundary = max(text.rfind(" ", 0, max_len), text.rfind(",", 0, max_len), text.rfind(";", 0, max_len))
    if boundary >= int(max_len * 0.6):
        text = text[:boundary]
    else:
        text = text[:max_len]
    return text.rstrip(" -|,;")


def _find_first(patterns: list[str], text: str, *, max_len: int) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = _sanitize_scalar(match.group(1), max_len=max_len)
            if value:
                return value
    return None


def _normalize_text_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


def _required_documents(raw_text: str, raw_payload: dict[str, Any]) -> dict[str, bool]:
    lowered = raw_text.lower()

    required_docs = raw_payload.get("required_documents", [])
    if isinstance(required_docs, str):
        required_docs = [required_docs]
    required_tokens = {str(item).strip().lower() for item in required_docs if str(item).strip()}

    requires_cover_letter = bool(raw_payload.get("requires_cover_letter", False)) or any(
        token in {"cover_letter", "cover letter"} for token in required_tokens
    )
    requires_transcript = bool(raw_payload.get("requires_transcript", False)) or any(
        token in {"transcript", "official transcript", "unofficial transcript"}
        for token in required_tokens
    )

    if not requires_cover_letter:
        requires_cover_letter = any(pattern.search(lowered) for pattern in DOCUMENT_REQUIRED_PATTERNS["cover_letter"])
    if not requires_transcript:
        requires_transcript = any(pattern.search(lowered) for pattern in DOCUMENT_REQUIRED_PATTERNS["transcript"])

    return {
        "requires_cover_letter": requires_cover_letter,
        "requires_transcript": requires_transcript,
    }


def _extract_application_questions(raw_text: str, raw_payload: dict[str, Any]) -> list[str]:
    provided = raw_payload.get("application_questions", [])
    questions: list[str] = []

    if isinstance(provided, list):
        questions.extend([str(item).strip() for item in provided if str(item).strip()])
    elif isinstance(provided, str) and provided.strip():
        questions.append(provided.strip())

    for line in _normalize_text_lines(raw_text):
        if "?" not in line and not line.lower().startswith("question:"):
            continue
        candidate = ""
        for pattern in QUESTION_LINE_PATTERNS:
            match = pattern.match(line)
            if match:
                candidate = match.group(1).strip()
                break
        if not candidate and line.endswith("?"):
            candidate = line.strip()
        if candidate and len(candidate) <= 320:
            questions.append(candidate)

    deduped: list[str] = []
    seen = set()
    for question in questions:
        normalized = re.sub(r"\s+", " ", question).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:10]


def _posting_active_status(raw_text: str, raw_payload: dict[str, Any]) -> tuple[bool, str | None]:
    if raw_payload.get("posting_active") is False:
        return False, "posting_active=false in payload"

    for pattern in UNAVAILABLE_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            return False, f"matched unavailable pattern: {match.group(0)}"
    return True, None


def normalize_job(raw_text: str, raw_payload: dict[str, Any]) -> dict[str, Any]:
    title = _sanitize_scalar(raw_payload.get("title"), max_len=255) or _find_first(
        [
            r"title:\s*(.{1,255}?)(?:\n|$|\s{2,}|company:|location:)",
            r"position:\s*(.{1,255}?)(?:\n|$|\s{2,}|company:|location:)",
            r"job title:\s*(.{1,255}?)(?:\n|$|\s{2,}|company:|location:)",
        ],
        raw_text,
        max_len=255,
    )
    company = _sanitize_scalar(raw_payload.get("company"), max_len=255) or _find_first(
        [r"company:\s*(.{1,255}?)(?:\n|$|\s{2,}|location:|title:|position:)"],
        raw_text,
        max_len=255,
    )
    location = _sanitize_scalar(raw_payload.get("location"), max_len=255) or _find_first(
        [
            r"location:\s*(.{1,255}?)(?:\n|$|\s{2,}|company:|title:|position:)",
            r"\b(remote|hybrid|onsite)\b",
        ],
        raw_text,
        max_len=255,
    )

    lowered = raw_text.lower()
    seniority = _sanitize_scalar(raw_payload.get("seniority"), max_len=100)
    if not seniority:
        for term in SENIORITY_TERMS:
            if term in lowered:
                seniority = term
                break

    requirements = raw_payload.get("requirements", [])
    if not requirements:
        bullets = re.findall(r"[-*]\s+(.+)", raw_text)
        requirements = bullets[:12]

    must_have = raw_payload.get("must_have", [])
    if not must_have:
        must_have = [req for req in requirements if "must" in req.lower() or "required" in req.lower()]

    doc_requirements = _required_documents(raw_text, raw_payload)
    application_questions = _extract_application_questions(raw_text, raw_payload)
    posting_active, inactive_reason = _posting_active_status(raw_text, raw_payload)

    return {
        "title": title,
        "company": company,
        "location": location,
        "seniority": seniority,
        "requirements": requirements,
        "must_have": must_have,
        "requires_cover_letter": doc_requirements["requires_cover_letter"],
        "requires_transcript": doc_requirements["requires_transcript"],
        "application_questions": application_questions,
        "posting_active": posting_active,
        "posting_inactive_reason": inactive_reason,
        "normalized_at": datetime.utcnow().isoformat(),
    }
