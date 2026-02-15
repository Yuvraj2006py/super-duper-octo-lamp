from app.services.parsing import normalize_job


def test_normalize_job_extracts_core_fields():
    raw_text = (
        "Title: Senior Backend Engineer\n"
        "Company: Acme Analytics\n"
        "Location: Remote - US\n"
        "- Must have FastAPI\n"
        "- Required PostgreSQL\n"
    )
    raw_payload = {"requirements": ["Must have FastAPI", "Required PostgreSQL"]}

    normalized = normalize_job(raw_text, raw_payload)

    assert normalized["title"] == "Senior Backend Engineer"
    assert normalized["company"] == "Acme Analytics"
    assert "remote" in normalized["location"].lower()
    assert len(normalized["requirements"]) == 2
    assert any("must" in req.lower() for req in normalized["must_have"])
    assert normalized["requires_cover_letter"] is False
    assert normalized["requires_transcript"] is False


def test_normalize_job_detects_document_requirements_and_questions():
    raw_text = (
        "Title: Data Engineering Intern\n"
        "Company: Example Corp\n"
        "Location: Remote - US\n"
        "Application materials: cover letter required.\n"
        "Please submit unofficial transcript.\n"
        "Question: Why are you interested in this role?\n"
    )
    raw_payload = {}

    normalized = normalize_job(raw_text, raw_payload)

    assert normalized["requires_cover_letter"] is True
    assert normalized["requires_transcript"] is True
    assert "Why are you interested in this role?" in normalized["application_questions"]


def test_normalize_job_marks_unavailable_posting_inactive():
    raw_text = "Sorry, the job you're looking for is no longer available."
    normalized = normalize_job(raw_text, {})

    assert normalized["posting_active"] is False
    assert normalized["posting_inactive_reason"] is not None


def test_normalize_job_marks_maintenance_page_inactive():
    raw_text = "Workday is currently unavailable. Please visit the maintenance page."
    normalized = normalize_job(raw_text, {})

    assert normalized["posting_active"] is False
    assert "unavailable" in (normalized["posting_inactive_reason"] or "").lower()


def test_normalize_job_bounds_long_scalar_fields():
    very_long_company = "A" * 600
    very_long_location = "Toronto, ON " + ("Canada " * 120)
    raw_payload = {
        "title": "Data Analytics Intern",
        "company": very_long_company,
        "location": very_long_location,
    }

    normalized = normalize_job("Title: Data Analytics Intern", raw_payload)

    assert normalized["title"] == "Data Analytics Intern"
    assert normalized["company"] is not None
    assert normalized["location"] is not None
    assert len(normalized["company"]) <= 255
    assert len(normalized["location"]) <= 255
