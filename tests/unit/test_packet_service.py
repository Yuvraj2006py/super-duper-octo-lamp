from pathlib import Path

from app.services.packet_service import _resolve_profile_resume_pdf, _resolve_transcript_pdf


def test_resolve_profile_resume_pdf_prefers_profile_source(tmp_path: Path):
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir(parents=True, exist_ok=True)
    resume_pdf = resume_dir / "YuvrajsSharmaResume.pdf"
    resume_pdf.write_bytes(b"%PDF-1.4 test")

    profile = {"resume_source": {"pdf_path": str(resume_pdf)}}
    assets = {}

    resolved = _resolve_profile_resume_pdf(profile, assets)
    assert resolved == resume_pdf


def test_resolve_transcript_pdf_from_assets(tmp_path: Path):
    transcript = tmp_path / "2026 Transcript.pdf"
    transcript.write_bytes(b"%PDF-1.4 transcript")

    assets = {"transcript_path": str(transcript)}
    resolved = _resolve_transcript_pdf(assets)
    assert resolved == transcript
