# 08_TEST_PLAN - Quality and Validation Strategy

## Test Objectives
- Validate deterministic behavior of parser/scoring/retrieval/verification.
- Confirm state transitions and approval gating.
- Ensure packet artifact generation and audit completeness.

## Unit Tests
1. Parser normalization:
- inputs with varied raw text and metadata produce consistent normalized output.

2. Scoring:
- weighted formula and breakdown values are deterministic and bounded.

3. Retrieval:
- top-k selection returns profile chunks sorted by similarity.

4. Verification:
- catches unsupported employers, metrics, and banned years phrases.

## Integration Tests
1. Pipeline progression:
- `DISCOVERED -> READY_FOR_REVIEW` for valid job/profile.

2. Approval + packet build:
- approve from review state and verify generated artifacts + status change.

3. Reject path:
- reject and validate `CLOSED` state and reason persistence.

4. Audit completeness:
- each critical transition writes expected audit event(s).

## E2E Demo Validation
- `make up`
- `make migrate`
- `make seed`
- `make run_demo`
- validate `/output/<job_id>/` artifact set for approved jobs.

## Quality Metrics
- Hallucination block rate: unsupported claims blocked / total unsupported claims in test set.
- Verification reason coverage: unique deterministic checks triggering expected reasons.
- Draft grounding coverage: claims with source mapping / total claims.
- Pipeline success rate: jobs reaching `READY_FOR_REVIEW` / processed jobs.
- Approval audit completeness: approval/reject actions logged / total decisions.

## Mocking Strategy
- Use `MockEmbeddingProvider` for deterministic vectors.
- Use `MockLLMProvider` for deterministic text generation.
- Avoid network dependencies for default test run.

## CI/Command Plan
- `make test` executes unit and integration tests.
- Future CI should run lint + type checks + tests per PR.

## What’s Built in MVP
- Unit tests for parser, scoring, retrieval, verification.
- Integration test covering pipeline to packet build with explicit approval simulation.

## Future Extensions
- Golden dataset for ranking quality regression.
- Mutation tests for verification guardrails.
- Performance tests for large job imports.

## Phase Roadmap (S/M/L effort tiers)
- S: core unit tests + single integration path.
- M: broader workflow and failure-path coverage.
- L: load, resiliency, and governance-grade validation.
