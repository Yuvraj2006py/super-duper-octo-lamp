import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import SourceType
from app.core.rate_limit import rate_limiter
from app.db import crud
from app.services.audit import audit_event
from app.services.form_fetcher import fetch_and_store_job_form_fields
from app.services.url_parser import fetch_and_extract_job_payload


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def import_jobs_from_json(
    db: Session,
    *,
    actor_id: str,
    jobs_payload: list[dict[str, Any]],
    source_name: str = "manual-json",
) -> list[str]:
    settings = get_settings()
    key = f"ingest:json:{actor_id}"
    if not rate_limiter.allow(key, settings.ingestion_rate_limit, settings.rate_limit_window_seconds):
        raise ValueError("Ingestion rate limit exceeded")

    source = crud.get_or_create_source(
        db,
        name=source_name,
        source_type=SourceType.MANUAL_JSON,
        source_url=None,
        terms_url=None,
        automation_allowed=True,
    )

    if not source.automation_allowed:
        raise ValueError("Source disallows automation")

    job_ids: list[str] = []
    for raw in jobs_payload:
        job = crud.upsert_job(
            db,
            source_id=source.id,
            external_id=str(raw.get("external_id") or raw.get("id") or raw.get("url")),
            url=raw.get("url"),
            raw_text=raw.get("raw_text", ""),
            raw_payload=raw,
            posted_at=_parse_posted_at(raw.get("posted_at")),
            platform=str(raw.get("platform") or (raw.get("source_metadata") or {}).get("platform") or "").strip().lower() or None,
        )
        job_ids.append(str(job.id))
        audit_event(
            db,
            actor_type="system",
            actor_id=actor_id,
            action="job_discovered",
            entity_type="job",
            entity_id=str(job.id),
            payload={"source": source.name},
        )
    db.flush()
    return job_ids


def import_jobs_from_json_file(db: Session, *, actor_id: str, file_path: Path) -> list[str]:
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("JSON file must contain a list of jobs")
    return import_jobs_from_json(db, actor_id=actor_id, jobs_payload=payload, source_name=file_path.stem)


def import_jobs_from_rss(
    db: Session,
    *,
    actor_id: str,
    feed_url: str,
    source_name: str,
    terms_url: str | None,
    automation_allowed: bool,
) -> list[str]:
    settings = get_settings()
    key = f"ingest:rss:{source_name}"
    if not rate_limiter.allow(key, settings.ingestion_rate_limit, settings.rate_limit_window_seconds):
        raise ValueError("Ingestion rate limit exceeded")

    source = crud.get_or_create_source(
        db,
        name=source_name,
        source_type=SourceType.RSS,
        source_url=feed_url,
        terms_url=terms_url,
        automation_allowed=automation_allowed,
    )

    if not source.automation_allowed:
        raise ValueError("Source disallows automation")

    feed = feedparser.parse(feed_url)
    job_ids: list[str] = []
    for entry in feed.entries:
        raw_text = f"Title: {entry.get('title', '')}\nSummary: {entry.get('summary', '')}"
        raw_payload = {
            "title": entry.get("title"),
            "company": entry.get("author"),
            "url": entry.get("link"),
            "posted_at": entry.get("published"),
            "raw_text": raw_text,
        }
        job = crud.upsert_job(
            db,
            source_id=source.id,
            external_id=str(entry.get("id") or entry.get("link") or entry.get("title")),
            url=entry.get("link"),
            raw_text=raw_text,
            raw_payload=raw_payload,
            posted_at=None,
            platform=None,
        )
        job_ids.append(str(job.id))
        audit_event(
            db,
            actor_type="system",
            actor_id=actor_id,
            action="job_discovered",
            entity_type="job",
            entity_id=str(job.id),
            payload={"source": source.name},
        )

    db.flush()
    return job_ids


def import_job_from_url(
    db: Session,
    *,
    actor_id: str,
    url: str,
    source_name: str = "manual-url",
    external_id: str | None = None,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    application_questions: list[str] | None = None,
) -> list[str]:
    settings = get_settings()
    key = f"ingest:url:{actor_id}"
    if not rate_limiter.allow(key, settings.ingestion_rate_limit, settings.rate_limit_window_seconds):
        raise ValueError("Ingestion rate limit exceeded")

    payload = fetch_and_extract_job_payload(
        url=url,
        timeout_seconds=45,
        external_id=external_id,
        title=title,
        company=company,
        location=location,
        user_questions=application_questions or [],
    )

    job_ids = import_jobs_from_json(
        db,
        actor_id=actor_id,
        jobs_payload=[payload],
        source_name=source_name,
    )
    job = crud.get_job(db, job_ids[0]) if job_ids else None
    if job:
        try:
            catalog_result = fetch_and_store_job_form_fields(db, job=job, actor_id=actor_id)
            audit_event(
                db,
                actor_type="system",
                actor_id=actor_id,
                action="form_catalog_refreshed",
                entity_type="job",
                entity_id=str(job.id),
                payload=catalog_result,
            )
        except Exception as exc:
            audit_event(
                db,
                actor_type="system",
                actor_id=actor_id,
                action="form_catalog_failed",
                entity_type="job",
                entity_id=str(job.id),
                payload={"error": str(exc)},
            )

    return job_ids
