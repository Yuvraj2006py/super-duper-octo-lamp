from app.services.resume_pdf_parser import merge_profiles, parse_resume_text


def test_parse_resume_text_extracts_sections():
    text = (
        "Yuvraj Sharma (905) 299-9148 | yuvisha06@gmail.com | LinkedIn | GitHub "
        "EDUCATION University of Western Ontario | London, ON April 2028 (Expected) "
        "Honours Specialization in Computer Science ● Relevant Coursework: Data Structures, Databases "
        "TECHNICAL SKILLS Languages & Frameworks: Python (FastAPI, Pandas), SQL, JavaScript "
        "RELEVANT EXPERIENCE Western Developers Society London, ON Project Manager September 2025 - Present "
        "● Led cross-functional teams ● Tracked KPIs and delivery metrics "
        "WesternAI London, ON AI Developer October 2025 - Present "
        "● Engineered 75+ high-signal features "
        "PROJECTS Verse | FastAPI, Python, PostgreSQL Built an investment analytics platform "
        "● Implemented ALM forecasting with LightGBM "
    )

    profile = parse_resume_text(text)

    assert profile["personal_info"]["name"] == "Yuvraj Sharma"
    assert profile["personal_info"]["email"] == "yuvisha06@gmail.com"
    assert len(profile["education"]) >= 1
    assert len(profile["experience"]) >= 2
    assert len(profile["projects"]) >= 1
    assert "Python" in profile["skills"]
    assert any(claim["metric"] in {"75+", "2028", "2025", "75"} for claim in profile["allowed_claims"])

    first_exp = profile["experience"][0]
    assert first_exp["company"] == "Western Developers Society"
    assert first_exp["title"] == "Project Manager"
    assert first_exp["location"] == "London, ON"


def test_merge_profiles_prefers_parsed_values_and_keeps_base_fallback():
    base = {
        "personal_info": {"name": "Base Name", "email": "base@example.com", "links": ["https://base.dev"]},
        "allowed_claims": [{"claim": "Base claim", "metric": "10%", "source": "base"}],
    }
    parsed = {
        "personal_info": {"name": "Parsed Name", "email": "parsed@example.com", "links": ["LinkedIn"]},
        "summary": "Parsed summary",
        "education": [{"school": "Parsed University"}],
        "experience": [{"company": "Parsed Co", "title": "Engineer"}],
        "projects": [{"name": "Parsed Project", "description": "Desc"}],
        "skills": ["Python"],
        "achievements": ["Built thing"],
        "allowed_claims": [{"claim": "Parsed claim", "metric": "35%", "source": "parsed"}],
        "resume_source": {"pdf_path": "resume/sample.pdf"},
    }

    merged = merge_profiles(base, parsed)

    assert merged["personal_info"]["name"] == "Parsed Name"
    assert merged["personal_info"]["email"] == "parsed@example.com"
    assert merged["summary"] == "Parsed summary"
    assert merged["education"][0]["school"] == "Parsed University"
    assert merged["allowed_claims"][0]["claim"] == "Parsed claim"
    assert "LinkedIn" in merged["personal_info"]["links"]
