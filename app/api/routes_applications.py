from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_current_user
from app.api.schemas import ApplicationResponse, ApprovalActionRequest, SubmissionPacketResponse
from app.core.enums import JobStatus
from app.db import crud
from app.db.models import Artifact, Application, SubmissionPacket, User
from app.services.audit import audit_event
from app.services.packet_service import build_packet_for_application

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    return crud.list_applications(db, limit=limit)


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    app = crud.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("/{application_id}/approve")
def approve_application(
    application_id: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    app = crud.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status not in {JobStatus.READY_FOR_REVIEW, JobStatus.APPROVED}:
        raise HTTPException(status_code=409, detail=f"Cannot approve from status {app.status.value}")

    app.status = JobStatus.APPROVED
    app.job.status = JobStatus.APPROVED
    app.approved_by = str(user.id)
    app.approved_at = datetime.now(timezone.utc)

    audit_event(
        db,
        actor_type="user",
        actor_id=str(user.id),
        action="application_approved",
        entity_type="application",
        entity_id=str(app.id),
        payload={"reason": payload.reason},
    )

    artifacts = build_packet_for_application(db, application=app, actor_id=str(user.id))
    db.commit()

    return {"status": app.status.value, "packet_status": app.job.status.value, "artifacts": artifacts}


@router.post("/{application_id}/reject")
def reject_application(
    application_id: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    app = crud.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.status = JobStatus.CLOSED
    app.job.status = JobStatus.CLOSED
    app.rejection_reason = payload.reason or "Rejected by reviewer"

    audit_event(
        db,
        actor_type="user",
        actor_id=str(user.id),
        action="application_rejected",
        entity_type="application",
        entity_id=str(app.id),
        payload={"reason": app.rejection_reason},
    )
    db.commit()

    return {"status": app.status.value}


@router.get("/{application_id}/artifacts")
def list_artifacts(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    app = crud.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    stmt = select(Artifact).where(Artifact.application_id == app.id).order_by(Artifact.created_at.asc())
    artifacts = list(db.scalars(stmt))
    return [
        {
            "id": artifact.id,
            "type": artifact.artifact_type.value,
            "path": artifact.path,
            "checksum_sha256": artifact.checksum_sha256,
            "metadata": artifact.metadata_json,
        }
        for artifact in artifacts
    ]


@router.get("/{application_id}/submission-packets", response_model=list[SubmissionPacketResponse])
def list_submission_packets(
    application_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    app = crud.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return crud.list_submission_packets(db, application_id=application_id, limit=limit)
