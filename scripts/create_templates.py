from pathlib import Path

from docx import Document


def ensure_template(path: Path, lines: list[str]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(str(path))


def ensure_templates(base_dir: Path = Path("app/templates")) -> None:
    ensure_template(
        base_dir / "resume_template.docx",
        [
            "{{NAME}}",
            "Email: {{EMAIL}}",
            "Summary",
            "{{SUMMARY}}",
            "Selected Highlights",
            "{{BULLETS}}",
        ],
    )

    ensure_template(
        base_dir / "cover_letter_template.docx",
        [
            "{{NAME}}",
            "Dear {{COMPANY}} Hiring Team,",
            "I am applying for {{ROLE}}.",
            "{{LETTER_BODY}}",
            "Sincerely,",
            "{{NAME}}",
        ],
    )


if __name__ == "__main__":
    ensure_templates()
    print("Templates ensured in app/templates")
