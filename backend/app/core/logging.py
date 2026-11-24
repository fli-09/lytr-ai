"""Logging setup with secret redaction.

Provider error messages can occasionally echo request details. Every log
record passes through a filter that replaces configured API key values
with a placeholder, so keys never reach stdout/host logs.
"""

from __future__ import annotations

import logging


class SecretRedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # longest first so overlapping secrets are fully replaced
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "***redacted***")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(secrets: list[str]) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    redactor = SecretRedactingFilter(secrets)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(redactor)
    # LiteLLM logs full provider errors on every failed fallback hop; our own
    # gateway logs a sanitised one-line summary instead.
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
