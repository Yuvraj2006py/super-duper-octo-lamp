from pathlib import Path

import yaml

from app.services.resume_pdf_parser import parse_resume_pdf


def main() -> None:
    resume_dir = Path("resume")
    candidates = sorted(resume_dir.glob("*.pdf"))
    if not candidates:
        raise SystemExit("No PDF found in resume/ directory")

    pdf_path = candidates[0]
    profile = parse_resume_pdf(pdf_path)

    output_path = Path("data/user_profile.generated.yaml")
    output_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    print(f"Parsed resume: {pdf_path}")
    print(f"Output profile: {output_path}")
    print(
        "Extracted counts: "
        f"education={len(profile.get('education', []))}, "
        f"experience={len(profile.get('experience', []))}, "
        f"projects={len(profile.get('projects', []))}, "
        f"skills={len(profile.get('skills', []))}"
    )


if __name__ == "__main__":
    main()
