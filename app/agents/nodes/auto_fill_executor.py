from typing import Callable

from app.agents.state import JobPipelineState
from app.core.enums import JobStatus
from app.db import crud
from app.services.audit import audit_event
from app.services.form_fetcher import fetch_and_store_job_form_fields
from app.services.form_submission_service import (
    build_field_payload,
    default_submission_config,
    now_utc,
    perform_submission,
)


def make_node(db, actor_id: str) -> Callable[[JobPipelineState], JobPipelineState]:
    def auto_fill_node(state: JobPipelineState) -> JobPipelineState:
        app_id = state.get("application_id")
        if not app_id:
            state.setdefault("errors", []).append("No application id available for auto fill")
            state["status"] = JobStatus.READY_FOR_REVIEW.value
            state["allow_packet_without_approval"] = True
            return state

        application = crud.get_application(db, app_id)
        job = crud.get_job(db, state.get("job_id", ""))
        user = crud.get_single_user(db)
        if not application or not job or not user:
            state.setdefault("errors", []).append("Missing job/application/user for auto fill")
            state["status"] = JobStatus.READY_FOR_REVIEW.value
            state["allow_packet_without_approval"] = True
            return state

        form_fields = []
        try:
            form_fields = crud.list_application_form_fields(db, job_id=str(job.id))
        except Exception:
            form_fields = []

        job_url = str(getattr(job, "url", "") or "").strip()
        job_platform = str(getattr(job, "platform", "") or "").strip() or "generic"
        job_raw_payload = getattr(job, "raw_payload", {}) or {}

        if not form_fields and job_url:
            try:
                fetch_and_store_job_form_fields(db, job=job, actor_id=actor_id)
                form_fields = crud.list_application_form_fields(db, job_id=str(job.id))
            except Exception as exc:
                state.setdefault("errors", []).append(f"Form fetch failed: {exc}")

        drafts = (job_raw_payload or {}).get("drafts", {})
        payload = build_field_payload(
            form_fields=form_fields,
            drafts=drafts,
            user_profile=user.profile_json or {},
        )

        cfg = default_submission_config()
        try:
            result = perform_submission(
                url=job_url,
                payload=payload,
                platform=job_platform,
                drafts=drafts,
                user_profile=user.profile_json or {},
                mode=str(cfg["mode"]),
                retries=int(cfg["retries"]),
                dry_run=bool(cfg["dry_run"]),
                storage_state_path=cfg["storage_state_path"],
                timeout_ms=int(cfg["timeout_ms"]),
                wait_ms=int(cfg["wait_ms"]),
                headless=bool(cfg["headless"]),
                allow_final_submit=bool(cfg.get("allow_final_submit", False)),
                max_steps=int(cfg.get("max_steps", 12)),
            )
        except Exception as exc:
            # Never let Playwright or platform logic crash the LangGraph run.
            result = {
                "status": "failed",
                "reason": f"exception:{type(exc).__name__}",
                "error": str(exc),
                "response_url": job_url,
                "filled_count": 0,
                "attempts": 1,
            }

        try:
            crud.add_submission_packet(
                db,
                application_id=str(application.id),
                attempt_no=int(result.get("attempts", 1)),
                status=str(result.get("status") or "failed"),
                payload={
                    "platform": job_platform,
                    "field_payload": payload,
                    "result": result,
                },
                response_url=str(result.get("response_url") or "") or None,
                block_reason=str(result.get("reason") or "") or None,
                submitted_at=now_utc() if str(result.get("status")) == "submitted" else None,
            )
        except Exception as exc:
            state.setdefault("errors", []).append(f"Failed to persist submission packet: {exc}")

        status = str(result.get("status") or "failed")
        if status == "submitted":
            application.status = JobStatus.SUBMITTED
            job.status = JobStatus.SUBMITTED
            state["status"] = JobStatus.SUBMITTED.value
            state["allow_packet_without_approval"] = False
            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="submission_result",
                entity_type="application",
                entity_id=str(application.id),
                payload={"status": status, "response_url": result.get("response_url")},
            )
            db.commit()
            return state

        # blocked, failed, or dry-run fallback path
        application.status = JobStatus.READY_FOR_REVIEW
        job.status = JobStatus.READY_FOR_REVIEW
        state["status"] = JobStatus.READY_FOR_REVIEW.value
        state["allow_packet_without_approval"] = True

        reason = str(result.get("reason") or "submission_not_completed")
        if status == "blocked":
            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="submission_blocked",
                entity_type="application",
                entity_id=str(application.id),
                payload={"reason": reason, "response_url": result.get("response_url")},
            )
        else:
            audit_event(
                db,
                actor_type="agent",
                actor_id=actor_id,
                action="submission_result",
                entity_type="application",
                entity_id=str(application.id),
                payload={"status": status, "reason": reason, "response_url": result.get("response_url")},
            )
        state.setdefault("errors", []).append(f"Submission pending: {reason}")
        db.commit()
        return state

    return auto_fill_node
