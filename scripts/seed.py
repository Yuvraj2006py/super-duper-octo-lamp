import json
import os
from pathlib import Path

import yaml
from sqlalchemy import delete, text

from app.core.enums import SourceType
from app.db import crud, models
from app.db.session import SessionLocal
from app.services.audit import audit_event
from app.services.embeddings import build_embedding_provider
from app.services.ingestion import import_jobs_from_json
from app.services.resume_pdf_parser import merge_profiles, parse_resume_pdf
from app.services.retrieval import embed_user_profile_chunks
from scripts.create_templates import ensure_templates


def _detect_resume_pdf() -> Path | None:
    explicit = os.getenv("RESUME_PDF_PATH")
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    resume_dir = Path("resume")
    if not resume_dir.exists():
        return None

    candidates = sorted(resume_dir.glob("*.pdf"))
    if not candidates:
        return None

    non_transcript = [path for path in candidates if "transcript" not in path.name.lower()]
    if not non_transcript:
        return None

    resume_named = [path for path in non_transcript if "resume" in path.name.lower()]
    if resume_named:
        return resume_named[0]
    return non_transcript[0]


def _detect_transcript_pdf() -> Path | None:
    explicit = os.getenv("TRANSCRIPT_PDF_PATH")
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    resume_dir = Path("resume")
    if not resume_dir.exists():
        return None

    candidates = sorted(resume_dir.glob("*.pdf"))
    for candidate in candidates:
        if "transcript" in candidate.name.lower():
            return candidate
    return None


def _load_profile(profile_path: Path) -> dict:
    if profile_path.exists():
        return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    return {}


def _build_profile(profile_path: Path) -> tuple[dict, str, Path | None]:
    base_profile = _load_profile(profile_path)
    resume_pdf = _detect_resume_pdf()
    transcript_pdf = _detect_transcript_pdf()

    if resume_pdf:
        parsed_profile = parse_resume_pdf(resume_pdf)
        profile_json = merge_profiles(base_profile, parsed_profile)
    else:
        profile_json = base_profile

    if not profile_json:
        raise ValueError("No profile data found. Provide data/user_profile.yaml or resume/*.pdf")

    assets = profile_json.get("application_assets")
    if not isinstance(assets, dict):
        assets = {}
    if transcript_pdf and not str(assets.get("transcript_path", "")).strip():
        assets["transcript_path"] = str(transcript_pdf)
    profile_json["application_assets"] = assets

    raw_yaml = yaml.safe_dump(profile_json, sort_keys=False)
    generated_path = Path("data/user_profile.generated.yaml")
    generated_path.write_text(raw_yaml, encoding="utf-8")

    return profile_json, raw_yaml, resume_pdf


def seed_user(db, profile_path: Path) -> models.User:
    profile_json, raw_yaml, resume_pdf = _build_profile(profile_path)

    user = crud.get_single_user(db)
    email = profile_json.get("personal_info", {}).get("email", "")
    name = profile_json.get("personal_info", {}).get("name", "")

    if not email or not name:
        raise ValueError("Profile must include personal_info.name and personal_info.email")

    if user:
        user.email = email
        user.full_name = name
        user.profile_yaml = raw_yaml
        user.profile_json = profile_json
    else:
        user = models.User(
            email=email,
            full_name=name,
            profile_yaml=raw_yaml,
            profile_json=profile_json,
        )
        db.add(user)
    db.flush()

    if resume_pdf:
        print(f"Seed profile source: {resume_pdf}")
    else:
        print(f"Seed profile source: {profile_path}")

    print("Wrote generated profile to data/user_profile.generated.yaml")
    return user


def seed_sources(db):
    crud.get_or_create_source(
        db,
        name="sample-json-source",
        source_type=SourceType.MANUAL_JSON,
        source_url=None,
        terms_url="https://example.com/terms",
        automation_allowed=True,
    )


def reset_demo_state(db) -> None:
    # Keep canonical user/source records but reset demo state for reproducible runs.
    db.execute(delete(models.Artifact))
    db.execute(delete(models.Message))
    db.execute(delete(models.Application))
    db.execute(delete(models.Embedding).where(models.Embedding.entity_type == "profile_chunk"))
    db.execute(delete(models.Job))
    db.flush()


def seed_jobs(db, user_id: str, jobs_path: Path) -> list[str]:
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    return import_jobs_from_json(
        db,
        actor_id=user_id,
        jobs_payload=payload,
        source_name="sample-json-source",
    )


def main() -> None:
    ensure_templates(Path("app/templates"))

    db = SessionLocal()
    try:
        profile_path = Path("data/user_profile.yaml")
        jobs_path = Path("data/jobs_sample.json")

        reset_demo_state(db)
        user = seed_user(db, profile_path)
        seed_sources(db)
        job_ids = seed_jobs(db, str(user.id), jobs_path)

        embedder = build_embedding_provider()
        chunk_count = embed_user_profile_chunks(db, user, embedder)

        audit_event(
            db,
            actor_type="system",
            actor_id=str(user.id),
            action="seed_completed",
            entity_type="user",
            entity_id=str(user.id),
            payload={"jobs_seeded": len(job_ids), "profile_chunks_embedded": chunk_count},
        )

        db.commit()

        # Improve IVFFLAT query planning after embeddings are inserted.
        db.execute(text("ANALYZE embeddings"))
        db.commit()

        print(f"Seed complete: user={user.email}, jobs={len(job_ids)}, profile_chunks={chunk_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
