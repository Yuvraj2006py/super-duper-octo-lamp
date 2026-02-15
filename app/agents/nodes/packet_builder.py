from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.packet_service import build_packet_for_application


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def packet_builder_node(state: JobPipelineState) -> JobPipelineState:
        app_id = state.get("application_id")
        if not app_id:
            state.setdefault("errors", []).append("No application id available for packet build")
            return state

        application = crud.get_application(db, app_id)
        if not application:
            state.setdefault("errors", []).append("Application not found for packet build")
            return state

        allow_without_approval = bool(state.get("allow_packet_without_approval", False))
        if application.status != JobStatus.APPROVED and not allow_without_approval:
            state.setdefault("errors", []).append("Application not approved; packet build blocked")
            return state

        build_packet_for_application(db, application=application, actor_id=actor_id)
        if allow_without_approval:
            application.status = JobStatus.READY_FOR_REVIEW
            application.job.status = JobStatus.READY_FOR_REVIEW
            state["status"] = JobStatus.READY_FOR_REVIEW.value
        else:
            state["status"] = JobStatus.PACKET_BUILT.value
        db.commit()
        return state

    return packet_builder_node
