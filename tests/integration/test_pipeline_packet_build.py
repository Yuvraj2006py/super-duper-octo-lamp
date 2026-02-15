from types import SimpleNamespace

from app.agents.graph import run_pipeline_for_job
from app.core.config import get_settings
from app.core.enums import JobStatus
from app.services.embeddings import MockEmbeddingProvider
from app.services.writing import MockLLMProvider


class FakeDB:
    def __init__(self):
        self.events = []

    def add(self, obj):
        self.events.append(("add", obj))

    def flush(self):
        return None

    def commit(self):
        return None


def _setup(monkeypatch):
    settings = get_settings()
    db = FakeDB()

    user = SimpleNamespace(
        id="user-1",
        email="alex@example.com",
        full_name="Alex Carter",
        profile_json={
            "summary": "Senior backend engineer",
            "skills": ["python", "fastapi", "postgresql", "redis", "celery"],
            "experience": [
                {
                    "company": "Northwind Labs",
                    "title": "Senior Software Engineer",
                    "start_date": "2022-01",
                    "end_date": "2025-12",
                    "highlights": "Reduced API latency by 35%",
                }
            ],
            "projects": [{"name": "Audit Trail", "description": "Built append-only audit logs"}],
            "allowed_claims": [{"claim": "Reduced API latency by 35%", "metric": "35%"}],
        },
    )

    job = SimpleNamespace(
        id="job-1",
        url="https://example.com/jobs/1/apply",
        platform="workday",
        raw_text=(
            "Title: Senior Backend Engineer\n"
            "Company: Acme Analytics\n"
            "Location: Remote\n"
            "- Build Python microservices\n"
            "- Experience with FastAPI and PostgreSQL\n"
        ),
        raw_payload={
            "title": "Senior Backend Engineer",
            "company": "Acme Analytics",
            "location": "Remote",
            "requirements": ["FastAPI", "PostgreSQL", "Redis"],
            "must_have": ["FastAPI", "PostgreSQL"],
        },
        posted_at=None,
        title=None,
        company=None,
        location=None,
        seniority=None,
        score_total=None,
        score_breakdown=None,
        status=JobStatus.DISCOVERED,
    )

    application = SimpleNamespace(
        id="app-1",
        user_id=user.id,
        job_id=job.id,
        status=JobStatus.DISCOVERED,
        verification_passed=None,
        verification_report=None,
        claims_table=None,
        approved_by=None,
        approved_at=None,
        rejection_reason=None,
        user=user,
        job=job,
    )
    job.application = application

    provider = MockEmbeddingProvider(dim=settings.embedding_dim)
    emb_vectors = provider.embed_texts(
        [
            "Senior Software Engineer at Northwind Labs: Reduced API latency by 35%",
            "Skills: python, fastapi, postgresql, redis, celery",
        ]
    )
    embeddings = [
        SimpleNamespace(
            entity_id=user.id,
            model_name=settings.embedding_model_name,
            chunk_key="experience_1",
            metadata={
                "text": "Senior Software Engineer at Northwind Labs: Reduced API latency by 35%",
                "source_field": "experience[0]",
            },
            vector=emb_vectors[0],
        ),
        SimpleNamespace(
            entity_id=user.id,
            model_name=settings.embedding_model_name,
            chunk_key="skills",
            metadata={
                "text": "Skills: python, fastapi, postgresql, redis, celery",
                "source_field": "skills",
            },
            vector=emb_vectors[1],
        ),
    ]

    def fake_get_job(_db, job_id):
        return job if str(job.id) == str(job_id) else None

    def fake_get_user(_db):
        return user

    def fake_get_or_create_application(_db, user_id, job_id):
        return application

    def fake_get_application(_db, application_id):
        return application if str(application.id) == str(application_id) else None

    def fake_list_embeddings(_db, entity_type):
        assert entity_type == "profile_chunk"
        return embeddings

    def fake_audit_event(_db, **kwargs):
        db.events.append(kwargs)
        return SimpleNamespace(id=len(db.events), **kwargs)

    def fake_build_packet(_db, application, actor_id):
        application.status = JobStatus.PACKET_BUILT
        application.job.status = JobStatus.PACKET_BUILT
        return {
            "RESUME_DOCX": f"/output/{application.job_id}/resume.docx",
            "COVER_LETTER_DOCX": f"/output/{application.job_id}/cover_letter.docx",
        }

    monkeypatch.setattr("app.db.crud.get_job", fake_get_job)
    monkeypatch.setattr("app.db.crud.get_single_user", fake_get_user)
    monkeypatch.setattr("app.db.crud.get_or_create_application", fake_get_or_create_application)
    monkeypatch.setattr("app.db.crud.get_application", fake_get_application)
    monkeypatch.setattr("app.db.crud.list_embeddings", fake_list_embeddings)

    monkeypatch.setattr("app.agents.nodes.scout.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.parser_normalizer.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.fit_scorer.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.writer.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.verifier.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.approval_gate.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.auto_fill_executor.audit_event", fake_audit_event)
    monkeypatch.setattr("app.agents.nodes.tracker.audit_event", fake_audit_event)

    monkeypatch.setattr("app.agents.nodes.packet_builder.build_packet_for_application", fake_build_packet)

    return db, user, job, application, provider


def test_pipeline_reaches_ready_for_review_when_submission_is_dry_run(monkeypatch):
    db, user, job, application, provider = _setup(monkeypatch)

    state = run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    # Safety default: we don't auto-submit in tests; the pipeline should produce a reviewable packet.
    assert state["status"] == JobStatus.READY_FOR_REVIEW.value
    assert application.status == JobStatus.READY_FOR_REVIEW
    assert application.verification_passed is True


def test_pipeline_second_run_remains_ready_for_review(monkeypatch):
    db, user, job, application, provider = _setup(monkeypatch)

    run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    state = run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    assert state["status"] == JobStatus.READY_FOR_REVIEW.value
    assert application.status == JobStatus.READY_FOR_REVIEW


def test_pipeline_reject_path_and_audit(monkeypatch):
    db, user, job, application, provider = _setup(monkeypatch)
    monkeypatch.setattr(
        "app.agents.nodes.verifier.verify_drafts",
        lambda **kwargs: {
            "passed": False,
            "reasons": ["forced verification failure"],
            "checks": {},
            "claims_checked": 0,
        },
    )

    state = run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    assert state["status"] == JobStatus.DRAFTED.value
    assert application.status == JobStatus.DRAFTED
    actions = [event["action"] for event in db.events if "action" in event]
    assert "job_parsed" in actions
    assert "job_scored" in actions
    assert "draft_generated" in actions
    assert "verification_completed" in actions
    assert "auto_approval_blocked" in actions


def test_pipeline_filters_non_internship_when_internship_mode_enabled(monkeypatch):
    db, user, job, application, provider = _setup(monkeypatch)
    user.profile_json["internship_preferences"] = {
        "target_internships_only": True,
        "all_tech_roles": True,
        "target_role_families": ["data", "ml", "backend", "software"],
    }
    job.raw_payload["title"] = "Senior Backend Engineer"
    job.raw_payload["seniority"] = "senior"
    job.raw_text = (
        "Title: Senior Backend Engineer\n"
        "Company: Acme Analytics\n"
        "Location: Remote\n"
        "- Build Python microservices\n"
        "- Experience with FastAPI and PostgreSQL\n"
    )

    state = run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    assert state["status"] == JobStatus.CLOSED.value
    assert "internship-only targeting enabled" in " ".join(state.get("errors", []))
    actions = [event["action"] for event in db.events if "action" in event]
    assert "job_filtered" in actions


def test_pipeline_closes_unavailable_posting_before_scoring(monkeypatch):
    db, user, job, application, provider = _setup(monkeypatch)
    job.raw_text = "The job you're looking for is no longer available."
    job.raw_payload = {"title": "Derivative Ops Analyst Intern"}

    state = run_pipeline_for_job(
        db,
        job_id=job.id,
        user_id=user.id,
        actor_id=user.id,
        embedding_provider=provider,
        llm_provider=MockLLMProvider(),
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )

    assert state["status"] == JobStatus.CLOSED.value
    assert "inactive posting" in " ".join(state.get("errors", [])).lower()
    actions = [event["action"] for event in db.events if "action" in event]
    assert "job_filtered" in actions
    assert "job_scored" not in actions
