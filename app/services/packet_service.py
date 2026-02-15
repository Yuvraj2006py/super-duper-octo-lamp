import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import ArtifactType, JobStatus
from app.db import crud, models
from app.services.audit import audit_event
from app.services.docs_builder import render_docx_template, render_text_pdf


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _cover_letter_body_for_template(letter_text: str) -> str:
    if not letter_text.strip():
        return ""
    lines = [line.rstrip() for line in letter_text.replace("\r\n", "\n").split("\n")]

    start_idx = None
    end_idx = None
    for idx, line in enumerate(lines):
        if line.strip().lower().startswith("dear "):
            start_idx = idx + 1
            break

    if start_idx is None:
        return letter_text

    for idx in range(start_idx, len(lines)):
        lowered = lines[idx].strip().lower()
        if lowered.startswith("sincerely") or lowered.startswith("best regards") or lowered.startswith("regards"):
            end_idx = idx
            break

    body_lines = lines[start_idx:end_idx] if end_idx is not None else lines[start_idx:]
    body = "\n".join(body_lines).strip()
    return body or letter_text


def _resolve_profile_resume_pdf(profile: dict[str, Any], assets: dict[str, Any]) -> Path | None:
    candidate_paths: list[str] = []
    for key in ["resume_pdf_path", "resume_path"]:
        value = str(assets.get(key, "")).strip()
        if value:
            candidate_paths.append(value)

    resume_source = profile.get("resume_source", {}) if isinstance(profile.get("resume_source", {}), dict) else {}
    source_path = str(resume_source.get("pdf_path", "")).strip()
    if source_path:
        candidate_paths.append(source_path)

    for path_str in candidate_paths:
        path = Path(path_str)
        if path.exists() and path.is_file():
            return path
    return None


def _resolve_transcript_pdf(assets: dict[str, Any]) -> Path | None:
    transcript_path = str(assets.get("transcript_path", "")).strip()
    if not transcript_path:
        return None
    candidate = Path(transcript_path)
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def build_packet_for_application(
    db: Session,
    *,
    application: models.Application,
    actor_id: str,
) -> dict[str, str]:
    settings = get_settings()
    job = application.job
    user = application.user
    drafts = (job.raw_payload or {}).get("drafts", {})
    structured = (job.raw_payload or {}).get("structured", {})
    verification_report = application.verification_report or {}
    profile = user.profile_json or {}
    assets = profile.get("application_assets", {}) or {}
    internship_prefs = profile.get("internship_preferences", {}) or {}
    requires_cover_letter = bool(structured.get("requires_cover_letter", False))
    requires_transcript = bool(structured.get("requires_transcript", False))
    application_questions = [str(item).strip() for item in structured.get("application_questions", []) if str(item).strip()]
    question_answer_pairs = [
        pair
        for pair in drafts.get("question_answer_pairs", [])
        if isinstance(pair, dict) and str(pair.get("question", "")).strip()
    ]
    profile_resume_source = _resolve_profile_resume_pdf(profile, assets)
    transcript_source = _resolve_transcript_pdf(assets)
    submission_packets = crud.list_submission_packets(db, application_id=str(application.id), limit=1)
    latest_submission_packet = submission_packets[0] if submission_packets else None

    output_dir = settings.output_dir / str(job.id)
    output_dir.mkdir(parents=True, exist_ok=True)

    resume_path = output_dir / "resume.docx"
    resume_pdf_path = output_dir / "resume.pdf"
    cover_path = output_dir / "cover_letter.docx"
    cover_pdf_path = output_dir / "cover_letter.pdf"
    transcript_output_path = output_dir / "transcript.pdf"
    payload_path = output_dir / "application_payload.json"
    report_path = output_dir / "verification_report.json"

    render_docx_template(
        settings.template_dir / "resume_template.docx",
        resume_path,
        {
            "NAME": user.full_name,
            "EMAIL": user.email,
            "SUMMARY": drafts.get("resume_summary", "Summary unavailable"),
            "BULLETS": "\n".join(drafts.get("bullet_ordering", [])),
        },
    )

    if profile_resume_source:
        shutil.copy2(profile_resume_source, resume_pdf_path)
    else:
        render_text_pdf(
            resume_pdf_path,
            title=f"{user.full_name} - Resume",
            body="\n".join(
                [
                    f"Email: {user.email}",
                    "",
                    drafts.get("resume_summary", "Summary unavailable"),
                    "",
                    "Recommended Bullet Ordering:",
                    *drafts.get("bullet_ordering", []),
                ]
            ),
        )

    generated_cover_letter = bool(drafts.get("cover_letter", "").strip()) and requires_cover_letter
    if generated_cover_letter:
        render_docx_template(
            settings.template_dir / "cover_letter_template.docx",
            cover_path,
            {
                "NAME": user.full_name,
                "COMPANY": job.company or "Hiring Team",
                "ROLE": job.title or "the role",
                "LETTER_BODY": _cover_letter_body_for_template(
                    drafts.get("cover_letter", "Cover letter draft unavailable")
                ),
            },
        )
        render_text_pdf(
            cover_pdf_path,
            title=f"Cover Letter - {job.company or 'Hiring Team'}",
            body=drafts.get("cover_letter", "Cover letter draft unavailable"),
        )
    else:
        if cover_path.exists():
            cover_path.unlink()
        if cover_pdf_path.exists():
            cover_pdf_path.unlink()

    transcript_selected_path = ""
    if requires_transcript and transcript_source:
        shutil.copy2(transcript_source, transcript_output_path)
        transcript_selected_path = str(transcript_output_path)
    elif transcript_output_path.exists():
        transcript_output_path.unlink()

    payload = {
        "job_id": str(job.id),
        "application_id": str(application.id),
        "user_id": str(user.id),
        "job": {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
        },
        "application_questions": application_questions,
        "application_answers": question_answer_pairs,
        "drafts": drafts,
        "claims_table": application.claims_table or [],
        "verification_passed": application.verification_passed,
        "submission_plan": {
            "resume_selected_path": str(resume_pdf_path),
            "resume_source_path": str(profile_resume_source) if profile_resume_source else "",
            "requires_cover_letter": requires_cover_letter,
            "cover_letter_generated": generated_cover_letter,
            "requires_transcript": requires_transcript,
            "transcript_selected_path": transcript_selected_path,
            "questions_answered": [
                str(item.get("question")).strip()
                for item in question_answer_pairs
                if str(item.get("answer", "")).strip()
            ],
        },
        "candidate_submission_assets": {
            "portfolio_url": assets.get("portfolio_url", ""),
            "github_url": assets.get("github_url", ""),
            "linkedin_url": assets.get("linkedin_url", ""),
            "website_url": assets.get("website_url", ""),
            "transcript_url": assets.get("transcript_url", ""),
            "transcript_path": assets.get("transcript_path", ""),
            "transcript_included_path": transcript_selected_path,
            "additional_links": assets.get("additional_links", []),
            "notes": "Fill these in at data/user_profile.yaml -> application_assets",
        },
        "internship_preferences": {
            "active_term": internship_prefs.get("active_term", ""),
            "target_terms": internship_prefs.get("target_terms", []),
            "target_role_families": internship_prefs.get("target_role_families", []),
            "preferred_locations": internship_prefs.get("preferred_locations", []),
        },
        "submission_packet": (
            {
                "status": latest_submission_packet.status,
                "attempt_no": latest_submission_packet.attempt_no,
                "response_url": latest_submission_packet.response_url,
                "block_reason": latest_submission_packet.block_reason,
                "submitted_at": (
                    latest_submission_packet.submitted_at.isoformat()
                    if latest_submission_packet.submitted_at
                    else None
                ),
                "payload": latest_submission_packet.payload,
            }
            if latest_submission_packet
            else None
        ),
    }
    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(verification_report, indent=2), encoding="utf-8")

    artifacts = {
        ArtifactType.RESUME_DOCX: resume_path,
        ArtifactType.RESUME_PDF: resume_pdf_path,
        ArtifactType.APPLICATION_PAYLOAD_JSON: payload_path,
        ArtifactType.VERIFICATION_REPORT_JSON: report_path,
    }
    if generated_cover_letter:
        artifacts[ArtifactType.COVER_LETTER_DOCX] = cover_path
        artifacts[ArtifactType.COVER_LETTER_PDF] = cover_pdf_path
    for artifact_type, path in artifacts.items():
        crud.add_artifact(
            db,
            application_id=str(application.id),
            artifact_type=artifact_type,
            path=str(path),
            checksum_sha256=_sha256_file(path),
            metadata={"size_bytes": path.stat().st_size},
        )

    application.status = JobStatus.PACKET_BUILT
    job.status = JobStatus.PACKET_BUILT

    audit_event(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="packet_built",
        entity_type="application",
        entity_id=str(application.id),
        payload={"job_id": str(job.id), "output_dir": str(output_dir)},
    )

    db.flush()
    return {artifact_type.value: str(path) for artifact_type, path in artifacts.items()}
