"""Read-only naming primitive; policy selection and approval belong to callers."""

from dataclasses import dataclass, field
import re
from typing import Mapping


class NamingError(ValueError):
    """A rule or supplied input is invalid; never include input values in errors."""


@dataclass(frozen=True)
class NamingRule:
    rule_id: str
    template: str
    tokens: Mapping[str, str]  # User-defined token -> clarification question.
    provenance: Mapping[str, str]
    bindings: Mapping[str, str] = field(default_factory=dict)


_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _segment(value: str) -> bool:
    return (
        isinstance(value, str) and bool(value.strip())
        and value not in (".", "..")
        and not any(c in value for c in '/\\:{}')
        and all(ord(c) >= 32 and ord(c) != 127 for c in value)
    )


def _path(value: str) -> bool:
    # Pure lexical validation: no filesystem access or platform-dependent parsing.
    return all(_segment(part) for part in value.split("/"))


def resolve_name(rule: NamingRule, values: Mapping[str, str]) -> dict[str, object]:
    """Resolve one explicitly selected rule or return targeted missing-input questions.

    Templates only substitute literal path segments. No code, formatting operators,
    nested references, automatic case conversion or recursive expansion is supported.
    This does not check adapter SQL identifier rules, filesystem collisions, rule
    applicability or human approval. It never writes files.
    """
    if not isinstance(rule.rule_id, str) or not rule.rule_id.strip():
        raise NamingError("A rule ID is required")
    if not isinstance(rule.template, str) or not rule.template or len(rule.template) > 4096:
        raise NamingError("A bounded non-empty template is required")
    for mapping in (rule.tokens, rule.bindings, rule.provenance, values):
        if not isinstance(mapping, Mapping) or len(mapping) > 256:
            raise NamingError("Expected a bounded mapping")
    if not rule.provenance or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
        for k, v in rule.provenance.items()
    ):
        raise NamingError("Non-empty string provenance fields are required")
    if any(not isinstance(k, str) or not _KEY.fullmatch(k)
           or not isinstance(v, str) or not v.strip() for k, v in rule.tokens.items()):
        raise NamingError("Tokens require names and clarification questions")
    used = list(dict.fromkeys(_TOKEN.findall(rule.template)))
    skeleton = _TOKEN.sub("token", rule.template)
    if "{" in skeleton or "}" in skeleton or not _path(skeleton):
        raise NamingError("Template must be a relative path with literal token placeholders")
    if any(token not in rule.tokens for token in used):
        raise NamingError("Template references an undeclared token")
    for mapping in (rule.bindings, values):
        if any(k not in rule.tokens or not _segment(v) or len(v) > 1024 for k, v in mapping.items()):
            raise NamingError("Inputs must be declared tokens with bounded literal segment values")
    if any(k in values and values[k] != v for k, v in rule.bindings.items()):
        raise NamingError("Supplied input conflicts with a fixed policy binding")
    effective = {**rule.bindings, **values}
    result = {"rule_id": rule.rule_id, "provenance": dict(rule.provenance)}
    missing = [token for token in used if token not in effective]
    if missing:
        return {**result, "status": "needs_clarification", "questions": [
            {"token": token, "question": rule.tokens[token]} for token in missing
        ]}
    rendered = _TOKEN.sub(lambda match: effective[match.group(1)], rule.template)
    if len(rendered) > 4096 or not _path(rendered):
        raise NamingError("Rendered name is not a bounded relative path")
    return {**result, "status": "resolved", "value": rendered, "questions": []}
