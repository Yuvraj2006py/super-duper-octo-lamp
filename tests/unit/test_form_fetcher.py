from app.services.form_fetcher import normalize_form_capture


def test_normalize_form_capture_includes_fields_and_scripts():
    fields = [
        {
            "tag": "input",
            "type": "text",
            "id": "firstName",
            "name": "firstName",
            "label": "First Name",
            "required": True,
            "placeholder": "",
            "ariaLabel": "",
        },
        {
            "tag": "select",
            "type": "select",
            "id": "schoolYear",
            "name": "schoolYear",
            "label": "What year are you in university?",
            "required": False,
            "options": ["1st", "2nd", "3rd"],
        },
    ]
    scripts = [
        {
            "source": "__NEXT_DATA__",
            "text": '{"questions":[{"questionText":"What is your GPA?"}]}'
        }
    ]

    normalized = normalize_form_capture(platform="workday", fields=fields, scripts=scripts)

    assert len(normalized) == 3
    assert normalized[0]["field_key"].startswith("form_firstname")
    assert normalized[0]["required"] is True
    assert normalized[0]["platform"] == "workday"

    assert normalized[1]["label"] == "What year are you in university?"
    assert normalized[1]["type"] == "select"

    script_rows = [row for row in normalized if row["type"] == "script_json"]
    assert len(script_rows) == 1
    prompts = script_rows[0]["metadata"].get("prompt_candidates") or []
    assert "What is your GPA?" in prompts


def test_normalize_form_capture_dedupes_duplicate_keys():
    fields = [
        {"name": "email", "label": "Email", "type": "email", "required": True},
        {"name": "email", "label": "Email Address", "type": "email", "required": True},
    ]

    normalized = normalize_form_capture(platform="workday", fields=fields, scripts=[])

    # Suffix index in the key keeps entries unique while preserving the source name.
    assert len(normalized) == 2
    assert normalized[0]["field_key"] != normalized[1]["field_key"]
