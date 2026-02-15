# 05_WORKFLOWS - State Machine and Operations

## Canonical State Machine
```text
DISCOVERED
  -> PARSED
  -> SCORED
  -> DRAFTED
  -> VERIFIED
  -> READY_FOR_REVIEW
  -> APPROVED
  -> PACKET_BUILT
  -> SUBMITTED (manual-only in MVP)
  -> FOLLOWUP_SCHEDULED
  -> CLOSED
```

## Core Workflow
1. Ingest jobs from RSS/manual JSON.
2. Normalize and score.
3. Draft and verify claims.
4. Queue for manual review.
5. Approve or reject.
6. Build packet for approved applications.
7. Track outcomes and follow-up states.

## Approval and Rejection Paths
- Approve:
  - Preconditions: `READY_FOR_REVIEW` and `verification_passed=true`.
  - Effects: `APPROVED` then `PACKET_BUILT` after packet generation.
- Reject:
  - Effects: `CLOSED` with rejection reason.

## Manual Submission Packet Path
For targets lacking permitted automation:
- system generates packet artifacts under `/output/<job_id>/`.
  - `resume.docx`, `resume.pdf`
  - `cover_letter.docx`, `cover_letter.pdf`
  - `application_payload.json`, `verification_report.json`
- user performs manual application using packet contents.
- status can be manually moved to `SUBMITTED` in future extension.

## Follow-up and Outcome Learning
MVP:
- tracker logs status updates and supports placeholder scheduling.
Future:
- ingest outcomes (interview/reject/offer) and tune ranking weights.

## What’s Built in MVP
- Full state progression through packet build with manual approval.
- Reject and close path.
- Audited transitions.

## Future Extensions
- Follow-up templates and reminder automation (still approval-gated).
- Outcome-driven ranking feedback loop.
- Channel-specific communication workflows.

## Phase Roadmap (S/M/L effort tiers)
- S: baseline lifecycle and transitions.
- M: outcome ingestion and analytics.
- L: adaptive policy/learning workflows.
