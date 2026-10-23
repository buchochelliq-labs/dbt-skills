"""Read-only structural filename comparison; no approval or semantic compliance claims."""

from pathlib import PurePosixPath
import re

from .modelling_naming import NamingError, NamingRule, _segment, resolve_name
from .modelling_policy import PolicyError, load_document
from .project_artifacts import inspect_artifacts


def match_template(template, value, bindings, *, max_states=2048):
    """Bounded existential match of a validated naming template; captures are not meanings."""
    parts, end = [], 0
    for match in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template):
        parts.extend(((False, template[end:match.start()]), (True, match.group(1))))
        end = match.end()
    parts.append((False, template[end:]))
    if len(parts) > 129 or len(value) > 4096:
        return "indeterminate"
    stack = [(0, 0, dict(bindings))]
    scheduled = 1
    while stack:
        index, position, captures = stack.pop()
        if index == len(parts):
            if position == len(value):
                return "matches"
            continue
        is_token, part = parts[index]
        if not is_token or part in captures:
            literal = captures[part] if is_token else part
            if value.startswith(literal, position):
                scheduled += 1
                if scheduled > max_states:
                    return "indeterminate"
                stack.append((index + 1, position + len(literal), captures))
            continue
        stop = value.find("/", position)
        stop = len(value) if stop == -1 else stop
        for finish in range(position + 1, min(stop, position + 1024) + 1):
            segment = value[position:finish]
            if not _segment(segment):
                continue
            scheduled += 1
            if scheduled > max_states:
                return "indeterminate"
            stack.append((index + 1, finish, {**captures, part: segment}))
    return "mismatch"


def compare_model_names(project, policy_path, snapshot=None, *, model_id=None, context=None):
    """Compare model_file rules. Scope dimensions other than directory require user context."""
    context = {} if context is None else context
    if context and not model_id:
        raise PolicyError("Explicit scope context requires one selected model")
    if (not isinstance(context, dict) or len(context) > 32 or any(
            not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip()
            or len(k) > 256 or len(v) > 4096 for k, v in context.items())):
        raise PolicyError("Scope context requires bounded non-empty string fields")
    loaded = load_document(policy_path)
    policy = loaded["document"]
    if policy["kind"] != "policy":
        raise PolicyError("Comparison requires an explicitly selected policy document")
    snapshot = inspect_artifacts(project) if snapshot is None else snapshot
    manifest = snapshot.get("manifest", {})
    result = {"status": "needs_review", "policy_provenance": loaded["provenance"],
              "source": {k: manifest.get(k) for k in ("status", "identity", "freshness", "sha256", "source_kind",
                         "generated_at", "observed_at", "age_seconds", "dbt_schema_version", "dbt_version", "project_name")},
              "models": [], "questions": [], "truncated": False,
              "unchecked_targets": sorted({r["target"] for r in policy["naming"] if r["target"] != "model_file"}),
              "limitations": ["Structural matches do not establish token meanings or approval",
                              "Normal forms, semantic design and recorded exceptions are not evaluated",
                              "Only model_file rules are compared; directory scope is exact, not recursive"]}
    if (manifest.get("status") != "available" or manifest.get("identity") != "matched"
            or manifest.get("project_name") != project.name or not manifest.get("sha256")):
        result["status"] = "needs_context"
        result["questions"].append("Can you provide a supported manifest for this project?")
        return result
    if manifest.get("freshness") != "fresh":
        result["questions"].append("Should the manifest be refreshed before reviewing these results?")
    rules = [(i, r) for i, r in enumerate(policy["naming"]) if r["target"] == "model_file"]
    if len(rules) > 64:
        result["status"] = "needs_context"
        result["truncated"] = True
        result["questions"].append("Can the selected policy be narrowed to at most 64 model-file rules?")
        return result
    resources = [r for r in manifest.get("resources", []) if r.get("resource_type") == "model"
                 and r.get("package_name") == project.name and (model_id is None or r.get("unique_id") == model_id)]
    if not resources:
        result["status"] = "needs_context"
        result["questions"].append("Which current-project model should be compared? No selected models were available.")
        return result
    if len(resources) > 200:
        result["truncated"] = True
    for resource in sorted(resources, key=lambda r: r["unique_id"])[:200]:
        path = resource.get("original_file_path")
        item = {"model_id": resource["unique_id"], "status": "not_evaluated",
                "source_provenance": {"document": manifest["path"], "revision": manifest["sha256"],
                                      "locator": "resource:" + resource["unique_id"] + ":original_file_path"}}
        result["models"].append(item)
        try:
            resolve_name(NamingRule("path", path, {}, {"source": "snapshot"}), {})
        except NamingError:
            item["question"] = "Can you supply a valid relative model file path?"
            continue
        known = {"directory": str(PurePosixPath(path).parent)}
        if "directory" in context and context["directory"] != known["directory"]:
            raise PolicyError("Explicit directory context conflicts with the manifest path")
        known.update(context)
        item["path"] = path
        item["scope_context"] = known
        item["scope_sources"] = {key: "caller" if key in context else "manifest" for key in known}
        applicable, uncertain = [], []
        for index, rule in rules:
            scope = rule.get("scope", {})
            if any(key in known and known[key] != value for key, value in scope.items()):
                continue
            missing = sorted(set(scope) - set(known))
            if missing:
                uncertain.append({"rule_id": rule["id"], "missing_dimensions": missing})
            else:
                applicable.append((index, rule))
        if uncertain:
            item.update(status="needs_scope", unresolved_rules=uncertain,
                        question="What scope values apply to this model before choosing a rule?")
        elif len(applicable) > 1:
            item.update(status="rule_conflict", rule_ids=[r["id"] for _, r in applicable],
                        question="Several rules apply. Should their scopes be narrowed or an explicit precedence decision recorded?")
        elif not applicable:
            item.update(status="uncovered", question="Should an existing rule cover this model, or is a separate convention needed?")
        else:
            index, rule = applicable[0]
            compared_value = path if "/" in rule["template"] else PurePosixPath(path).name
            status = match_template(rule["template"], compared_value, rule.get("bindings", {}))
            item.update(status=status, rule_id=rule["id"],
                        compared_value=compared_value,
                        rule_provenance={**loaded["provenance"], "locator": f"/naming/{index}"})
            if status == "mismatch":
                item["question"] = "Is this a model-specific exception, a model change, or a proposed wider policy change?"
            elif status == "indeterminate":
                item["question"] = "Can this template be made less ambiguous or token values supplied before comparing it?"
    return result
