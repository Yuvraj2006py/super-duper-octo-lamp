from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.audit import audit_event
from app.services.verification import verify_drafts


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def verifier_node(state: JobPipelineState) -> JobPipelineState:
        user = crud.get_single_user(db)
        job = crud.get_job(db, state["job_id"])
        if not user or not job:
            state.setdefault("errors", []).append("Missing user/job for verification")
            return state

        application = crud.get_or_create_application(db, user_id=str(user.id), job_id=str(job.id))
        drafts = state.get("drafts") or (job.raw_payload or {}).get("drafts", {})
        claims_table = state.get("claims_table") or application.claims_table or []

        report = verify_drafts(
            user_profile=user.profile_json,
            drafts=drafts,
            claims_table=claims_table,
            job_structured=state.get("job_structured")
            or {
                "company": job.company,
                "title": job.title,
            },
        )

        application.verification_passed = report["passed"]
        application.verification_report = report

        if report["passed"]:
            application.status = JobStatus.VERIFIED
            job.status = JobStatus.VERIFIED
            state["status"] = JobStatus.VERIFIED.value
        else:
            application.status = JobStatus.DRAFTED
            job.status = JobStatus.DRAFTED
            state["status"] = JobStatus.DRAFTED.value
            state.setdefault("errors", []).extend(report["reasons"])

        state["verification_report"] = report

        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="verification_completed",
            entity_type="application",
            entity_id=str(application.id),
            payload={"passed": report["passed"], "reasons": report["reasons"]},
        )
        db.commit()
        return state

    return verifier_node
