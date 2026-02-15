from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import JobStatus, SourceType
from app.db import models


def get_single_user(db: Session) -> Optional[models.User]:
    return db.scalar(select(models.User).limit(1))


def get_or_create_source(
    db: Session,
    *,
    name: str,
    source_type: SourceType,
    source_url: str | None,
    terms_url: str | None,
    automation_allowed: bool,
) -> models.JobSource:
    stmt = select(models.JobSource).where(models.JobSource.name == name)
    existing = db.scalar(stmt)
    if existing:
        return existing

    source = models.JobSource(
        name=name,
        source_type=source_type,
        source_url=source_url,
        terms_url=terms_url,
        automation_allowed=automation_allowed,
        active=True,
    )
    db.add(source)
    db.flush()
    return source


def upsert_job(
    db: Session,
    *,
    source_id: int,
    external_id: str,
    url: str | None,
    raw_text: str,
    raw_payload: dict,
    posted_at: datetime | None,
    platform: str | None = None,
) -> models.Job:
    stmt = select(models.Job).where(
        models.Job.source_id == source_id,
        models.Job.external_id == external_id,
    )
    job = db.scalar(stmt)
    if job:
        job.url = url
        job.raw_text = raw_text
        job.raw_payload = raw_payload
        job.posted_at = posted_at
        job.platform = platform or job.platform
        return job

    job = models.Job(
        source_id=source_id,
        external_id=external_id,
        url=url,
        raw_text=raw_text,
        raw_payload=raw_payload,
        posted_at=posted_at,
        platform=platform,
        status=JobStatus.DISCOVERED,
    )
    db.add(job)
    db.flush()
    return job


def list_jobs(db: Session, status: JobStatus | None = None, limit: int = 100) -> list[models.Job]:
    stmt = select(models.Job)
    if status:
        stmt = stmt.where(models.Job.status == status)
    stmt = stmt.order_by(models.Job.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_job(db: Session, job_id: str) -> Optional[models.Job]:
    return db.get(models.Job, job_id)


def get_or_create_application(db: Session, *, user_id: str, job_id: str) -> models.Application:
    stmt = select(models.Application).where(models.Application.job_id == job_id)
    app = db.scalar(stmt)
    if app:
        return app

    app = models.Application(user_id=user_id, job_id=job_id, status=JobStatus.DISCOVERED)
    db.add(app)
    db.flush()
    return app


def update_application_status(db: Session, app: models.Application, status: JobStatus) -> models.Application:
    app.status = status
    db.flush()
    return app


def list_applications(db: Session, limit: int = 100) -> list[models.Application]:
    stmt = select(models.Application).order_by(models.Application.updated_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_application(db: Session, application_id: str) -> Optional[models.Application]:
    return db.get(models.Application, application_id)


def add_artifact(
    db: Session,
    *,
    application_id: str,
    artifact_type,
    path: str,
    checksum_sha256: str,
    metadata: dict,
) -> models.Artifact:
    artifact = models.Artifact(
        application_id=application_id,
        artifact_type=artifact_type,
        path=path,
        checksum_sha256=checksum_sha256,
        metadata_json=metadata,
    )
    db.add(artifact)
    db.flush()
    return artifact


def store_embedding(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    chunk_key: str,
    model_name: str,
    vector: list[float],
    metadata: dict,
) -> models.Embedding:
    stmt = select(models.Embedding).where(
        models.Embedding.entity_type == entity_type,
        models.Embedding.entity_id == entity_id,
        models.Embedding.chunk_key == chunk_key,
        models.Embedding.model_name == model_name,
    )
    existing = db.scalar(stmt)
    if existing:
        existing.vector = vector
        existing.metadata_json = metadata
        return existing

    emb = models.Embedding(
        entity_type=entity_type,
        entity_id=entity_id,
        chunk_key=chunk_key,
        model_name=model_name,
        vector=vector,
        metadata_json=metadata,
    )
    db.add(emb)
    db.flush()
    return emb


def list_embeddings(db: Session, entity_type: str) -> list[models.Embedding]:
    stmt = select(models.Embedding).where(models.Embedding.entity_type == entity_type)
    return list(db.scalars(stmt))


def list_audit_logs(
    db: Session,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    limit: int = 200,
) -> list[models.AuditLog]:
    stmt = select(models.AuditLog)
    if action:
        stmt = stmt.where(models.AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(models.AuditLog.entity_type == entity_type)
    stmt = stmt.order_by(models.AuditLog.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def replace_application_form_fields(
    db: Session,
    *,
    job_id: str,
    fields: Iterable[dict],
) -> list[models.ApplicationFormField]:
    existing = list(
        db.scalars(
            select(models.ApplicationFormField).where(models.ApplicationFormField.job_id == job_id)
        )
    )
    for row in existing:
        db.delete(row)
    db.flush()

    inserted: list[models.ApplicationFormField] = []
    for field in fields:
        row = models.ApplicationFormField(
            job_id=job_id,
            field_key=str(field.get("field_key") or "").strip(),
            label=(str(field.get("label")).strip() if field.get("label") is not None else None),
            type=str(field.get("type") or "unknown").strip().lower(),
            required=bool(field.get("required", False)),
            platform=str(field.get("platform") or "generic").strip().lower() or "generic",
            metadata_json=field.get("metadata", {}) or {},
        )
        db.add(row)
        inserted.append(row)
    db.flush()
    return inserted


def list_application_form_fields(
    db: Session,
    *,
    job_id: str,
) -> list[models.ApplicationFormField]:
    stmt = (
        select(models.ApplicationFormField)
        .where(models.ApplicationFormField.job_id == job_id)
        .order_by(models.ApplicationFormField.id.asc())
    )
    return list(db.scalars(stmt))


def add_submission_packet(
    db: Session,
    *,
    application_id: str,
    attempt_no: int,
    status: str,
    payload: dict,
    response_url: str | None = None,
    block_reason: str | None = None,
    submitted_at: datetime | None = None,
) -> models.SubmissionPacket:
    packet = models.SubmissionPacket(
        application_id=application_id,
        attempt_no=attempt_no,
        status=status,
        payload=payload,
        response_url=response_url,
        block_reason=block_reason,
        submitted_at=submitted_at,
    )
    db.add(packet)
    db.flush()
    return packet


def list_submission_packets(
    db: Session,
    *,
    application_id: str,
    limit: int = 20,
) -> list[models.SubmissionPacket]:
    stmt = (
        select(models.SubmissionPacket)
        .where(models.SubmissionPacket.application_id == application_id)
        .order_by(models.SubmissionPacket.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))
