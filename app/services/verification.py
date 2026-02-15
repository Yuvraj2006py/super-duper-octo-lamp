import re
from typing import Any


BANNED_YEARS_PATTERN = re.compile(r"\b\d+\+?\s+years\b", re.IGNORECASE)
SENIORITY_SELF_CLAIM_PATTERNS = [
    re.compile(r"\bi am (?:a|an)\s+senior\b", re.IGNORECASE),
    re.compile(r"\bas (?:a|an)\s+senior\b", re.IGNORECASE),
    re.compile(r"\bseasoned\b", re.IGNORECASE),
    re.compile(r"\bstaff[-\s]?level\b", re.IGNORECASE),
    re.compile(r"\bprincipal\b", re.IGNORECASE),
]
METRIC_PATTERN = re.compile(
    r"(?<!\d)(\$\d+(?:\.\d+)?[kKmM]?|\d{1,3}(?:,\d{3})+(?:\.\d+)?\+?%?|\d+\+%?|\d+%|\d+x)(?!\d)"
)
YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
EMPLOYER_PATTERN = re.compile(r"\bat\s+([A-Z][A-Za-z0-9&.\- ]{1,40}?)(?=[,.;:\n]|$)")
TITLE_MENTION_PATTERN = re.compile(r"\bas\s+(?:a|an)?\s*([A-Za-z][A-Za-z/& -]{2,50})", re.IGNORECASE)
TITLE_HINTS = {
    "engineer",
    "developer",
    "manager",
    "analyst",
    "intern",
    "lead",
    "scientist",
    "consultant",
    "designer",
    "coordinator",
    "specialist",
    "assistant",
    "architect",
    "director",
    "officer",
    "president",
    "founder",
}
GENERIC_TITLE_TOKENS = {
    "developer",
    "engineer",
    "analyst",
    "intern",
    "manager",
    "scientist",
}


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _collect_profile_facts(profile: dict[str, Any]) -> dict[str, set[str]]:
    employers = {exp.get("company", "").strip() for exp in profile.get("experience", []) if exp.get("company")}
    titles = {exp.get("title", "").strip() for exp in profile.get("experience", []) if exp.get("title")}
    schools = {edu.get("school", "").strip() for edu in profile.get("education", []) if edu.get("school")}
    dates = {
        exp.get("start_date", "").strip() for exp in profile.get("experience", []) if exp.get("start_date")
    } | {exp.get("end_date", "").strip() for exp in profile.get("experience", []) if exp.get("end_date")}

    allowed_claim_text = {
        item.get("claim", "").strip() for item in profile.get("allowed_claims", []) if item.get("claim")
    }

    metrics = {
        str(item.get("metric", "")).strip()
        for item in profile.get("allowed_claims", [])
        if item.get("metric") is not None
    }

    return {
        "employers": {v for v in employers if v},
        "schools": {v for v in schools if v},
        "titles": {v for v in titles if v},
        "dates": {v for v in dates if v},
        "allowed_claim_text": {v for v in allowed_claim_text if v},
        "metrics": {v for v in metrics if v},
    }


def verify_drafts(
    *,
    user_profile: dict[str, Any],
    drafts: dict[str, Any],
    claims_table: list[dict[str, Any]],
    job_structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    facts = _collect_profile_facts(user_profile)
    reasons: list[str] = []
    internship_prefs = user_profile.get("internship_preferences", {}) or {}
    internship_mode = bool(internship_prefs.get("target_internships_only", False))
    profile_years = {
        year
        for date in facts["dates"]
        for year in re.findall(r"(?:19|20)\d{2}", date)
    }
    target_company = str((job_structured or {}).get("company") or "").strip().lower()
    target_title = str((job_structured or {}).get("title") or "").strip().lower()
    target_title_hints = {hint for hint in TITLE_HINTS if re.search(rf"\b{hint}\b", target_title)}
    known_titles_lower = {title.lower() for title in facts["titles"]}
    known_employers_normalized = {_normalize_token(employer) for employer in facts["employers"]}
    known_schools_normalized = {_normalize_token(school) for school in facts["schools"]}
    target_company_normalized = _normalize_token(target_company) if target_company else ""

    combined_text = "\n".join(
        [
            drafts.get("resume_summary", ""),
            drafts.get("cover_letter", ""),
            "\n".join(drafts.get("bullet_ordering", [])),
            "\n".join(drafts.get("short_answers", {}).values()),
        ]
    )

    for claim in claims_table:
        if not claim.get("source_field"):
            reasons.append(f"Claim missing source_field: {claim.get('claim', '')[:80]}")

    for match in METRIC_PATTERN.findall(combined_text):
        normalized = match.strip(" .,")
        if YEAR_PATTERN.match(normalized):
            if normalized not in profile_years:
                reasons.append(f"Date year '{normalized}' not present in profile")
            continue
        if normalized.isdigit() and int(normalized) < 20:
            continue
        if normalized and normalized not in facts["metrics"]:
            if normalized not in " ".join(facts["allowed_claim_text"]):
                reasons.append(f"Metric '{normalized}' not present in allowed claims")

    years_mentions = BANNED_YEARS_PATTERN.findall(combined_text)
    allowed_text_blob = " ".join(facts["allowed_claim_text"]).lower()
    for mention in years_mentions:
        if mention.lower() not in allowed_text_blob:
            reasons.append(f"Banned phrase requires explicit profile evidence: '{mention}'")

    for employer in EMPLOYER_PATTERN.findall(combined_text):
        normalized = employer.strip()
        if not normalized:
            continue
        normalized_token = _normalize_token(normalized)
        if target_company_normalized and (
            normalized_token == target_company_normalized
            or normalized_token.startswith(target_company_normalized + " ")
        ):
            continue
        if any(
            normalized_token == employer_token or normalized_token.startswith(employer_token + " ")
            for employer_token in known_employers_normalized
            if employer_token
        ):
            continue
        if normalized_token and normalized_token in known_schools_normalized:
            continue
        if normalized_token and normalized_token not in known_employers_normalized:
            reasons.append(f"Employer not found in profile experience: '{normalized}'")

    for mention in TITLE_MENTION_PATTERN.findall(combined_text):
        normalized = re.sub(r"\s+", " ", mention).strip(" .,-")
        if not normalized:
            continue
        if "role" in normalized.lower():
            continue
        if not re.search(rf"\b({'|'.join(TITLE_HINTS)})\b", normalized, flags=re.IGNORECASE):
            continue
        normalized_lower = normalized.lower()
        if "candidate" in normalized_lower:
            continue
        if " at " in normalized_lower:
            continue
        if normalized_lower in GENERIC_TITLE_TOKENS:
            continue
        if target_title and target_title in normalized_lower:
            continue
        if target_title_hints and any(hint in normalized_lower for hint in target_title_hints):
            continue
        grounded = normalized_lower in known_titles_lower or any(title in normalized_lower for title in known_titles_lower)
        if not grounded:
            reasons.append(f"Title not found in profile experience: '{normalized}'")

    if internship_mode:
        # For internship mode, block self-positioning language that overstates seniority.
        body_without_subject = re.sub(r"^Re:\s*.*$", "", combined_text, flags=re.MULTILINE)
        for pattern in SENIORITY_SELF_CLAIM_PATTERNS:
            match = pattern.search(body_without_subject)
            if match:
                reasons.append(
                    f"Internship tone violation: self-seniority phrase '{match.group(0)}' is not allowed"
                )

    dedup_reasons: list[str] = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            dedup_reasons.append(reason)
            seen.add(reason)
    reasons = dedup_reasons

    passed = len(reasons) == 0
    return {
        "passed": passed,
        "reasons": reasons,
        "checks": {
            "claims_have_sources": all(c.get("source_field") for c in claims_table),
            "metrics_grounded": not any("Metric" in r for r in reasons),
            "banned_years_blocked": not any("Banned phrase" in r for r in reasons),
            "employers_grounded": not any("Employer" in r for r in reasons),
        },
        "claims_checked": len(claims_table),
    }
