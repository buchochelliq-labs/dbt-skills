"""Bounded declarative modelling documents; no automatic authority promotion."""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import re
import stat

from jsonschema import Draft202012Validator
import yaml

from .modelling_naming import NamingError, NamingRule, resolve_name


class PolicyError(ValueError):
    """Invalid policy; messages intentionally omit untrusted document contents."""


class _Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise PolicyError("YAML aliases are not supported")
        self.policy_depth = getattr(self, "policy_depth", 0) + 1
        self.policy_nodes = getattr(self, "policy_nodes", 0) + 1
        if self.policy_depth > 32 or self.policy_nodes > 20000:
            raise PolicyError("Document exceeds structural limits")
        try:
            return super().compose_node(parent, index)
        finally:
            self.policy_depth -= 1

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise PolicyError("Mapping keys must be unique strings")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# YAML's implicit timestamp conversion is inappropriate for JSON Schema documents.
_Loader.yaml_implicit_resolvers = {
    k: [(tag, regex) for tag, regex in rules if tag != "tag:yaml.org,2002:timestamp"]
    for k, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_SCHEMA = json.loads(Path(__file__).with_name("modelling-policy.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(_SCHEMA)
_MAX_BYTES = 1024 * 1024


def load_document(path: str | Path) -> dict:
    """Load one explicit policy/observations/decisions file without following references."""
    path = Path(path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise PolicyError("Document must be a regular file")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise PolicyError("Document exceeds 1 MiB")
        document = yaml.load(raw.decode("utf-8"), Loader=_Loader)
    except PolicyError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError, ValueError, KeyError, TypeError, OverflowError):
        raise PolicyError("Cannot read a valid YAML document") from None
    validate_document(document)
    provenance = {"document": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}
    return {"document": document, "provenance": provenance}


def validate_document(document: dict) -> None:
    """Validate an in-memory document with the same contract as file loading."""
    pending, nodes = [(document, 1)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 20000:
            raise PolicyError("Document exceeds structural limits")
        if isinstance(value, dict):
            if len(value) > 20000:
                raise PolicyError("Document exceeds structural limits")
            pending.extend((item, depth + 1) for pair in value.items() for item in pair)
        elif isinstance(value, list):
            if len(value) > 20000:
                raise PolicyError("Document exceeds structural limits")
            pending.extend((item, depth + 1) for item in value)
    try:
        serialized = json.dumps(document, indent=2, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise PolicyError("Document must contain JSON-compatible values") from None
    if len(serialized) > _MAX_BYTES:
        raise PolicyError("Canonical document exceeds 1 MiB")
    if not _VALIDATOR.is_valid(document):
        raise PolicyError("Document does not match modelling schema version 1")
    records = document.get("naming", []) + document.get("modelling", []) + document.get("records", [])
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise PolicyError("Record IDs must be unique within a document")
    if document["kind"] == "decisions":
        for record in records:
            timestamp = record["approved_at"]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", timestamp):
                raise PolicyError("Approval timestamps require an ISO date-time with timezone")
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                raise PolicyError("Approval timestamp is not a valid date-time") from None
    if document["kind"] == "policy":
        for index, record in enumerate(document["naming"]):
            try:
                resolve_name(_rule(document, record, {"document": "in-memory"}, index), {})
            except NamingError as error:
                raise PolicyError(str(error)) from None
    if document["kind"] == "proposals":
        for record in records:
            if record["decision"] == "exception" and record["models"] != [record["trigger_model"]]:
                raise PolicyError("An exception proposal must apply only to its trigger model")


def _rule(document, record, provenance, index):
    return NamingRule(record["id"], record["template"], document["tokens"],
                      {**provenance, "locator": f"/naming/{index}"}, record.get("bindings", {}))


def resolve_policy_name(path: str | Path, rule_id: str, values: dict[str, str]) -> dict:
    """Resolve an explicitly selected rule; scope applicability is the caller's decision."""
    loaded = load_document(path)
    document = loaded["document"]
    if document["kind"] != "policy":
        raise PolicyError("Only declared policy documents provide naming rules")
    for index, record in enumerate(document["naming"]):
        if record["id"] == rule_id:
            try:
                result = resolve_name(_rule(document, record, loaded["provenance"], index), values)
            except NamingError as error:
                raise PolicyError(str(error)) from None
            return {**result, "target": record["target"], "scope": record.get("scope", {})}
    raise PolicyError("Naming rule was not found")


def discover_policy_files(root: str | Path, *, max_entries: int = 10000, include_references: bool = False) -> dict:
    """Find standard document filenames without reading their contents or following links."""
    root = Path(root).resolve()
    if not root.is_dir() or not 1 <= max_entries <= 100000:
        raise PolicyError("Discovery requires a directory and a bounded entry limit")
    names = {f"modelling{suffix}.{extension}" for suffix in ("", "-observations", "-decisions")
             for extension in ("yml", "yaml")}
    excluded = {".git", "target", "dbt_packages", "node_modules", ".venv", "venv", "__pycache__"}
    candidates, references, pending, scanned, truncated = [], [], [root], 0, False
    try:
        while pending and not truncated:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > max_entries:
                        truncated = True
                        break
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False) and entry.name not in excluded:
                        pending.append(Path(entry.path))
                    elif entry.name in names and entry.is_file(follow_symlinks=False):
                        candidates.append(Path(entry.path).relative_to(root).as_posix())
                    elif include_references and entry.is_file(follow_symlinks=False):
                        name = entry.name.lower()
                        if name in (".sqlfluff", "dbt_project.yml") or (
                            Path(name).suffix in (".md", ".yml", ".yaml") and
                            any(word in name for word in ("model", "standard", "convention", "decision"))
                        ):
                            references.append(Path(entry.path).relative_to(root).as_posix())
    except OSError:
        raise PolicyError("Cannot complete policy discovery") from None
    return {"candidates": sorted(candidates), **({"references": sorted(references)} if include_references else {}), "truncated": truncated,
            "questions": ["Which existing document is authoritative?" if candidates else
                          "Where are your modelling standards documented, or should a policy be proposed?"]}
