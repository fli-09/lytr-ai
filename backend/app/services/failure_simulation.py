"""Parsing for the X-Simulate-Failure request header.

Format: comma-separated `<key_id>=<status>` pairs; `*` means every key.
Example: "key_1=429,key_2=500" or "*=429".
"""

from __future__ import annotations

SUPPORTED_STATUSES = frozenset({429, 500, 502, 503})


class InvalidSimulationHeader(ValueError):
    pass


def parse_simulation_header(raw: str | None, key_ids: list[str]) -> dict[str, int]:
    """Return {key_id: status} for this request. Empty dict = no simulation."""
    if raw is None or not raw.strip():
        return {}

    plan: dict[str, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise InvalidSimulationHeader(f"invalid X-Simulate-Failure entry '{part}': expected <key_id>=<status>")
        target, _, status_text = part.partition("=")
        target, status_text = target.strip(), status_text.strip()
        try:
            status = int(status_text)
        except ValueError:
            raise InvalidSimulationHeader(f"invalid status '{status_text}' in X-Simulate-Failure") from None
        if status not in SUPPORTED_STATUSES:
            raise InvalidSimulationHeader(
                f"unsupported status {status} in X-Simulate-Failure; use one of 429, 500, 502, 503"
            )
        if target == "*":
            for key_id in key_ids:
                plan[key_id] = status
        elif target in key_ids:
            plan[target] = status
        else:
            raise InvalidSimulationHeader(f"unknown key id '{target}' in X-Simulate-Failure")
    return plan
