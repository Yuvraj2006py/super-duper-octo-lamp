from typing import Any

from app.db.models import JobSource

DISALLOWED_ACTIONS = {
    "captcha_bypass",
    "stealth_browser",
    "auto_submit",
    "auto_send_message",
}


def assert_source_allowed(source: JobSource) -> None:
    if not source.automation_allowed:
        raise ValueError("Automation is disabled for this source by policy")


def assert_action_allowed(action: str) -> None:
    if action in DISALLOWED_ACTIONS:
        raise ValueError(f"Action is disallowed by policy: {action}")


def redact_sensitive(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    pii_fields = {"email", "phone", "address", "token", "api_key"}
    for key in list(redacted.keys()):
        if key.lower() in pii_fields:
            redacted[key] = "[REDACTED]"
    return redacted
