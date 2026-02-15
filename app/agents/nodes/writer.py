from typing import Callable

from app.agents.state import JobPipelineState
from app.core.config import get_settings
from app.core.enums import JobStatus
from app.core.rate_limit import rate_limiter
from app.db import crud
from app.services.audit import audit_event
from app.services.retrieval import retrieve_profile_chunks_for_job
from app.services.writing import generate_drafts


def make_node(db, actor_id: str, embedding_provider, llm_provider) -> Callable[[JobPipelineState], JobPipelineState]:
    settings = get_settings()

    def writer_node(state: JobPipelineState) -> JobPipelineState:
        key = f"draft:{state.get('user_id', 'unknown')}"
        allowed = rate_limiter.allow(
            key,
            settings.drafting_rate_limit,
            settings.rate_limit_window_seconds,
        )
        if not allowed:
            state.setdefault("errors", []).append("Drafting rate limit exceeded")
            return state

        job = crud.get_job(db, state["job_id"])
        user = crud.get_single_user(db)
        if not job or not user:
            state.setdefault("errors", []).append("Missing job or user for writer")
            return state

        retrieved_chunks = retrieve_profile_chunks_for_job(
            db,
            user=user,
            job_text=job.raw_text,
            embedding_provider=embedding_provider,
            top_k=8,
        )

        drafts, claims_table = generate_drafts(
            user_profile=user.profile_json,
            job_structured=state.get("job_structured", {}),
            retrieved_chunks=retrieved_chunks,
            llm_provider=llm_provider,
        )

        payload = dict(job.raw_payload or {})
        payload["drafts"] = drafts
        job.raw_payload = payload
        job.status = JobStatus.DRAFTED

        application = crud.get_or_create_application(db, user_id=str(user.id), job_id=str(job.id))
        application.status = JobStatus.DRAFTED
        application.claims_table = claims_table

        state["application_id"] = str(application.id)
        state["retrieved_profile_chunks"] = retrieved_chunks
        state["drafts"] = drafts
        state["claims_table"] = claims_table
        state["status"] = JobStatus.DRAFTED.value

        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="draft_generated",
            entity_type="application",
            entity_id=str(application.id),
            payload={"claims_count": len(claims_table)},
        )
        db.commit()
        return state

    return writer_node
