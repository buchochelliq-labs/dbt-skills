"""Shared bounds for context and review-only metadata responses."""
import json


class ContextLimitError(ValueError):
    """Static response-limit diagnostic."""


def check_bounds(draft):
    if len(json.dumps(draft, indent=2, ensure_ascii=True, allow_nan=False).encode()) > 1024 * 1024:
        raise ContextLimitError('Context exceeds the review document byte limit')
    pending, count = [(draft, 0)], 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 16 or count > 20000:
            raise ContextLimitError('Context exceeds review document structural limits')
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)

