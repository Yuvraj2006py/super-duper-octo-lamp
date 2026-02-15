from typing import Callable

from app.agents.state import JobPipelineState
from app.services.audit import audit_event


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def scout_node(state: JobPipelineState) -> JobPipelineState:
        # Scout is handled by ingestion adapters; this node records pipeline entry.
        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="scout_node_entered",
            entity_type="job",
            entity_id=state["job_id"],
            payload={"run_id": state.get("run_id")},
        )
        db.commit()
        return state

    return scout_node
