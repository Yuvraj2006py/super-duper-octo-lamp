from typing import Any, TypedDict


class JobPipelineState(TypedDict, total=False):
    run_id: str
    job_id: str
    application_id: str
    user_id: str
    actor_id: str

    job_raw: dict[str, Any]
    job_structured: dict[str, Any]

    score: float
    score_breakdown: dict[str, float]

    retrieved_profile_chunks: list[dict[str, Any]]
    drafts: dict[str, Any]
    claims_table: list[dict[str, Any]]

    verification_report: dict[str, Any]
    status: str
    errors: list[str]
    allow_packet_without_approval: bool

    manual_decision: str
    auto_packet: bool
