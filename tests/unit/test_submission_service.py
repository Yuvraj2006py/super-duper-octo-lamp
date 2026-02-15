from pathlib import Path
from types import SimpleNamespace

from app.services import form_submission_service as submission


def _field(field_key: str, label: str, required: bool = True, field_type: str = "text"):
    return SimpleNamespace(
        field_key=field_key,
        label=label,
        required=required,
        type=field_type,
        metadata_json={"name": field_key},
    )


def test_build_field_payload_prefers_general_meta_answers():
    fields = [
        _field("university_year", "What university year are you in?"),
        _field("gpa", "What is your GPA?"),
        _field("availability", "What is your internship availability?"),
        _field("work_auth_ca", "Are you authorized to work in Canada?"),
        _field("work_auth_us", "Are you authorized to work in the US?"),
    ]
    payload = submission.build_field_payload(
        form_fields=fields,
        drafts={},
        user_profile={
            "general_meta": {
                "university_year": "2nd year",
                "gpa": "3.6/4.0",
                "availability_terms": ["Summer 2026", "Fall 2026"],
                "work_authorization": {
                    "canada_authorized": True,
                    "us_authorized": True,
                    "requires_sponsorship_canada": False,
                    "requires_sponsorship_us": False,
                },
            }
        },
    )

    values = {item["field_key"]: item for item in payload}
    assert values["university_year"]["value"] == "2nd year"
    assert values["university_year"]["source"] == "general_meta.university_year"
    assert values["gpa"]["value"] == "3.6/4.0"
    assert values["availability"]["value"] == "Summer 2026, Fall 2026"
    assert "authorized to work in Canada" in values["work_auth_ca"]["value"]
    assert "do not require sponsorship" in values["work_auth_ca"]["value"]
    assert "authorized to work in the United States" in values["work_auth_us"]["value"]

def test_build_field_payload_maps_workday_login_and_skips_honeypot():
    fields = [
        _field("email", "Email Address*", required=True, field_type="text"),
        _field("password", "Password*", required=True, field_type="password"),
        _field("website", "Enter website. This input is for robots only, do not enter if you're human.", required=False, field_type="text"),
    ]
    payload = submission.build_field_payload(
        form_fields=fields,
        drafts={},
        user_profile={"personal_info": {"email": "student@example.com"}},
    )

    items = {item["field_key"]: item for item in payload}
    assert items["email"]["value"] == "student@example.com"
    assert items["email"]["source"] == "profile.personal_info.email"

    assert items["password"]["value"] == "<redacted>"
    assert items["password"]["runtime_value_env"] == "WORKDAY_PASSWORD"
    assert items["password"]["source"] == "secret.env.WORKDAY_PASSWORD"
    assert items["password"]["metadata"]["sensitive"] is True

    assert items["website"]["value"] == ""
    assert items["website"]["source"] == "honeypot.skip"


def test_build_field_payload_uses_drafts_when_meta_missing():
    fields = [_field("why", "Why are you interested in this internship?", required=True)]
    payload = submission.build_field_payload(
        form_fields=fields,
        drafts={
            "question_answer_pairs": [
                {
                    "question": "Why are you interested in this internship?",
                    "answer": "I want to apply data and ML fundamentals in production.",
                }
            ]
        },
        user_profile={},
    )

    assert payload[0]["value"] == "I want to apply data and ML fundamentals in production."
    assert payload[0]["source"] == "draft.question_answer_pairs"


def test_perform_submission_mock_detects_captcha_and_blocks():
    result = submission.perform_submission(
        url="https://example.com/apply",
        payload=[{"label": "Please complete CAPTCHA", "value": "", "required": True}],
        mode="mock",
        retries=3,
        dry_run=False,
        storage_state_path=Path("secrets/workday_state.json"),
        timeout_ms=1000,
        wait_ms=50,
        headless=True,
    )
    assert result["status"] == "blocked"
    assert result["attempts"] == 1


def test_perform_submission_retries_until_success(monkeypatch):
    calls = {"count": 0}

    def fake_submit(**kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            return {
                "status": "failed",
                "reason": "timeout",
                "response_url": kwargs["url"],
                "filled_count": 1,
            }
        return {
            "status": "submitted",
            "reason": None,
            "response_url": kwargs["url"],
            "filled_count": 1,
        }

    monkeypatch.setattr(submission, "submit_with_playwright", fake_submit)

    result = submission.perform_submission(
        url="https://example.com/apply",
        payload=[{"label": "Email", "value": "alex@example.com", "required": True}],
        mode="playwright",
        retries=2,
        dry_run=False,
        storage_state_path=Path("secrets/workday_state.json"),
        timeout_ms=1000,
        wait_ms=50,
        headless=True,
    )

    assert calls["count"] == 2
    assert result["status"] == "submitted"
    assert result["attempts"] == 2
