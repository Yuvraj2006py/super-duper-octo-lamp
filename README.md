# Job Application Assistant (MVP)

Autonomous discovery/ranking/drafting/tracking with automatic packet build after verification. The MVP is intentionally compliance-first:
- no CAPTCHA bypass
- no stealth automation
- no browser auto-submit or outbound auto-send
- source allowlisting and auditability by default

## Stack
- Python 3.11+
- FastAPI + Pydantic
- Postgres + pgvector
- Alembic migrations
- Celery + Redis
- LangGraph agents
- Next.js dashboard
- Docker Compose

## Repository Structure
See `docs/02_ARCHITECTURE.md` and scaffold directories under `/app`, `/dashboard`, `/docs`, `/data`, `/scripts`, `/tests`.

## Quick Start
1. Copy env:
```bash
cp .env.example .env
```
2. Boot services:
```bash
make up
```
If you change `.env` values later (for example LLM settings), apply them with:
```bash
make reload
```
3. Apply migrations:
```bash
make migrate
```
4. Seed user profile/jobs/templates/embeddings:
```bash
make seed
```
Notes:
- If `resume/*.pdf` exists, seed will parse it and merge into profile fields (`education`, `experience`, `projects`, `skills`, etc.).
- A generated canonical profile is written to `data/user_profile.generated.yaml`.
- `make seed` resets mutable demo state (`jobs`, `applications`, `artifacts`, `messages`) for reproducible reruns.
- Internship-mode defaults and editable placeholders are in `data/user_profile.yaml`.

Optional: parse resume without seeding DB:
```bash
make parse_resume
```
5. Run demo pipeline (top 3 discovered jobs, fully automated packet build for verified jobs):
```bash
make run_demo
```
6. Open dashboard:
- `http://localhost:3000`
- Login API key: value in `.env` (`LOCAL_API_KEY`, default `change-me`)

## API Endpoints
- `GET /healthz`
- `POST /auth/login`
- `POST /jobs/import/json`
- `POST /jobs/import/json-file`
- `POST /jobs/import/rss`
- `POST /jobs/import/url`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /pipeline/run`
- `GET /applications`
- `GET /applications/{application_id}`
- `POST /applications/{application_id}/approve`
- `POST /applications/{application_id}/reject`
- `GET /applications/{application_id}/artifacts`
- `GET /audit`

## Demo Walkthrough
1. Seed loads:
- profile from `data/user_profile.yaml`
- jobs from `data/jobs_sample.json`
- profile chunk embeddings into `embeddings`
2. Pipeline run performs:
- normalize -> score -> retrieve -> draft -> verify -> auto-approve -> packet build
 - if application questions are available in source content (or provided in URL import), auto-generates grounded answers
3. Verified items produce packet files in `/output/<job_id>/`:
- `resume.docx`
- `resume.pdf`
- `cover_letter.docx`
- `cover_letter.pdf`
- `application_payload.json`
- `verification_report.json`
- `application_payload.json` includes `candidate_submission_assets` placeholders (portfolio/github/linkedin/transcript).
 - `application_payload.json` now includes `application_questions` and `application_answers` for clean review.

### Import from a single job URL
```bash
curl -X POST "http://localhost:8000/jobs/import/url" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "manual-live-url",
    "url": "https://example.com/jobs/123",
    "application_questions": [
      "Why are you interested in this internship?",
      "Describe a project where you used Python."
    ]
  }'
```
Notes:
- The importer extracts title/text and attempts question discovery from page text, labels, and embedded JSON.
- If application form questions are not publicly visible, pass them explicitly via `application_questions`.
- Common form prompts (work authorization/sponsorship/GPA/graduation/availability) use deterministic profile-backed answers.

## Internship Profile Fields (Where to Edit)
Edit `data/user_profile.yaml`:
- `application_assets.portfolio_url`
- `application_assets.github_url`
- `application_assets.linkedin_url`
- `application_assets.transcript_url` or `application_assets.transcript_path`
- `application_assets.additional_links`
- `external_experiences` (for non-resume context you want drafting to use later)
- `internship_preferences.active_term` (`summer` now; `fall`/`winter` kept as placeholders)
- `internship_preferences.target_role_families` (data/ml/backend/software)
- `internship_preferences.preferred_locations` (`remote`, `us`, `canada`)
- `internship_preferences.max_applications_per_company` (anti-spam cap)

## Safety and Compliance
- Source gating via `job_sources.automation_allowed`.
- Verification gate before automatic packet build.
- No outbound sending behavior in MVP.
- Rate limits for ingestion/drafting.
- Per-company application cap to reduce spam-like behavior.
- Audit log for every major action.

## Testing
```bash
make test
```

Included tests:
- parser normalization
- resume PDF parsing and profile merge
- scoring function
- retrieval ranking
- verification hallucination checks
- integration flow for pipeline states and approval outcomes

## CI
GitHub Actions workflow is provided at `.github/workflows/ci.yml`:
- Backend job: migrations, seed, tests.
- Dashboard job: dependency install and Next.js production build.

## Swapping in Real Providers
### LLM provider
- Current default: `LLM_PROVIDER=mock`.
- Built-in OpenAI-compatible path is now supported by env config:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_BASE_URL=https://api.openai.com/v1
```
- Groq (OpenAI-compatible) is also supported:
```bash
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
LLM_API_KEY=your_groq_key
LLM_BASE_URL=https://api.groq.com/openai/v1
```
- Provider selection is handled in `app/services/writing.py` via `build_llm_provider(...)`.
- Do not put API keys in `LLM_PROVIDER`; put them in `LLM_API_KEY`.

### Embeddings provider
- Current default provider is configured by env:
```bash
EMBEDDING_PROVIDER=mock
EMBEDDING_MODEL_NAME=mock-embed-v1
EMBEDDING_DIM=256
```
- Free local BGE embeddings are implemented:
```bash
EMBEDDING_PROVIDER=bge
EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=256
EMBEDDING_CACHE_DIR=/workspace/.cache/fastembed
```
- `EMBEDDING_DIM=256` keeps compatibility with current `vector(256)` schema.
- For full native BGE dimensionality (384), migrate DB vector column and re-embed profile/job content.

## PDF Export Notes
MVP generates both docx and simple text-rendered pdf artifacts.
For production-grade PDF layout, consider:
- Option A: LibreOffice headless conversion in worker container.
- Option B: docx2pdf (platform-dependent).
- Option C: render HTML templates and convert via wkhtmltopdf/weasyprint.

## Known MVP Constraints
- Single-user auth model.
- Deterministic mock models prioritize reproducibility over quality.
- `SUBMITTED` status is reserved for future manual/approved submission integration.
