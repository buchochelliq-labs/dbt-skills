"""Conservative naming hypotheses from the shared manifest snapshot, never raw SQL."""

from collections import defaultdict
from pathlib import PurePosixPath
import re

from .modelling_naming import NamingError, NamingRule, resolve_name
from .modelling_policy import discover_policy_files
from .project_artifacts import inspect_artifacts


def infer_conventions(project, snapshot=None) -> dict:
    """Produce non-authoritative drafts; hosts may reuse a validated inspect_artifacts result.

    Only current-project model file paths are analysed. Meanings of filename segments,
    modelling styles and normal forms are deliberately left as questions.
    """
    snapshot = inspect_artifacts(project) if snapshot is None else snapshot
    manifest = snapshot.get("manifest", {})
    inventory = discover_policy_files(project.root, include_references=True)
    result = {
        "status": "needs_review", "truncated": inventory["truncated"],
        "source": {key: manifest.get(key) for key in ("status", "identity", "freshness", "sha256")},
        "existing_documents": {key: inventory[key][:16] for key in ("candidates", "references")},
        "observations": {"schema_version": 1, "kind": "observations", "records": []},
        "proposed_policy": {"schema_version": 1, "kind": "policy", "tokens": {}, "naming": [], "modelling": []},
        "questions": [{"kind": "authority", "question": "Which existing policy, configuration or decision document is authoritative?"}],
        "limitations": ["Drafts are hypotheses, not approved standards",
                        "Only model filename layouts are inferred; SQL and document prose are not read",
                        "Underscore, hyphen and dot delimiters are recognised; semantic token meanings are unknown",
                        "A manifest may differ from current files even when its age is fresh"],
    }
    if any(len(inventory[key]) > 16 for key in ("candidates", "references")):
        result["truncated"] = True
    if (manifest.get("status") != "available" or manifest.get("identity") != "matched"
            or manifest.get("project_name") != project.name or not manifest.get("sha256")):
        result["status"] = "needs_context"
        result["questions"].append({"kind": "context", "question": "Can you provide a supported manifest for this project before inferring conventions?"})
        return result
    if manifest.get("freshness") != "fresh":
        result["questions"].append({"kind": "freshness", "question": "Should the manifest be refreshed before reviewing these naming hypotheses?"})
    result["questions"].append({"kind": "modelling", "question": "What modelling style and normal-form target, if any, apply to each layer or domain?"})
    groups = defaultdict(dict)
    skipped = 0
    resources = manifest.get("resources", [])
    if len(resources) > 10000:
        result["status"] = "needs_context"
        result["truncated"] = True
        return result
    for resource in resources:
        if resource.get("resource_type") != "model" or resource.get("package_name") != project.name:
            continue
        path = resource.get("original_file_path")
        identity = resource.get("unique_id")
        if not isinstance(path, str) or not isinstance(identity, str) or not identity or len(identity) > 4000:
            skipped += 1
            continue
        try:
            # The naming primitive rejects traversal, expressions, controls and absolute paths.
            resolve_name(NamingRule("path-check", path, {}, {"source": "snapshot"}), {})
        except NamingError:
            skipped += 1
            continue
        parsed = PurePosixPath(path)
        if parsed.suffix.lower() != ".sql":
            continue
        current = groups[str(parsed.parent)].get(path)
        # Versioned resources can share files; one filename is one observation.
        if current is None or identity < current:
            groups[str(parsed.parent)][path] = identity
    result["skipped_model_paths"] = skipped
    if len(groups) > 16:
        result["truncated"] = True
    for directory, paths in sorted(groups.items())[:16]:
        layouts = defaultdict(list)
        for path in sorted(paths):
            parts = re.split(r"([_.-]+)", PurePosixPath(path).stem)
            if not all(parts[::2]) or len(parts) > 17:
                continue
            layouts[(tuple(parts[1::2]), PurePosixPath(path).suffix)].append((path, parts))
        ranked = sorted(layouts.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        if not ranked or len(ranked[0][1]) < 2:
            continue
        if len(ranked) > 1 and len(ranked[0][1]) == len(ranked[1][1]):
            result["questions"].append({"kind": "conflict", "directory": directory,
                                        "question": "Several filename layouts are equally common here. Which should apply, and where?"})
            continue
        matches = ranked[0][1]
        template_parts, tokens = [], {}
        for index, part in enumerate(matches[0][1]):
            if index % 2 or all(parts[index] == part for _, parts in matches):
                template_parts.append(part)
            else:
                token = f"token_{len(tokens) + 1}"
                tokens[token] = f"What does {token} mean in this filename layout?"
                template_parts.append("{" + token + "}")
        template = (directory + "/" if directory != "." else "") + "".join(template_parts) + PurePosixPath(matches[0][0]).suffix
        number = len(result["proposed_policy"]["naming"]) + 1
        rule_id = f"candidate_{number}"
        provenance = {"document": manifest["path"], "revision": manifest["sha256"]}
        # Tokens are rule-specific so human meanings need not agree between directories.
        renames = {token: f"{rule_id}_{token}" for token in tokens}
        for old, new in renames.items():
            template = template.replace("{" + old + "}", "{" + new + "}")
        candidate_tokens = {new: tokens[old] for old, new in renames.items()}
        try:
            resolve_name(NamingRule(rule_id, template, candidate_tokens, provenance), {})
        except NamingError:
            result["truncated"] = True
            continue
        def evidence(path):
            return {**provenance, "locator": "resource:" + paths[path] + ":original_file_path"}
        matched_paths = {path for path, _ in matches}
        counterexamples = sorted(set(paths) - matched_paths)
        record = {"id": rule_id, "statement": f"Candidate filename layout: {template}",
                  "confidence": "medium" if len(matches) >= 3 and not counterexamples and manifest.get("freshness") == "fresh" else "low",
                  "evidence": [evidence(path) for path, _ in matches[:8]],
                  "counterexamples": [evidence(path) for path in counterexamples[:8]]}
        if len(record["statement"]) > 4096:
            result["truncated"] = True
            continue
        result["observations"]["records"].append(record)
        if len(matches) > 8 or len(counterexamples) > 8:
            result["truncated"] = True
        for old, new in renames.items():
            result["proposed_policy"]["tokens"][new] = tokens[old]
            result["questions"].append({"kind": "token", "rule_id": rule_id, "token": new, "question": tokens[old]})
        result["proposed_policy"]["naming"].append({"id": rule_id, "target": "model_file", "template": template,
                                                    "scope": {"directory": directory}})
        result["questions"].append({"kind": "scope", "rule_id": rule_id,
                                    "question": "Is this layout an intended rule for this directory, or are the matches and exceptions incidental?"})
    if len(result["questions"]) > 64:
        result["questions"] = result["questions"][:64]
        result["truncated"] = True
    return result
