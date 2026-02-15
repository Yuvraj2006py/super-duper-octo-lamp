# 01_PRD - Job Application Assistant

## Product Summary
The product autonomously discovers, parses, ranks, drafts, verifies, and tracks job applications while requiring explicit human approval for any irreversible or identity-bearing action. The MVP produces high-quality submission packets and never performs automatic submission or message sending.

## Problem Statement
Job seekers lose time on repetitive discovery, qualification, and drafting tasks. Existing automation tools either over-automate (risking policy violations) or under-automate (low leverage). This product balances autonomy with human control.

## Personas
- Primary user: individual job seeker with a canonical profile and measurable achievements.
- Secondary stakeholder: advisor/recruiter reviewing draft quality and compliance.
- Governance stakeholder: security/compliance reviewer validating auditability and ToS adherence.

## Goals
- Reduce time from job discovery to review-ready packet.
- Improve fit-based prioritization with explainable scoring.
- Eliminate ungrounded claims before review.
- Preserve user agency through approval gating.

## Non-Goals
- No bypass of CAPTCHA, anti-bot controls, or website protections.
- No stealth browser automation.
- No autonomous external submission or messaging in MVP.
- No multi-tenant production auth in MVP.

## Functional Requirements
1. Ingest jobs from allowed sources (RSS and manual JSON import).
2. Normalize jobs into stable schema.
3. Score jobs with weighted breakdown and shortlist support.
4. Draft resume summary, bullet ordering, cover letter, and short answers.
5. Verify claims against user profile and block unsupported claims.
6. Queue verified applications as `READY_FOR_REVIEW`.
7. Support approve/reject action in dashboard/API.
8. Build packet artifacts for approved applications:
   - `resume.docx`
   - `resume.pdf`
   - `cover_letter.docx`
   - `cover_letter.pdf`
   - `application_payload.json`
   - `verification_report.json`
9. Track lifecycle statuses and audit every agent/action transition.

## Non-Functional Requirements
- Reliability: deterministic mock providers for reproducible local demo.
- Explainability: persist scoring breakdown and claims-evidence mapping.
- Safety: strict approval gate and rate limiting.
- Traceability: append-only audit log for who/what/when.
- Extensibility: provider interfaces for LLM and embeddings swap.

## Scope Boundaries
In scope:
- Single-user MVP.
- Local deployment via Docker Compose.
- Dashboard for list/detail/review actions.

Out of scope:
- Multi-user RBAC.
- Full production secrets platform.
- Automated external apply APIs.

## User Stories
- As a user, I import jobs and receive a ranked shortlist.
- As a user, I see generated drafts only from my profile evidence.
- As a user, I get explicit verification failures before review.
- As a user, I approve/reject each application packet manually.
- As a stakeholder, I can audit all actions and transitions.

## Risk and Compliance Notes
- Source compliance gate (`automation_allowed`) blocks disallowed automation.
- Guardrails prohibit banned automation actions.
- Generated text must map to profile claims/evidence.
- No identity-bearing action occurs without explicit approval.
- Rate limiting prevents spammy ingestion/drafting behavior.

## What’s Built in MVP
- End-to-end local pipeline through `PACKET_BUILT`.
- Approval-gated workflow and packet generation.
- Audit logging, rate limits, and deterministic verification.
- FastAPI + Celery + Postgres/pgvector + Redis + Next.js scaffold.

## Future Extensions
- Multi-user auth, RBAC, and per-tenant data isolation.
- Official partner APIs for compliant application submission.
- Stronger retrieval/reranking and model-based quality scoring.
- Advanced follow-up automation with approval templates.

## Phase Roadmap (S/M/L effort tiers)
- Phase 1 (S): platform bootstrap and health checks.
- Phase 2 (M): schema/migrations/seed and profile embeddings.
- Phase 3 (M): graph pipeline and deterministic verification.
- Phase 4 (M): approval gating, packet generation, audit hardening.
- Phase 5 (S): dashboard polish and test coverage.
- Phase 6 (S): production hardening and governance artifacts.
