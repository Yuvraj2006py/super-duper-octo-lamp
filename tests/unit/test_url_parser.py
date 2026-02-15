from app.services.url_parser import detect_platform, extract_job_payload_from_html


def test_extract_job_payload_from_html_discovers_questions_and_docs():
    html = """
    <html>
      <head>
        <title>Data Analyst Intern | Example Corp</title>
        <script id="__NEXT_DATA__" type="application/json">
          {"props":{"pageProps":{"application":{"questions":[{"questionText":"How do you handle ambiguity in analytics projects?"}]}}}}
        </script>
      </head>
      <body>
        <h1>Data Analyst Intern</h1>
        <p>Please include a cover letter and submit unofficial transcript.</p>
        <label for="q1">Why do you want this internship?</label>
        <p>Question: Describe a project where you used Python and SQL.</p>
      </body>
    </html>
    """

    payload = extract_job_payload_from_html(
        source_url="https://example.com/job/123",
        html_text=html,
        final_url="https://example.com/job/123",
        status_code=200,
        user_questions=["What excites you about this role?"],
    )

    assert payload["title"] == "Data Analyst Intern | Example Corp"
    assert "cover_letter" in payload["required_documents"]
    assert "transcript" in payload["required_documents"]
    questions = payload["application_questions"]
    assert "What excites you about this role?" in questions
    assert "Why do you want this internship?" in questions
    assert "Describe a project where you used Python and SQL." in questions
    assert any("ambiguity in analytics projects" in q for q in questions)


def test_extract_job_payload_filters_noise_labels():
    html = """
    <html>
      <body>
        <label>Cookie settings</label>
        <label>Sign in</label>
        <label>Are you legally authorized to work in Canada?</label>
      </body>
    </html>
    """

    payload = extract_job_payload_from_html(
        source_url="https://example.com/job/456",
        html_text=html,
        final_url="https://example.com/job/456",
        status_code=200,
    )

    questions = payload["application_questions"]
    assert "Are you legally authorized to work in Canada?" in questions
    assert not any("cookie" in q.lower() for q in questions)


def test_detect_platform_from_url():
    assert detect_platform("https://cibc.wd3.myworkdayjobs.com/search") == "workday"
    assert detect_platform("https://job-boards.greenhouse.io/example/jobs/123") == "greenhouse"
    assert detect_platform("https://jobs.lever.co/example/abc") == "lever"
