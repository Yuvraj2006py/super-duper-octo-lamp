from app.services.verification import verify_drafts


def test_verification_blocks_hallucinated_claims():
    profile = {
        "experience": [
            {
                "company": "Northwind Labs",
                "title": "Senior Software Engineer",
                "start_date": "2022-01",
                "end_date": "2025-12",
            }
        ],
        "allowed_claims": [
            {"claim": "Reduced API latency by 35% at Northwind Labs.", "metric": "35%"}
        ],
    }
    drafts = {
        "resume_summary": "I delivered 55% growth at Fabrikam and have 12 years experience.",
        "cover_letter": "I worked at Fabrikam and improved conversion by 55%.",
        "bullet_ordering": ["Led migration"],
        "short_answers": {"why": "I have 12 years of experience."},
    }
    claims_table = [{"claim": "Worked at Fabrikam", "source_field": "", "source_chunk_key": "x"}]

    report = verify_drafts(user_profile=profile, drafts=drafts, claims_table=claims_table)

    assert report["passed"] is False
    assert any("source_field" in reason for reason in report["reasons"])
    assert any("Metric" in reason for reason in report["reasons"])
    assert any("Banned phrase" in reason for reason in report["reasons"])


def test_verification_blocks_seniority_self_claims_for_internship_mode():
    profile = {
        "experience": [{"company": "Northwind Labs", "title": "Software Engineer"}],
        "allowed_claims": [],
        "internship_preferences": {"target_internships_only": True},
    }
    drafts = {
        "resume_summary": "I am a student applying for internship roles.",
        "cover_letter": "As a seasoned engineer, I am a senior backend engineer ready for this role.",
        "bullet_ordering": [],
        "short_answers": {"why": "I am excited for this internship."},
    }
    claims_table = [{"claim": "I am a senior backend engineer", "source_field": "summary", "source_chunk_key": "x"}]

    report = verify_drafts(user_profile=profile, drafts=drafts, claims_table=claims_table)

    assert report["passed"] is False
    assert any("Internship tone violation" in reason for reason in report["reasons"])
