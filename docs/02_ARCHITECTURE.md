# 02_ARCHITECTURE - System Design

## Overview
The system is split into API, worker, database, queue/cache, and dashboard layers. A LangGraph pipeline orchestrates agent nodes for parsing, scoring, drafting, verification, approval gating, packet building, and tracking.

## Runtime Components
- `FastAPI`: API gateway, auth, orchestration endpoints.
- `Celery + Redis`: asynchronous job processing and scheduling.
- `Postgres + pgvector`: source of truth for jobs, applications, embeddings, artifacts, and audit.
- `LangGraph`: deterministic pipeline state machine.
- `Next.js`: minimal stakeholder-facing dashboard.

## Component Diagram (ASCII)
```text
            +------------------+
            |  Next.js UI      |
            |  (review/approve)|
            +--------+---------+
                     |
                     v
+--------------------+--------------------+
|                FastAPI                  |
| auth/jobs/pipeline/apps/audit endpoints |
+----------+-------------------+----------+
           |                   |
           v                   v
   +-------+------+    +-------+------+
   |   Postgres   |    |   Redis      |
   |  + pgvector  |    | queue+limits |
   +-------+------+    +-------+------+
           ^                   ^
           |                   |
     +-----+-------------------+-----+
     |        Celery Worker          |
     | LangGraph nodes + services    |
     +-------------------------------+
```

## Agent Roles and Boundaries
- Scout: ingest from permitted sources only.
- Parser/Normalizer: deterministic extraction to normalized schema.
- Fit Scorer: weighted score + explainable breakdown.
- Writer: grounded drafts using retrieved profile chunks.
- Verification: deterministic hallucination/fabrication checks.
- Approval Gate: enforces review checkpoint.
- Packet Builder: generates docx/pdf + JSON artifacts.
- Tracker: lifecycle updates and analytics hooks.

## Data Flow
1. Ingest raw jobs.
2. Normalize structure and requirements.
3. Score fit and store breakdown.
4. Retrieve profile chunks and draft content.
5. Verify and gate for review.
6. Human approve/reject.
7. Build artifacts for approved applications.
8. Persist audit events for every transition.

## Tech Choice Rationale
- FastAPI: concise and typed API layer.
- SQLAlchemy + Alembic: schema evolution and migration control.
- Postgres + pgvector: transactional + vector in one store.
- Redis/Celery: simple, proven async model.
- LangGraph: explicit state transitions and controllable execution.
- Next.js: lightweight stakeholder UI.

## Alternatives Considered
- CrewAI/AutoGen: less deterministic state control for this workflow.
- LlamaIndex RAG: skipped for MVP simplicity.
- CLI-only dashboard: faster, but weaker stakeholder demo.

## What’s Built in MVP
- Full component scaffold with local docker-compose deployment.
- Synchronous + worker-executable pipeline path.
- Explicit approval gate before packet build.

## Future Extensions
- Event streaming (Kafka) for richer analytics.
- Policy engine for organization-specific compliance controls.
- Distributed tracing and robust metrics stack.

## Phase Roadmap (S/M/L effort tiers)
- S: baseline services and infra.
- M: pipeline orchestration and persistence.
- M: compliance and approval operations.
- S: UX/operability improvements.
