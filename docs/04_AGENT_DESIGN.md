# 04_AGENT_DESIGN - LangGraph and Guardrails

## Pipeline State Object
State keys:
- `run_id`, `job_id`, `application_id`, `user_id`, `actor_id`
- `job_raw`, `job_structured`
- `score`, `score_breakdown`
- `retrieved_profile_chunks`
- `drafts`, `claims_table`
- `verification_report`
- `status`, `errors`
- `manual_decision`, `auto_packet`

## Node Responsibilities
1. Scout
- Logs pipeline entry and confirms job context.

2. Parser/Normalizer
- Converts raw posting to normalized schema.
- Updates status to `PARSED`.

3. Fit Scorer
- Computes weighted fit score and breakdown.
- Updates status to `SCORED`.

4. Writer
- Retrieves top-k profile chunks.
- Generates grounded drafts and claims table.
- Updates status to `DRAFTED`.

5. Verification
- Deterministic claim checks vs profile.
- If pass: `VERIFIED`; else remains `DRAFTED` with reasons.

6. Approval Gate
- No decision: set `READY_FOR_REVIEW`.
- Manual approve: set `APPROVED`.
- Manual reject: set `CLOSED`.

7. Packet Builder
- Allowed only when `APPROVED`.
- Generates packet artifacts and sets `PACKET_BUILT`.

8. Tracker
- Logs lifecycle checkpoint for analytics/reminders.

## Tooling and Prompts
- Writer/verifier prompt templates live under `app/agents/prompts`.
- Mock providers ensure deterministic output.
- All node actions are audited.

## Guardrail Policy
- Disallow CAPTCHA bypass, stealth browser behavior, auto-submit, auto-send.
- Enforce source allowlist via `automation_allowed`.
- Require manual review for identity-bearing actions.
- Redact sensitive fields in structured logs.

## Failure Handling
- Node-level errors append to `state.errors`.
- Verification failure blocks progression.
- Packet build blocked unless status is `APPROVED`.
- Rate-limit failures produce explicit errors.

## Retry Behavior
- Pipeline is idempotent on same job id (upserts + status transitions).
- Re-running on failed drafts allowed after profile updates/manual edits.

## What’s Built in MVP
- All required agent nodes implemented as LangGraph nodes.
- End-to-end transition to `READY_FOR_REVIEW`.
- Manual approval path for packet build.

## Future Extensions
- Human-in-the-loop edits between `DRAFTED` and `VERIFIED`.
- Multi-agent confidence calibration and critique loops.
- Tool-use policies per source/provider.

## Phase Roadmap (S/M/L effort tiers)
- S: node scaffolding and state contracts.
- M: verification hardening and retries.
- M: richer policy engine and adaptive routing.
