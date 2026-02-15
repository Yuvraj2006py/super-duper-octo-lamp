from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_current_user
from app.api.schemas import PipelineRunRequest, PipelineRunResponse
from app.db.models import Job, User
from app.workers.tasks import run_pipeline_batch_sync

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    payload: PipelineRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    if payload.dry_run:
        stmt = (
            select(Job)
            .where(Job.status == payload.status_filter)
            .order_by(Job.posted_at.desc().nullslast(), Job.created_at.desc())
            .limit(payload.top_n)
        )
        jobs = list(db.scalars(stmt))
        return PipelineRunResponse(
            processed=0,
            results=[{"job_id": str(job.id), "status": job.status.value} for job in jobs],
        )

    try:
        results = run_pipeline_batch_sync(
            top_n=payload.top_n,
            status_filter=payload.status_filter.value,
            actor_id=str(user.id),
        )
        return PipelineRunResponse(processed=len(results), results=results)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Pipeline execution failed. Check worker/api logs for details.",
        ) from exc
