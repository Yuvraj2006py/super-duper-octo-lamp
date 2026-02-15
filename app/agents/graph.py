import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents.nodes import (
    approval_gate,
    auto_fill_executor,
    fit_scorer,
    packet_builder,
    parser_normalizer,
    scout,
    tracker,
    verifier,
    writer,
)
from app.agents.state import JobPipelineState


def _route_after_approval(state: JobPipelineState) -> str:
    if state.get("status") == "APPROVED":
        return "auto_fill_executor"
    return "tracker"


def _route_after_scoring(state: JobPipelineState) -> str:
    if state.get("status") == "CLOSED":
        return "tracker"
    return "writer"


def _route_after_parser(state: JobPipelineState) -> str:
    if state.get("status") == "CLOSED":
        return "tracker"
    return "scorer"


def _route_after_auto_fill(state: JobPipelineState) -> str:
    if state.get("status") == "SUBMITTED":
        return "tracker"
    return "packet_builder"


def build_pipeline(db: Session, actor_id: str, embedding_provider, llm_provider):
    graph = StateGraph(JobPipelineState)

    graph.add_node("scout", scout.make_node(db, actor_id))
    graph.add_node("parser", parser_normalizer.make_node(db, actor_id))
    graph.add_node("scorer", fit_scorer.make_node(db, actor_id, embedding_provider))
    graph.add_node("writer", writer.make_node(db, actor_id, embedding_provider, llm_provider))
    graph.add_node("verifier", verifier.make_node(db, actor_id))
    graph.add_node("approval_gate", approval_gate.make_node(db, actor_id))
    graph.add_node("auto_fill_executor", auto_fill_executor.make_node(db, actor_id))
    graph.add_node("packet_builder", packet_builder.make_node(db, actor_id))
    graph.add_node("tracker", tracker.make_node(db, actor_id))

    graph.set_entry_point("scout")
    graph.add_edge("scout", "parser")
    graph.add_conditional_edges(
        "parser",
        _route_after_parser,
        {
            "scorer": "scorer",
            "tracker": "tracker",
        },
    )
    graph.add_conditional_edges(
        "scorer",
        _route_after_scoring,
        {
            "writer": "writer",
            "tracker": "tracker",
        },
    )
    graph.add_edge("writer", "verifier")
    graph.add_edge("verifier", "approval_gate")
    graph.add_conditional_edges(
        "approval_gate",
        _route_after_approval,
        {
            "auto_fill_executor": "auto_fill_executor",
            "tracker": "tracker",
        },
    )
    graph.add_conditional_edges(
        "auto_fill_executor",
        _route_after_auto_fill,
        {
            "packet_builder": "packet_builder",
            "tracker": "tracker",
        },
    )
    graph.add_edge("packet_builder", "tracker")
    graph.add_edge("tracker", END)

    return graph.compile()


def run_pipeline_for_job(
    db: Session,
    *,
    job_id: str,
    user_id: str,
    actor_id: str,
    embedding_provider,
    llm_provider,
    manual_decision: str | None = None,
    auto_packet: bool = False,
) -> JobPipelineState:
    app = build_pipeline(db, actor_id, embedding_provider, llm_provider)
    initial_state: JobPipelineState = {
        "run_id": str(uuid.uuid4()),
        "job_id": str(job_id),
        "user_id": str(user_id),
        "actor_id": actor_id,
        "errors": [],
        "manual_decision": manual_decision or "AUTO_APPROVE",
        "auto_packet": bool(auto_packet),
    }
    return app.invoke(initial_state)
