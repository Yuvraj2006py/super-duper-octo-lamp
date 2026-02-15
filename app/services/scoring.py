from datetime import datetime, timezone
from typing import Any

from app.services.embeddings import EmbeddingProvider, cosine_similarity


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


INTERNSHIP_TERMS = {
    "intern",
    "internship",
    "co-op",
    "co op",
    "coop",
    "new grad",
    "student",
}

TECH_ROLE_HINTS = {
    "software",
    "developer",
    "engineer",
    "backend",
    "frontend",
    "full stack",
    "full-stack",
    "api",
    "data",
    "machine learning",
    "ml",
    "ai",
    "analytics",
    "platform",
    "devops",
    "cloud",
}

ROLE_FAMILY_KEYWORDS = {
    "data": {"data", "analytics", "sql", "etl", "warehouse", "pipeline", "bi"},
    "ml": {"machine learning", "ml", "model", "nlp", "computer vision", "llm", "ai"},
    "backend": {"backend", "api", "fastapi", "django", "flask", "microservice"},
    "software": {"software", "engineer", "developer", "swe"},
}


def _text_blob(*parts: str) -> str:
    return " ".join([part for part in parts if part]).lower()


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _extract_preferred_seniority(user_profile: dict[str, Any], internship_only: bool) -> list[str]:
    values = [str(s).lower() for s in user_profile.get("preferred_seniority", []) if str(s).strip()]
    if values:
        return values
    if internship_only:
        return ["intern", "co-op", "junior", "new grad"]
    return ["mid", "senior", "staff"]


def _extract_preferred_locations(user_profile: dict[str, Any]) -> list[str]:
    prefs = [str(loc).lower() for loc in user_profile.get("preferred_locations", []) if str(loc).strip()]
    if prefs:
        return prefs

    internship_prefs = user_profile.get("internship_preferences", {}) or {}
    fallback = internship_prefs.get("preferred_locations", [])
    fallback_locs = [str(loc).lower() for loc in fallback if str(loc).strip()]
    return fallback_locs or ["remote", "us", "canada"]


def _location_match_score(target_location: str, preferred_locations: list[str]) -> float:
    if not target_location:
        return 0.7

    normalized = target_location.lower()
    if "remote" in normalized and any("remote" in pref for pref in preferred_locations):
        return 1.0

    us_tokens = {"us", "usa", "united states"}
    ca_tokens = {"ca", "canada"}
    if any(pref in normalized or normalized in pref for pref in preferred_locations):
        return 1.0
    if any(pref in us_tokens for pref in preferred_locations) and any(token in normalized for token in us_tokens):
        return 1.0
    if any(pref in ca_tokens for pref in preferred_locations) and any(token in normalized for token in ca_tokens):
        return 1.0
    return 0.35


def _internship_role_fit(job_text: str, internship_only: bool) -> float:
    if _contains_any(job_text, INTERNSHIP_TERMS):
        return 1.0
    return 0.1 if internship_only else 0.7


def _role_family_match(user_profile: dict[str, Any], job_text: str) -> float:
    prefs = user_profile.get("internship_preferences", {}) or {}
    target_families = [str(item).lower() for item in prefs.get("target_role_families", []) if str(item).strip()]
    all_tech_roles = bool(prefs.get("all_tech_roles", False))

    if not target_families:
        return 1.0 if _contains_any(job_text, TECH_ROLE_HINTS) else 0.6

    if all_tech_roles:
        return 1.0 if _contains_any(job_text, TECH_ROLE_HINTS) else 0.4

    family_scores: list[float] = []
    for family in target_families:
        keywords = ROLE_FAMILY_KEYWORDS.get(family, {family})
        family_scores.append(1.0 if _contains_any(job_text, set(keywords)) else 0.2)

    if not family_scores:
        return 0.6
    return max(family_scores)


def compute_fit_score(
    *,
    user_profile: dict[str, Any],
    job_structured: dict[str, Any],
    job_raw_text: str,
    embedding_provider: EmbeddingProvider,
) -> tuple[float, dict[str, float]]:
    profile_skills = {skill.lower() for skill in user_profile.get("skills", [])}
    requirements = [r.lower() for r in job_structured.get("requirements", [])]

    required_skill_tokens = set()
    for req in requirements:
        for token in req.replace(",", " ").split():
            if len(token) > 2:
                required_skill_tokens.add(token)

    overlap = len([token for token in required_skill_tokens if token in profile_skills])
    keyword_skill_match = overlap / max(1, len(required_skill_tokens))

    profile_summary = " ".join(
        [
            user_profile.get("summary", ""),
            " ".join(user_profile.get("skills", [])),
            " ".join([exp.get("highlights", "") for exp in user_profile.get("experience", [])]),
        ]
    )
    emb_job, emb_profile = embedding_provider.embed_texts([job_raw_text, profile_summary])
    semantic_similarity = _clamp((cosine_similarity(emb_job, emb_profile) + 1.0) / 2.0)

    must_have = [item.lower() for item in job_structured.get("must_have", [])]
    must_hits = sum(
        1
        for item in must_have
        if any(skill in item for skill in profile_skills)
        or item in profile_summary.lower()
    )
    must_have_satisfaction = must_hits / max(1, len(must_have)) if must_have else 1.0

    internship_prefs = user_profile.get("internship_preferences", {}) or {}
    internship_only = bool(internship_prefs.get("target_internships_only", False))

    target_seniority = (job_structured.get("seniority") or "").lower()
    seniority_pref = _extract_preferred_seniority(user_profile, internship_only=internship_only)
    seniority_match = 1.0 if not target_seniority or target_seniority in seniority_pref else 0.4

    target_location = (job_structured.get("location") or "").lower()
    preferred_locations = _extract_preferred_locations(user_profile)
    location_match = _location_match_score(target_location, preferred_locations)

    job_text = _text_blob(
        job_structured.get("title", ""),
        job_structured.get("seniority", ""),
        job_structured.get("location", ""),
        " ".join(job_structured.get("requirements", [])),
        job_raw_text,
    )
    internship_role_fit = _internship_role_fit(job_text, internship_only=internship_only)
    role_family_match = _role_family_match(user_profile, job_text)

    seniority_location_fit = _clamp(
        (seniority_match + location_match + internship_role_fit + role_family_match) / 4.0
    )

    posted_at_raw = job_structured.get("posted_at")
    recency_score = 0.5
    if posted_at_raw:
        try:
            posted_at = datetime.fromisoformat(posted_at_raw.replace("Z", "+00:00"))
            age_days = max(0, (datetime.now(timezone.utc) - posted_at).days)
            recency_score = _clamp(1.0 - (age_days / 30.0))
        except Exception:
            recency_score = 0.5

    weighted = {
        "keyword_skill_match": _clamp(keyword_skill_match),
        "semantic_similarity": _clamp(semantic_similarity),
        "must_have_satisfaction": _clamp(must_have_satisfaction),
        "seniority_location_fit": _clamp(seniority_location_fit),
        "recency_score": _clamp(recency_score),
        "internship_role_fit": _clamp(internship_role_fit),
        "role_family_match": _clamp(role_family_match),
        "location_match": _clamp(location_match),
        "seniority_match": _clamp(seniority_match),
    }

    total = (
        0.30 * weighted["keyword_skill_match"]
        + 0.30 * weighted["semantic_similarity"]
        + 0.15 * weighted["must_have_satisfaction"]
        + 0.15 * weighted["seniority_location_fit"]
        + 0.10 * weighted["recency_score"]
    )

    weighted["total"] = round(total, 6)
    return weighted["total"], weighted
