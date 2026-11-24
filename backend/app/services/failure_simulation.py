"""Parsing for the X-Simulate-Failure request header.

Format: comma-separated `<target>=<status>` pairs.
Targets:
  key_1, key_2, ...  one pool key
  *                  every pool key AND the self-hosted fallback (assignment: `*=429` -> 503)
  keys               every pool key only, so the self-hosted fallback can be tested
  fallback           the self-hosted fallback only
Example: "key_1=429,key_2=500", "*=429", "keys=429".
"""

from __future__ import annotations

SUPPORTED_STATUSES = frozenset({429, 500, 502, 503})
FALLBACK_TARGET = "fallback"


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
        if target in ("*", "keys"):
            for key_id in key_ids:
                plan[key_id] = status
            if target == "*":
                plan[FALLBACK_TARGET] = status
        elif target == FALLBACK_TARGET or target in key_ids:
            plan[target] = status
        else:
            raise InvalidSimulationHeader(f"unknown key id '{target}' in X-Simulate-Failure")
    return plan
