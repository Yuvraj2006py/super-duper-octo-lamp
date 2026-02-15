from sqlalchemy import func, select

from app.agents.graph import run_pipeline_for_job
from app.core.config import get_settings
from app.core.enums import JobStatus
from app.db import crud
from app.db.models import Application, Job
from app.db.session import SessionLocal
from app.services.audit import audit_event
from app.services.embeddings import build_embedding_provider
from app.services.packet_service import build_packet_for_application
from app.services.writing import build_llm_provider
from app.workers.celery_app import celery


def run_pipeline_batch_sync(
    *,
    top_n: int,
    status_filter: str,
    actor_id: str,
    manual_decision: str | None = "AUTO_APPROVE",
    auto_packet: bool = True,
) -> list[dict]:
    db = SessionLocal()
    try:
        settings = get_settings()
        user = crud.get_single_user(db)
        if not user:
            return []

        status = JobStatus(status_filter)
        stmt = (
            select(Job)
            .where(Job.status == status)
            .order_by(Job.posted_at.desc().nullslast(), Job.created_at.desc())
            .limit(top_n)
        )
        jobs = list(db.scalars(stmt))

        embedder = build_embedding_provider()
        llm = build_llm_provider(settings)
        results = []

        profile_prefs = (user.profile_json or {}).get("internship_preferences", {}) or {}
        max_per_company = int(
            profile_prefs.get("max_applications_per_company", settings.max_applications_per_company)
        )
        batch_company_counts: dict[str, int] = {}

        for job in jobs:
            company_raw = (
                (job.company or "")
                or str((job.raw_payload or {}).get("company") or "")
                or "unknown-company"
            )
            company_key = company_raw.strip().lower() or "unknown-company"

            existing_count = db.scalar(
                select(func.count(Application.id))
                .join(Job, Job.id == Application.job_id)
                .where(Application.user_id == user.id)
                .where(func.lower(func.coalesce(Job.company, "")) == company_key)
                .where(Application.status != JobStatus.CLOSED)
            ) or 0

            projected_count = int(existing_count) + batch_company_counts.get(company_key, 0)
            if max_per_company > 0 and projected_count >= max_per_company:
                audit_event(
                    db,
                    actor_type="worker",
                    actor_id=actor_id,
                    action="pipeline_job_skipped_company_limit",
                    entity_type="job",
                    entity_id=str(job.id),
                    payload={
                        "company": company_raw,
                        "limit": max_per_company,
                        "existing_count": int(existing_count),
                    },
                )
                results.append(
                    {
                        "job_id": str(job.id),
                        "status": "SKIPPED_COMPANY_LIMIT",
                        "errors": [f"Skipped: max applications reached for company '{company_raw}'"],
                    }
                )
                continue

            state = run_pipeline_for_job(
                db,
                job_id=str(job.id),
                user_id=str(user.id),
                actor_id=actor_id,
                embedding_provider=embedder,
                llm_provider=llm,
                manual_decision=manual_decision or "AUTO_APPROVE",
                auto_packet=True,
            )
            results.append(dict(state))
            batch_company_counts[company_key] = batch_company_counts.get(company_key, 0) + 1
        db.commit()
        return results
    finally:
        db.close()


@celery.task(name="app.workers.tasks.run_pipeline_batch")
def run_pipeline_batch(top_n: int = 3, status_filter: str = "DISCOVERED", actor_id: str = "worker"):
    return run_pipeline_batch_sync(
        top_n=top_n,
        status_filter=status_filter,
        actor_id=actor_id,
        manual_decision="AUTO_APPROVE",
        auto_packet=True,
    )


@celery.task(name="app.workers.tasks.build_packet")
def build_packet(application_id: str, actor_id: str = "worker"):
    db = SessionLocal()
    try:
        app = crud.get_application(db, application_id)
        if not app:
            return {"ok": False, "error": "Application not found"}
        if app.status != JobStatus.APPROVED:
            return {"ok": False, "error": "Application not approved"}
        artifacts = build_packet_for_application(db, application=app, actor_id=actor_id)
        db.commit()
        return {"ok": True, "artifacts": artifacts}
    finally:
        db.close()


@celery.task(name="app.workers.tasks.ingest_rss_sources")
def ingest_rss_sources():
    # MVP: placeholder schedule. Real source list/sync policy should be configured by user.
    return {"ok": True, "message": "No scheduled RSS sources configured"}
