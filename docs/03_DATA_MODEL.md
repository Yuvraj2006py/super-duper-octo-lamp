# 03_DATA_MODEL - Postgres Schema and ERD

## Schema Overview
The schema models users, job sources, jobs, embeddings, applications, artifacts, messages, and append-only audit logs.

## Status Enum Lifecycle
`DISCOVERED -> PARSED -> SCORED -> DRAFTED -> VERIFIED -> READY_FOR_REVIEW -> APPROVED -> PACKET_BUILT -> SUBMITTED -> FOLLOWUP_SCHEDULED -> CLOSED`

## Tables
### users
- `id UUID PK`
- `email UNIQUE NOT NULL`
- `full_name NOT NULL`
- `profile_yaml TEXT NOT NULL`
- `profile_json JSONB NOT NULL`
- timestamps

### job_sources
- `id PK`
- `name NOT NULL`
- `source_type ENUM(RSS, MANUAL_JSON, MANUAL_CSV)`
- `source_url`, `terms_url`
- `automation_allowed BOOLEAN`
- `active BOOLEAN`
- timestamps

### jobs
- `id UUID PK`
- `source_id FK job_sources.id`
- `external_id NOT NULL`
- `UNIQUE(source_id, external_id)`
- `url`, `raw_text`, `raw_payload JSONB`
- normalized fields: `title`, `company`, `location`, `seniority`, `posted_at`
- `status ENUM`
- `score_total`, `score_breakdown JSONB`
- timestamps

### embeddings
- `id PK`
- `entity_type`, `entity_id`, `chunk_key`, `model_name`
- `vector vector(256)`
- `metadata JSONB`
- `UNIQUE(entity_type, entity_id, chunk_key, model_name)`
- timestamps

### applications
- `id UUID PK`
- `user_id FK users.id`
- `job_id FK jobs.id UNIQUE`
- `status ENUM`
- `verification_passed`
- `verification_report JSONB`
- `claims_table JSONB`
- `approved_by`, `approved_at`, `rejection_reason`
- timestamps

### artifacts
- `id PK`
- `application_id FK applications.id`
- `artifact_type ENUM(RESUME_DOCX, RESUME_PDF, COVER_LETTER_DOCX, COVER_LETTER_PDF, APPLICATION_PAYLOAD_JSON, VERIFICATION_REPORT_JSON)`
- `path`, `checksum_sha256`
- `metadata JSONB`
- timestamps

### messages
- `id PK`
- `application_id FK applications.id`
- `channel`, `direction`, `subject`, `body`
- `status ENUM(DRAFT, READY, SENT)`
- timestamps

### audit_log
- `id BIGSERIAL PK`
- `actor_type`, `actor_id`
- `action`, `entity_type`, `entity_id`
- `payload JSONB`
- `created_at`

## ERD (ASCII)
```text
users (1) ------< applications >------ (1) jobs >------ (1) job_sources
  |                   |                     |
  |                   |                     |
  |                   +------< artifacts    +------< embeddings (entity link)
  |                   +------< messages
  |
  +----------------------------< audit_log (entity references)
```

## Indexing Strategy
- `jobs(status, posted_at DESC)` for pipeline selection.
- `jobs(score_total DESC)` for shortlist ordering.
- GIN: `jobs.raw_payload`, `jobs.score_breakdown`.
- IVFFLAT: `embeddings.vector` with `vector_cosine_ops`.
- `applications(status, updated_at DESC)` for review queue.
- `audit_log(entity_type, entity_id, created_at DESC)` for trace lookup.

## Retention and Storage Notes
- Audit log append-only; no in-place mutation.
- Artifact files stored on shared volume with checksum tracking.
- Embeddings re-generated when profile updates.

## What’s Built in MVP
- Complete migrations (`0001_init`, `0002_add_pdf_artifact_types`) with all required tables/enums/indexes.
- pgvector extension bootstrapped at migration time.
- Seed workflow populates user/profile/jobs/embeddings.

## Future Extensions
- Partitioning for `audit_log` and `jobs` at scale.
- Soft-delete/versioning support for user profile evolution.
- Dedicated claims evidence table for stronger relational guarantees.

## Phase Roadmap (S/M/L effort tiers)
- S: base tables/enums.
- M: indexing and vector search tuning.
- M: data governance, retention automation.
