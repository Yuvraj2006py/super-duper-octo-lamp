from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.audit import audit_event
from app.services.scoring import compute_fit_score


def make_node(db, actor_id: str, embedding_provider) -> Callable[[JobPipelineState], JobPipelineState]:
    def scorer_node(state: JobPipelineState) -> JobPipelineState:
        job = crud.get_job(db, state["job_id"])
        user = crud.get_single_user(db)
        if not job or not user:
            state.setdefault("errors", []).append("Missing job or user for scoring")
            return state

        total, breakdown = compute_fit_score(
            user_profile=user.profile_json,
            job_structured=state.get("job_structured", {}),
            job_raw_text=job.raw_text,
            embedding_provider=embedding_provider,
        )

        internship_prefs = (user.profile_json or {}).get("internship_preferences", {}) or {}
        internship_only = bool(internship_prefs.get("target_internships_only", False))
        internship_fit = float(breakdown.get("internship_role_fit", 1.0))
        if internship_only and internship_fit < 0.5:
            job.score_total = total
            job.score_breakdown = breakdown
            job.status = JobStatus.CLOSED
            state["score"] = total
            state["score_breakdown"] = breakdown
            state["status"] = JobStatus.CLOSED.value
            state.setdefault("errors", []).append(
                "Filtered: internship-only targeting enabled and job did not match internship terms"
            )

            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="job_filtered",
                entity_type="job",
                entity_id=str(job.id),
                payload={
                    "reason": "internship_only_non_match",
                    "internship_role_fit": internship_fit,
                    "score": total,
                },
            )
            db.commit()
            return state

        job.score_total = total
        job.score_breakdown = breakdown
        job.status = JobStatus.SCORED

        state["score"] = total
        state["score_breakdown"] = breakdown
        state["status"] = JobStatus.SCORED.value

        audit_event(
            db,
            actor_type="agent",
            actor_id=actor_id,
            action="job_scored",
            entity_type="job",
            entity_id=str(job.id),
            payload={"score": total, "breakdown": breakdown},
        )
        db.commit()
        return state

    return scorer_node
