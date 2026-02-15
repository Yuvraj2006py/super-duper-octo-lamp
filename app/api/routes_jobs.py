from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_current_user
from app.api.schemas import (
    ApplicationFormFieldResponse,
    JobImportJsonFileRequest,
    JobImportJsonRequest,
    JobImportRssRequest,
    JobImportUrlRequest,
    JobResponse,
)
from app.core.enums import JobStatus
from app.db import crud
from app.db.models import User
from app.services.ingestion import (
    import_job_from_url,
    import_jobs_from_json,
    import_jobs_from_json_file,
    import_jobs_from_rss,
)
from app.services.form_fetcher import fetch_and_store_job_form_fields

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/import/json")
def import_json(
    payload: JobImportJsonRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    job_ids = import_jobs_from_json(
        db,
        actor_id=str(user.id),
        jobs_payload=payload.jobs,
        source_name=payload.source_name,
    )
    db.commit()
    return {"imported": len(job_ids), "job_ids": job_ids}


@router.post("/import/json-file")
def import_json_file(
    payload: JobImportJsonFileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    path = Path(payload.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {payload.file_path}")

    job_ids = import_jobs_from_json_file(db, actor_id=str(user.id), file_path=path)
    db.commit()
    return {"imported": len(job_ids), "job_ids": job_ids}


@router.post("/import/rss")
def import_rss(
    payload: JobImportRssRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        job_ids = import_jobs_from_rss(
            db,
            actor_id=str(user.id),
            feed_url=payload.feed_url,
            source_name=payload.source_name,
            terms_url=payload.terms_url,
            automation_allowed=payload.automation_allowed,
        )
        db.commit()
        return {"imported": len(job_ids), "job_ids": job_ids}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/url")
def import_url(
    payload: JobImportUrlRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    try:
        job_ids = import_job_from_url(
            db,
            actor_id=str(user.id),
            url=payload.url,
            source_name=payload.source_name,
            external_id=payload.external_id,
            title=payload.title,
            company=payload.company,
            location=payload.location,
            application_questions=payload.application_questions,
        )
        db.commit()
        return {"imported": len(job_ids), "job_ids": job_ids}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status: JobStatus | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    return crud.list_jobs(db, status=status, limit=limit)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/form-fields", response_model=list[ApplicationFormFieldResponse])
def list_job_form_fields(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return crud.list_application_form_fields(db, job_id=job_id)


@router.post("/{job_id}/form-fields/fetch")
def fetch_job_form_fields(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.url:
        raise HTTPException(status_code=400, detail="Job has no URL")

    try:
        result = fetch_and_store_job_form_fields(db, job=job, actor_id=str(user.id))
        db.commit()
        return {"ok": True, **result}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
