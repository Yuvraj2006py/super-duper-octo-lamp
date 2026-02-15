# 06_SECURITY_COMPLIANCE - Threat Model and Controls

## Security Objectives
- Protect user PII and profile data.
- Preserve workflow integrity and non-repudiation.
- Enforce compliant automation boundaries.

## Threat Model (STRIDE)
| Category | Threat | MVP Control |
|---|---|---|
| Spoofing | Unauthorized API access | API key login + signed session token |
| Tampering | Status/artifact manipulation | DB constraints + audit trail + checksums |
| Repudiation | Deny who approved/rejected | Append-only audit log with actor_id/time |
| Information Disclosure | PII leakage in logs | Redaction policy + structured logging |
| Denial of Service | Abuse via repeated ingest/draft | Redis-backed rate limits |
| Elevation of Privilege | Bypass approval gate | explicit status checks before packet build |

## Secrets Management
- `.env` for local secrets in MVP.
- No secrets committed; `.env.example` provided.
- Future: managed secret store (Vault/SSM/KMS).

## PII Handling
- Profile data stored in `users.profile_json/profile_yaml`.
- Sensitive values redacted from logs where practical.
- Audit events avoid raw credential/token storage.

## Logging and Audit
- Structured JSON logs for services.
- `audit_log` records every meaningful action.
- Artifact files hashed and tracked.

## ToS Compliance Policy
- Only ingest from approved, non-prohibited sources.
- `automation_allowed` gate blocks unsafe sources.
- No stealth automation or anti-bot bypassing.
- No autonomous submissions/messages in MVP.

## Rate Limiting and Anti-Spam
- Ingestion limit per actor/source window.
- Draft generation limit per user window.
- Outreach sending disabled in MVP.

## What’s Built in MVP
- Policy checks, approval gate, and source gating.
- Rate limiter with Redis fallback.
- Audit log and artifact checksums.

## Future Extensions
- Full RBAC and row-level security.
- At-rest encryption + key rotation policies.
- DLP scanning and compliance dashboards.

## Phase Roadmap (S/M/L effort tiers)
- S: baseline controls and policy enforcement.
- M: auth hardening and secure secret lifecycle.
- L: enterprise compliance controls and attestations.
