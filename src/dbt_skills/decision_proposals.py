"""Pending decision proposals and reviewable patches; never approvals or file writes."""

import copy
import hashlib
import json

from .modelling_naming import NamingError, NamingRule, resolve_name
from .modelling_policy import PolicyError, load_document, validate_document
from .project_artifacts import inspect_artifacts


def prepare_decision(project, policy_path, rule_id, model_id, rationale, *,
                     decision="exception", template=None, proposals_path=None, snapshot=None):
    """Propose one-model exception by default; wider template changes require explicit intent."""
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4096:
        raise PolicyError("A bounded, non-empty rationale is required")
    if decision not in ("exception", "standard_change"):
        raise PolicyError("Choose an exception or an explicit standard change")
    if (decision == "exception" and template is not None) or (decision == "standard_change" and template is None):
        raise PolicyError("Only an explicit standard change requires a replacement template")
    loaded = load_document(policy_path)
    policy = loaded["document"]
    if policy["kind"] != "policy":
        raise PolicyError("Select a declared policy before proposing a decision")
    matches = [(i, r) for i, r in enumerate(policy["naming"]) if r["id"] == rule_id]
    if not matches or matches[0][1]["target"] != "model_file":
        raise PolicyError("Select an existing model-file naming rule")
    index, rule = matches[0]
    snapshot = inspect_artifacts(project) if snapshot is None else snapshot
    manifest = snapshot.get("manifest", {})
    if (manifest.get("status") != "available" or manifest.get("identity") != "matched"
            or manifest.get("project_name") != project.name or not manifest.get("sha256")):
        raise PolicyError("A supported project-matched manifest is required")
    models = [r for r in manifest.get("resources", []) if r.get("unique_id") == model_id
              and r.get("resource_type") == "model" and r.get("package_name") == project.name]
    if len(models) != 1:
        raise PolicyError("Select one current-project model from the manifest")
    path = models[0].get("original_file_path")
    try:
        resolve_name(NamingRule("path", path, {}, {"source": "manifest"}), {})
    except NamingError:
        raise PolicyError("The selected model has no valid relative file path") from None
    policy_evidence = {"document": loaded["provenance"]["document"], "revision": loaded["provenance"]["sha256"],
                       "locator": f"/naming/{index}"}
    manifest_evidence = {"document": manifest["path"], "revision": manifest["sha256"],
                         "locator": f"resource:{model_id}:original_file_path"}
    for key in ("generated_at", "observed_at"):
        if isinstance(manifest.get(key), str) and manifest[key]:
            manifest_evidence[key] = manifest[key]
    record = {"rule_id": rule_id, "decision": decision, "models": [model_id] if decision == "exception" else [],
              "trigger_model": model_id, "observed_path": path, "rationale": rationale,
              "rule_scope": copy.deepcopy(rule.get("scope", {})), "previous_template": rule["template"],
              "evidence": [policy_evidence, manifest_evidence]}
    proposed_policy, patch = None, []
    if decision == "standard_change":
        if template == rule["template"]:
            raise PolicyError("The replacement template must change the selected rule")
        proposed_policy = copy.deepcopy(policy)
        proposed_policy["naming"][index]["template"] = template
        validate_document(proposed_policy)
        record["proposed_template"] = template
        patch = [{"op": "test", "path": f"/naming/{index}/template", "value": rule["template"]},
                 {"op": "replace", "path": f"/naming/{index}/template", "value": template}]
    # Stable for the same source revisions and intent, independent of retrieval time.
    identity = {k: v for k, v in record.items() if k != "evidence"}
    identity["revisions"] = [policy_evidence["revision"], manifest_evidence["revision"]]
    record["id"] = "proposal_" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    existing = load_document(proposals_path) if proposals_path is not None else None
    if existing is not None and existing["document"]["kind"] != "proposals":
        raise PolicyError("Select a pending-proposals document, not approved decisions")
    document = copy.deepcopy(existing["document"]) if existing else {"schema_version": 1, "kind": "proposals", "records": []}
    document["records"].append(record)
    validate_document(document)
    return {"status": "pending_review", "proposal_document": document, "policy_patch": patch,
            "proposed_policy": proposed_policy, "policy_base": loaded["provenance"],
            "proposals_base": existing["provenance"] if existing else None,
            "proposals_patch": [{"op": "add", "path": "/records/-", "value": record}] if existing else
                               [{"op": "add", "path": "", "value": document}],
            "source": {k: manifest.get(k) for k in ("sha256", "freshness", "generated_at", "observed_at", "age_seconds")},
            "review_requirements": ["Confirm rule applicability and scope for the trigger model",
                                    "Verify evidence and base hashes before adopting any change",
                                    "Record human approval separately; a pending proposal is not authority"],
            "limitations": ["Template changes preserve scope and use already declared tokens",
                            "No files, policy or approved decisions are updated; patches are review-only",
                            "Model-specific exceptions do not change the general naming rule"]}
