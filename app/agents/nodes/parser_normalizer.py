from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.audit import audit_event
from app.services.parsing import normalize_job


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def parser_node(state: JobPipelineState) -> JobPipelineState:
        job = crud.get_job(db, state["job_id"])
        if not job:
            state.setdefault("errors", []).append("Job not found")
            return state

        structured = normalize_job(job.raw_text, job.raw_payload or {})
        if job.posted_at:
            structured["posted_at"] = job.posted_at.isoformat()

        job.title = structured.get("title")
        job.company = structured.get("company")
        job.location = structured.get("location")
        job.seniority = structured.get("seniority")
        payload = dict(job.raw_payload or {})
        payload["structured"] = structured
        job.raw_payload = payload
        state["job_structured"] = structured

        if not structured.get("posting_active", True):
            reason = structured.get("posting_inactive_reason") or "posting marked inactive"
            job.status = JobStatus.CLOSED
            state["status"] = JobStatus.CLOSED.value
            state.setdefault("errors", []).append(f"Filtered: inactive posting ({reason})")

            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="job_filtered",
                entity_type="job",
                entity_id=str(job.id),
                payload={
                    "reason": "posting_inactive",
                    "detail": reason,
                },
            )
            db.commit()
            return state

        job.status = JobStatus.PARSED
        state["status"] = JobStatus.PARSED.value

        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="job_parsed",
            entity_type="job",
            entity_id=str(job.id),
            payload={"structured_fields": ["title", "company", "location", "seniority"]},
        )
        db.commit()
        return state

    return parser_node
