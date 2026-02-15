# 07_CHECKLIST - Implementation Checklist

## Phase 1 (S): Bootstrap + Infra
- [x] Create repository structure.
- [x] Add FastAPI entrypoint and health endpoint.
- [x] Configure Celery/Redis scaffold.
- [x] Add docker-compose and base Dockerfiles.
- [x] Add settings/logging/security modules.

Acceptance criteria:
- [ ] `make up` boots services.
- [ ] `GET /healthz` returns ok.

## Phase 2 (M): Data Model + Migrations + Seed
- [x] Implement SQLAlchemy models.
- [x] Create Alembic migration with pgvector extension.
- [x] Add schema indexes and constraints.
- [x] Add seed scripts and sample data.
- [x] Embed profile chunks into embeddings table.

Acceptance criteria:
- [ ] `make migrate` runs cleanly.
- [ ] `make seed` inserts user, jobs, embeddings.

## Phase 3 (M): Agent Pipeline
- [x] Implement LangGraph state and nodes.
- [x] Build parser/scorer/writer/verifier logic.
- [x] Persist scoring breakdown and claims table.
- [x] Add deterministic verification checks.

Acceptance criteria:
- [ ] Pipeline moves job to `READY_FOR_REVIEW` when verification passes.
- [ ] Verification failures produce reasons and block progression.

## Phase 4 (M): Approval Gate + Packet Build + Audit
- [x] Add approve/reject APIs.
- [x] Enforce approved-only packet build.
- [x] Generate required output artifacts.
- [x] Audit all actions/transitions.

Acceptance criteria:
- [ ] Approved applications become `PACKET_BUILT`.
- [ ] Artifacts exist under `/output/<job_id>/`.

## Phase 5 (S): Dashboard + Demo + Tests
- [x] Implement Next.js list/detail views.
- [x] Add approval panel in job detail view.
- [x] Add Makefile demo/test targets.
- [x] Add unit + integration tests.

Acceptance criteria:
- [ ] `make run_demo` processes top 3 and prompts approval.
- [ ] Dashboard shows score/status/drafts/reports.

## Phase 6 (S): Governance Docs
- [x] Produce docs 01-08 + assumptions.
- [x] Include MVP and future extension sections.
- [x] Include effort-tier roadmap per doc.

Acceptance criteria:
- [ ] Stakeholder review confirms decision completeness.

## Definition of Done
- End-to-end local run from ingest to packet build.
- No auto-submit/no auto-send behaviors in code path.
- Approval gate and audit evidence present for every processed application.
- Tests included and runnable via `make test`.

## What’s Built in MVP
- Implementation checklist mapped to infrastructure, data, agent pipeline, approval, and testing phases.
- Acceptance criteria checkpoints for each phase.
- Explicit definition-of-done for safety and governance requirements.

## Future Extensions
- Add checklist gates for production readiness (SLOs, on-call, incident response).
- Add change-management and policy attestation checkpoints.
- Add release checklist for provider/model swaps.

## Phase Roadmap (S/M/L effort tiers)
- S: scaffold + migration + seed + baseline tests.
- M: verification hardening, richer dashboard, integration depth.
- L: production operations, compliance expansion, and scale testing.
