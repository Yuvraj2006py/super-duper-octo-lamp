# Local Resume Assets (Not Committed)

Put your personal documents in this folder. They are ignored by git.

Expected files:
- `resume/*.pdf` (resume, transcript, etc.)

Config (optional):
- `RESUME_PDF_PATH=resume/<your_resume>.pdf`
- `TRANSCRIPT_PDF_PATH=resume/<your_transcript>.pdf`

If you don't set paths, the Workday auto-fill will pick the largest matching PDF in this folder for labels containing "resume/cv" or "transcript".
