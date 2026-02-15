from app.services.embeddings import MockEmbeddingProvider
from app.services.scoring import compute_fit_score


def test_compute_fit_score_returns_weighted_breakdown():
    user_profile = {
        "summary": "Computer science student with FastAPI and PostgreSQL experience",
        "skills": ["python", "fastapi", "postgresql", "redis", "celery"],
        "experience": [{"highlights": "Built reliable backend services"}],
        "preferred_locations": ["remote", "us", "canada"],
        "preferred_seniority": ["intern", "co-op", "new grad"],
        "internship_preferences": {
            "target_internships_only": True,
            "all_tech_roles": True,
            "target_role_families": ["data", "ml", "backend", "software"],
            "preferred_locations": ["remote", "us", "canada"],
        },
    }
    job_structured = {
        "requirements": ["FastAPI", "PostgreSQL", "Redis"],
        "must_have": ["FastAPI", "PostgreSQL"],
        "location": "Remote - US",
        "seniority": "intern",
        "posted_at": "2026-02-10T09:00:00+00:00",
        "title": "Machine Learning Intern",
    }
    job_raw_text = "Machine Learning Intern role requiring FastAPI and PostgreSQL with Redis"

    total, breakdown = compute_fit_score(
        user_profile=user_profile,
        job_structured=job_structured,
        job_raw_text=job_raw_text,
        embedding_provider=MockEmbeddingProvider(dim=64),
    )

    assert 0 <= total <= 1
    assert total == breakdown["total"]
    assert {
        "keyword_skill_match",
        "semantic_similarity",
        "must_have_satisfaction",
        "seniority_location_fit",
        "recency_score",
        "total",
    }.issubset(set(breakdown.keys()))
    assert breakdown["internship_role_fit"] == 1.0
