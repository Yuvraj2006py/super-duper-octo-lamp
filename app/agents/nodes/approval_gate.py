from datetime import datetime, timezone
from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.audit import audit_event


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def approval_gate_node(state: JobPipelineState) -> JobPipelineState:
        job = crud.get_job(db, state["job_id"])
        user = crud.get_single_user(db)
        if not job or not user:
            state.setdefault("errors", []).append("Missing job/user in approval gate")
            return state

        application = crud.get_or_create_application(db, user_id=str(user.id), job_id=str(job.id))

        if not application.verification_passed:
            state["status"] = application.status.value
            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="auto_approval_blocked",
                entity_type="application",
                entity_id=str(application.id),
                payload={"status": state["status"], "reason": "verification_failed"},
            )
            db.commit()
            return state

        application.status = JobStatus.APPROVED
        application.approved_by = actor_id
        application.approved_at = datetime.now(timezone.utc)
        job.status = JobStatus.APPROVED
        state["status"] = JobStatus.APPROVED.value

        state["application_id"] = str(application.id)

        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="auto_approved",
            entity_type="application",
            entity_id=str(application.id),
            payload={"status": state["status"], "decision": "AUTO_APPROVE"},
        )
        db.commit()
        return state

    return approval_gate_node
