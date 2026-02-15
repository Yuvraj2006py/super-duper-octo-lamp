from app.services.writing import LLMProvider, generate_drafts


class _StaticProvider(LLMProvider):
    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, prompt: str) -> str:
        return self.text


class _FailingProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        raise RuntimeError("simulated provider failure")


def _base_profile() -> dict:
    return {
        "personal_info": {
            "name": "Alex Carter",
            "email": "alex@example.com",
            "links": ["https://github.com/alexcarter"],
        }
    }


def _base_job() -> dict:
    return {
        "title": "Senior Backend Engineer",
        "company": "Acme Analytics",
        "requires_cover_letter": True,
    }


def _chunks() -> list[dict]:
    return [
        {
            "text": "Led backend modernization to FastAPI and cut API latency by 35%.",
            "source_field": "experience[0].highlights",
            "chunk_key": "experience_0",
            "score": 0.9,
        },
        {
            "text": "Built deterministic ranking engine for candidate-role matching.",
            "source_field": "projects[0].description",
            "chunk_key": "project_0",
            "score": 0.8,
        },
    ]


def test_cover_letter_is_professional_and_signed_with_real_name():
    provider = _StaticProvider(
        "Here is a concise cover letter:\n\n"
        "Dear Hiring Manager,\n\n"
        "I led backend improvements across Python services.\n\n"
        "Sincerely,\n[Your Name]"
    )

    drafts, _ = generate_drafts(
        user_profile=_base_profile(),
        job_structured=_base_job(),
        retrieved_chunks=_chunks(),
        llm_provider=provider,
    )

    cover = drafts["cover_letter"]
    lines = cover.splitlines()
    assert lines[0] == "Alex Carter"
    assert lines[1] == "alex@example.com"
    assert "February" in lines[3]
    assert "Alex Carter" in cover
    assert "Dear Hiring Manager," in cover
    assert "Re: Senior Backend Engineer" in cover
    assert "Acme Analytics" in cover
    assert "[Your Name]" not in cover
    assert "Here is a concise cover letter" not in cover
    assert "Sincerely,\nAlex Carter" in cover


def test_cover_letter_fallback_still_produces_structured_output():
    drafts, _ = generate_drafts(
        user_profile=_base_profile(),
        job_structured=_base_job(),
        retrieved_chunks=_chunks(),
        llm_provider=_FailingProvider(),
    )

    cover = drafts["cover_letter"]
    assert "Alex Carter" in cover
    assert "Dear Hiring Manager," in cover
    assert "Sincerely,\nAlex Carter" in cover
    assert "Acme Analytics" in cover


def test_resume_context_used_when_retrieval_is_sparse():
    sparse_chunks = [
        {
            "text": "Python, FastAPI, PostgreSQL",
            "source_field": "skills",
            "chunk_key": "skills",
            "score": 0.5,
        }
    ]
    profile = {
        "personal_info": {
            "name": "Alex Carter",
            "email": "alex@example.com",
            "links": ["https://github.com/alexcarter"],
        },
        "summary": "Senior backend engineer focused on platform reliability.",
        "experience": [
            {
                "title": "Senior Software Engineer",
                "company": "Northwind Labs",
                "highlights": "Reduced API latency by 35% after migrating critical services to FastAPI.",
            }
        ],
        "projects": [
            {
                "name": "Audit Trail Platform",
                "description": "Built append-only audit logging with review checkpoints.",
            }
        ],
    }

    drafts, _ = generate_drafts(
        user_profile=profile,
        job_structured=_base_job(),
        retrieved_chunks=sparse_chunks,
        llm_provider=_FailingProvider(),
    )

    cover = drafts["cover_letter"]
    assert "Northwind Labs" in cover
    assert "FastAPI" in cover
    assert "Audit Trail Platform" in cover


def test_internship_mode_enforces_student_tone_and_avoids_senior_language():
    provider = _StaticProvider(
        "As a seasoned engineer, I am a senior backend engineer with years of production experience.\n\n"
        "I have led large teams and shipped critical systems.\n\n"
        "I am excited to apply."
    )
    profile = {
        "personal_info": {
            "name": "Alex Carter",
            "email": "alex@example.com",
            "links": ["https://github.com/alexcarter"],
        },
        "education": [
            {
                "school": "University of Washington",
                "degree": "B.S. Computer Science",
                "year": "2028",
                "gpa": "3.8/4.0",
            }
        ],
        "internship_preferences": {"target_internships_only": True},
    }

    drafts, _ = generate_drafts(
        user_profile=profile,
        job_structured={
            "title": "Software Engineering Intern",
            "company": "Acme Analytics",
            "requires_cover_letter": True,
        },
        retrieved_chunks=_chunks(),
        llm_provider=provider,
    )

    cover = drafts["cover_letter"].lower()
    assert "seasoned" not in cover
    assert "i am a senior" not in cover
    assert "senior backend engineer" not in cover
    assert "student" in cover
    assert "gpa 3.8/4.0" in cover


def test_cover_letter_not_generated_when_not_required():
    drafts, _ = generate_drafts(
        user_profile=_base_profile(),
        job_structured={
            "title": "Software Engineering Intern",
            "company": "Acme Analytics",
            "requires_cover_letter": False,
        },
        retrieved_chunks=_chunks(),
        llm_provider=_FailingProvider(),
    )

    assert drafts["cover_letter"] == ""


def test_application_questions_are_answered_when_present():
    drafts, _ = generate_drafts(
        user_profile=_base_profile(),
        job_structured={
            "title": "Software Engineering Intern",
            "company": "Acme Analytics",
            "requires_cover_letter": False,
            "application_questions": [
                "Why are you interested in this internship?",
                "Describe a project where you used Python.",
            ],
        },
        retrieved_chunks=_chunks(),
        llm_provider=_FailingProvider(),
    )

    short_answers = drafts["short_answers"]
    assert "why_are_you_interested_in_this_internship" in short_answers
    assert "describe_a_project_where_you_used_python" in short_answers
    assert all(answer.strip() for answer in short_answers.values())


def test_no_application_questions_produces_no_short_answers():
    drafts, _ = generate_drafts(
        user_profile=_base_profile(),
        job_structured={
            "title": "Software Engineering Intern",
            "company": "Acme Analytics",
            "requires_cover_letter": False,
            "application_questions": [],
        },
        retrieved_chunks=_chunks(),
        llm_provider=_FailingProvider(),
    )

    assert drafts["short_answers"] == {}
    assert drafts["question_answer_pairs"] == []


def test_authorization_question_uses_deterministic_profile_answer():
    profile = _base_profile()
    profile["internship_preferences"] = {
        "work_authorization": {
            "us_authorized": True,
            "canada_authorized": True,
            "requires_sponsorship_us": False,
            "requires_sponsorship_canada": False,
        }
    }

    drafts, _ = generate_drafts(
        user_profile=profile,
        job_structured={
            "title": "Data Analyst Intern",
            "company": "Acme Analytics",
            "requires_cover_letter": False,
            "application_questions": ["Are you legally authorized to work in Canada?"],
        },
        retrieved_chunks=_chunks(),
        llm_provider=_FailingProvider(),
    )

    answer = drafts["short_answers"]["are_you_legally_authorized_to_work_in_canada"]
    assert "authorized to work in Canada" in answer
    assert "do not require sponsorship" in answer
