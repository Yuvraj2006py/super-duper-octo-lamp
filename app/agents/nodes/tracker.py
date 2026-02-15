from typing import Callable

from app.agents.state import JobPipelineState
from app.services.audit import audit_event


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def tracker_node(state: JobPipelineState) -> JobPipelineState:
        app_id = state.get("application_id") or "unknown"
        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="tracker_updated",
            entity_type="application",
            entity_id=app_id,
            payload={"status": state.get("status"), "run_id": state.get("run_id")},
        )
        db.commit()
        return state

    return tracker_node
