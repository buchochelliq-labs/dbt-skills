"""Authoritative UOL application commands. Browser inputs never mutate repository state."""

from copy import deepcopy
from datetime import datetime, timezone
import math
from .workspace_store import WorkspaceError
from .application_resolver import resolve_context
from .native_publication import (
    validate_proposal,
    export_handoff,
    fingerprint,
    verify_readback,
)

HOUR = 3600000


def item(s, collection, identifier):
    found = next((x for x in s[collection] if x["id"] == identifier), None)
    if found is None:
        raise WorkspaceError("Object unavailable")
    return found


def ident(s, prefix):
    value = f"{prefix}-{s['sequence']}"
    s["sequence"] += 1
    return value


def invalidate(s):
    s["configVersion"] += 1
    s["cache"] = []


def permitted(x, reader):
    return not x.get("hidden", False) and not (
        reader == "restricted" and x.get("restricted", False)
    )


def visible_state(state, reader):
    s = deepcopy(state)
    s["knowledge"] = [x for x in s["knowledge"] if permitted(x, reader)]
    s["assets"] = [x for x in s["assets"] if permitted(x, reader)]
    kids = {x["id"] for x in s["knowledge"]}
    aids = {x["id"] for x in s["assets"]}
    ids = kids | aids | {d["id"] for d in s["domains"]}
    for k in s["knowledge"]:
        k["related"] = [i for i in k["related"] if i in kids]
    for a in s["assets"]:
        a["knowledgeIds"] = [i for i in a["knowledgeIds"] if i in kids]
        if a["parent"] not in aids:
            a["parent"] = None
    s["mappings"] = [
        m for m in s["mappings"] if m["knowledgeId"] in kids and m["assetId"] in aids
    ]
    s["relationships"] = [
        r for r in s["relationships"] if r["source"] in ids and r["target"] in ids
    ]
    hidden_targets = {a["id"] for a in state["assets"]} - aids
    s["targets"] = [
        t
        for t in s["targets"]
        if t["id"] not in hidden_targets
        and (reader == "steward" or t["audience"] != "Finance stewards")
    ]
    tids = {t["id"] for t in s["targets"]}
    s["proposals"] = [
        p for p in s["proposals"] if p["originId"] in kids and p["targetId"] in tids
    ]
    pids = {p["id"] for p in s["proposals"]}
    s["deliveries"] = [d for d in s["deliveries"] if d["proposalId"] in pids]
    assets = {a["id"]: a for a in s["assets"]}
    providers = {p["id"]: p for p in s["providers"]}

    def cache_visible(c):
        evidence = c["fact"]["evidence"]
        provider = providers.get(evidence["providerId"])
        if (c["reader"] != reader or evidence["reader"] != reader or c["knowledgeId"] not in kids
                or not provider or not provider["enabled"] or provider["health"] in ("denied", "malformed")):
            return False
        if evidence["assetId"]:
            asset = assets.get(evidence["assetId"])
            if asset is None:
                return False
            if asset.get("sourceEvidence"):
                group = "columns" if evidence.get("fieldPath") else "relation"
                source = asset["sourceEvidence"].get(group)
                if not source or (evidence["providerId"], evidence["sourceRevision"], evidence["sourcePath"]) != (
                    source["provider"], source["revision"], source["document"] + "#" + source["locator"]
                ):
                    return False
        return True

    s["cache"] = [c for c in s["cache"] if cache_visible(c)]
    visible_facts = {(c["knowledgeId"], c["fact"]["id"], c["fact"]["evidence"]["providerId"]) for c in s["cache"]}
    s["observations"] = [o for o in s["observations"]
                         if (o["knowledgeId"], o["factId"], o["providerId"]) in visible_facts]
    for p in s["pages"]:
        p["relatedAssets"] = [i for i in p["relatedAssets"] if i in aids]
    return s


def ancestors(s, id):
    out = []
    seen = set()
    while id:
        if id in seen:
            raise WorkspaceError("Domain cycle")
        seen.add(id)
        d = item(s, "domains", id)
        out.insert(0, d)
        id = d["parent"]
    return out


def validity(from_, to=None):
    for value in [from_, to]:
        if value:
            try:
                if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
                    raise ValueError()
            except Exception:
                raise WorkspaceError("Use a real calendar date YYYY-MM-DD") from None
    if not from_ or to and to < from_:
        raise WorkspaceError("Invalid validity interval")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{label} is required")
    return value.strip()


def ttl(value):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not 0 < value <= 8760
    ):
        raise WorkspaceError("TTL must be positive and at most 8760 hours")
    return value


def patch_allowed(patch, allowed):
    if not isinstance(patch, dict) or set(patch) - set(allowed):
        raise WorkspaceError("Unsupported edit fields")


def create_proposal(s, args, reader):
    k = item(s, "knowledge", args["originId"])
    t = item(s, "targets", args["targetId"])
    if not permitted(k, reader):
        raise WorkspaceError("Proposal unavailable")
    a = next((a for a in s["assets"] if a["id"] == t["id"]), None)
    if a and not permitted(a, reader):
        raise WorkspaceError("Proposal unavailable")
    field = args["field"]
    after = deepcopy(args["after"])
    if field not in [
        "description",
        "tags",
        "yaml",
        "serialized_space",
        "summary",
        "page",
        "projection",
    ]:
        raise WorkspaceError("Unsupported target field")
    if args.get("expectedRevision", t["revision"]) != t["revision"]:
        raise WorkspaceError("Target changed while editing; reload complete target")
    if t["content"].get(field) == after:
        raise WorkspaceError("Make a change before proposing")
    if field == "tags" and (
        not isinstance(after, dict)
        or any(not isinstance(v, str) for v in after.values())
    ):
        raise WorkspaceError("Tags require string values")
    if field in ["description", "summary"]:
        text(after, "Description")
    if field == "serialized_space" and (
        not isinstance(after, dict)
        or after.get("version") != 2
        or any(
            not isinstance(after.get(key), dict)
            for key in ["config", "data_sources", "instructions"]
        )
    ):
        raise WorkspaceError("Complete Genie version 2 configuration required")
    if field == "page":
        for key in ["name", "owner", "body"]:
            text(after.get(key), key)
    if field == "yaml":
        if (
            not isinstance(after, dict)
            or str(after.get("version")) != "1.1"
            or not isinstance(after.get("source"), str)
            or not isinstance(after.get("measures"), list)
            or not after["measures"]
        ):
            raise WorkspaceError("Supported metric YAML 1.1 required")
        for m in after["measures"]:
            if not isinstance(m, dict):
                raise WorkspaceError("Malformed metric measure")
            text(m.get("name"), "Measure name")
            text(m.get("expr"), "Measure expression")
    p = dict(
        id=ident(s, "proposal"),
        originId=k["id"],
        originRevision=k["version"],
        targetId=t["id"],
        field=field,
        before=deepcopy(t["content"].get(field)),
        after=after,
        expectedRevision=t["revision"],
        reason=text(args.get("reason"), "Reason"),
        audience=args.get("audience") or t["audience"],
        state="Draft",
        dependencies=args.get("dependencies", []),
        evidence=f"{k['originId']}@{k['version']}",
    )
    if t.get("nativeObservation"):
        observed = t["nativeObservation"]
        if observed.get("origin_id") != k["originId"]:
            raise WorkspaceError("Native target is bound to a different UOL origin")
        p["nativeBaseFingerprint"] = observed["fingerprint"]
    s["proposals"].append(p)
    return p


def native_target(t):
    if t["kind"] not in ["genie", "table", "view", "unity_catalog"]:
        raise WorkspaceError("Native observation does not support this target kind")
    return {
        "kind": "genie" if t["kind"] == "genie" else "unity_catalog",
        "id": (
            t["name"]
            if t["id"].startswith("native:genie:") or t["kind"] != "genie"
            else t["id"]
        ),
    }


def native_proposal(s, p):
    t = item(s, "targets", p["targetId"])
    k = item(s, "knowledge", p["originId"])
    observed = t.get("nativeObservation")
    if not observed or not p.get("nativeBaseFingerprint"):
        raise WorkspaceError(
            "Observe the native target, then reopen and review a new proposal"
        )
    if observed.get("origin_id") != k["originId"]:
        raise WorkspaceError("Native origin mapping differs from proposal origin")
    field = (
        "comment"
        if t["kind"] != "genie" and p["field"] == "description"
        else p["field"]
    )
    allowed = (
        ["title", "description", "serialized_space", "warehouse_id", "parent_path"]
        if t["kind"] == "genie"
        else ["comment", "tags"]
    )
    if field not in allowed:
        raise WorkspaceError("Field is unsupported by native observation")
    return {
        "schema_version": 1,
        "target": native_target(t),
        "origin": {"id": k["originId"], "revision": str(p["originRevision"])},
        "base_fingerprint": p["nativeBaseFingerprint"],
        "changes": [{"id": p["id"], "path": [field], "value": p["after"]}],
        "selected_change_ids": [p["id"]],
        "intended_audience": [p["audience"]],
    }


def refresh_native_target(t, adapter):
    if adapter is None:
        raise WorkspaceError("No authenticated native observation adapter configured")
    try:
        target = native_target(t)
        observed = adapter.read_target(target)
        if (
            observed.get("target") != target
            or not isinstance(observed.get("document"), dict)
            or observed.get("fingerprint") != fingerprint(observed["document"])
            or observed.get("permissions", {}).get("read") is not True
            or not isinstance(observed.get("origin_id"), str)
        ):
            raise ValueError()
    except Exception:
        raise WorkspaceError("Native observation failed; no write attempted") from None
    if observed != t.get("nativeObservation"):
        t["revision"] += 1
    t["nativeObservation"] = deepcopy(observed)
    t["content"] = deepcopy(observed["document"])
    if target["kind"] == "unity_catalog":
        t["content"]["description"] = t["content"].pop("comment", None)
    t["permission"] = (
        "permitted" if observed["permissions"].get("write") is True else "unknown"
    )
    t["audience"] = (
        observed["audience"][0]
        if isinstance(observed.get("audience"), list) and len(observed["audience"]) == 1
        else "Unknown"
    )
    t["atomic"] = bool(target["kind"] == "genie" and observed.get("revision_token"))
    t["capability"] = "unsupported"
    return observed


def execute(
    s,
    name,
    payload,
    *,
    reader="steward",
    simulation=False,
    catalog_resolve=None,
    native_adapter=None,
):
    if name == "context.resolve":
        return resolve_context(
            s,
            payload["request"],
            reader=reader,
            simulation=simulation,
            catalog_resolve=catalog_resolve,
        )
    if reader != "steward":
        raise WorkspaceError("This reader cannot modify metadata")
    if not simulation:
        s["clock"] = int(datetime.now(timezone.utc).timestamp() * 1000)
    if name == "domain.create":
        item(s, "domains", payload["parent"])
        n = text(payload["name"], "Name")
        if any(
            d["parent"] == payload["parent"] and d["name"].casefold() == n.casefold()
            for d in s["domains"]
        ):
            raise WorkspaceError("Sibling name already exists")
        d = dict(
            id=ident(s, "domain"),
            name=n,
            parent=payload["parent"],
            description=payload.get("description", ""),
            owner=None,
            technicalOwner=None,
            steward=None,
            providerPolicy=None,
            ttl=None,
        )
        s["domains"].append(d)
        return d
    if name == "domain.update":
        d = item(s, "domains", payload["id"])
        patch = payload["patch"]
        patch_allowed(
            patch,
            [
                "name",
                "parent",
                "description",
                "owner",
                "technicalOwner",
                "steward",
                "providerPolicy",
                "ttl",
            ],
        )
        parent = patch.get("parent", d["parent"])
        n = text(patch.get("name", d["name"]), "Name")
        if d["parent"] is None and parent is not None:
            raise WorkspaceError("Root must remain root")
        if d["parent"] is not None and not parent:
            raise WorkspaceError("Parent required")
        if parent and d["id"] in [x["id"] for x in ancestors(s, parent)]:
            raise WorkspaceError("Domain cannot move into itself or descendants")
        if any(
            x["id"] != d["id"]
            and x["parent"] == parent
            and x["name"].casefold() == n.casefold()
            for x in s["domains"]
        ):
            raise WorkspaceError("Sibling name already exists")
        if patch.get("ttl") is not None:
            ttl(patch["ttl"])
        d.update(patch)
        d.update(name=n, parent=parent)
        invalidate(s)
        return d
    if name == "knowledge.create":
        d = item(s, "domains", payload["domain"])
        id = ident(s, "knowledge")
        definition = text(payload["definition"], "Definition")
        kind = payload["type"]
        if kind not in ["Concept", "Business term", "Metric", "Rule", "Page"]:
            raise WorkspaceError("Unknown knowledge type")
        k = dict(
            id=id,
            name=text(payload["name"], "Name"),
            type=kind,
            domain=d["id"],
            memberships=[],
            summary=definition,
            definition=definition,
            scope="Enterprise",
            grain="",
            status="Draft",
            origin="Curated",
            version=1,
            owner=d["owner"] or "",
            source="Authored definitions",
            sourcePath=f"local/{id}.yaml",
            effective="Pending approval",
            validFrom=datetime.fromtimestamp(s["clock"] / 1000, timezone.utc)
            .date()
            .isoformat(),
            synonyms=[],
            related=[],
            originId=f"uol:{id}",
            history=[],
        )
        s["knowledge"].append(k)
        if kind == "Page" and s["providers"]:
            provider = next(
                (p for p in s["providers"] if p["kind"] == "authored"),
                s["providers"][0],
            )
            s["targets"].append(
                dict(
                    id=id,
                    name=k["name"],
                    kind="page",
                    providerId=provider["id"],
                    revision=0,
                    content={},
                    capability="unsupported",
                    permission="unknown",
                    audience="Human import reviewer",
                    atomic=False,
                    failNext=False,
                    mismatchNext=False,
                    origins={},
                )
            )
        return k
    if name == "knowledge.revise":
        k = item(s, "knowledge", payload["id"])
        patch = deepcopy(payload["patch"])
        # Full editor object is accepted, but immutable fields cannot be overwritten.
        patch_allowed(
            patch,
            k.keys()
            | {
                "validTo",
                "formula",
                "unit",
                "aggregation",
                "dimensions",
                "logic",
                "exclusions",
                "ttl",
            },
        )
        for key in [
            "id",
            "originId",
            "origin",
            "source",
            "sourcePath",
            "history",
            "version",
            "status",
            "hidden",
            "restricted",
        ]:
            if key in patch and patch[key] != k.get(key):
                raise WorkspaceError("Immutable provenance cannot be edited")
            patch.pop(key, None)
        next_ = {**k, **patch}
        text(next_["definition"], "Definition")
        item(s, "domains", next_["domain"])
        validity(next_["validFrom"], next_.get("validTo"))
        members = next_["memberships"]
        if (
            len(set(members)) != len(members)
            or next_["domain"] in members
            or any(x not in {d["id"] for d in s["domains"]} for x in members)
        ):
            raise WorkspaceError("Invalid additional memberships")
        k["history"].append(
            dict(
                revision=k["version"],
                definition=k["definition"],
                status=k["status"],
                origin=k["origin"],
                changedAt=s["clock"],
            )
        )
        k.update(patch)
        k["version"] += 1
        k["status"] = "Draft"
        invalidate(s)
        return k
    if name == "knowledge.approve":
        k = item(s, "knowledge", payload["id"])
        k["status"] = "Approved"
        invalidate(s)
        return k
    if name in ["provider.update", "provider.create"]:
        if name == "provider.create":
            if not simulation:
                raise WorkspaceError(
                    "Configure provider credentials and exact project mappings in the operator catalog configuration, then sync"
                )
            p = deepcopy(payload["provider"])
            p["id"] = ident(s, "provider")
            s["providers"].append(p)
        else:
            p = item(s, "providers", payload["id"])
            patch = payload["patch"]
            patch_allowed(
                patch,
                [
                    "name",
                    "enabled",
                    "ttl",
                    "scope",
                    "health",
                    "workspace",
                    "metastore",
                    "kind",
                ],
            )
            if not simulation and any(
                k in patch and patch[k] != p.get(k)
                for k in ["health", "workspace", "metastore", "kind", "scope"]
            ):
                raise WorkspaceError(
                    "Native identity and metadata scope require operator configuration and sync"
                )
            p.update(patch)
        ttl(p["ttl"])
        text(p["name"], "Provider name")
        invalidate(s)
        return p
    if name == "provider.reorder":
        p = item(s, "providers", payload["id"])
        i = s["providers"].index(p)
        delta = payload["delta"]
        if delta not in [-1, 1]:
            raise WorkspaceError("Order must move one position")
        j = i + delta
        if 0 <= j < len(s["providers"]):
            s["providers"][i], s["providers"][j] = s["providers"][j], s["providers"][i]
        invalidate(s)
        return True
    if name == "clock.advance":
        if not simulation:
            raise WorkspaceError("Real clock cannot be advanced")
        s["clock"] += ttl(payload["hours"]) * HOUR
        return True
    if name == "cache.clear":
        s["cache"] = []
        return True
    if name == "ttl.dismiss":
        s["ttlDismissed"] = True
        return True
    if name == "ttl.accept":
        k = item(s, "knowledge", payload["knowledgeId"])
        k["ttl"] = ttl(payload["hours"])
        s["ttlDismissed"] = True
        invalidate(s)
        return k
    if name == "mapping.save":
        m = deepcopy(payload["mapping"])
        k = item(s, "knowledge", m["knowledgeId"])
        a = item(s, "assets", m["assetId"])
        if not permitted(k, reader) or not permitted(a, reader):
            raise WorkspaceError("Mapping endpoints unavailable")
        for f in ["attribute", "scope", "evidence"]:
            text(m.get(f), f)
        if m.get("fieldPath") and m["fieldPath"] not in [
            f["path"] for f in a["fields"]
        ]:
            raise WorkspaceError("Field not declared on containing asset")
        validity(m["validFrom"], m.get("validTo"))
        m.update(id=ident(s, "mapping"), status="Draft")
        s["mappings"].append(m)
        invalidate(s)
        return m
    if name == "mapping.review":
        m = item(s, "mappings", payload["id"])
        k = item(s, "knowledge", m["knowledgeId"])
        a = item(s, "assets", m["assetId"])
        if not permitted(k, reader) or not permitted(a, reader):
            raise WorkspaceError("Mapping endpoints unavailable")
        field = m.get("fieldPath")
        if field and field not in {f["path"] for f in a["fields"]}:
            raise WorkspaceError("Field not declared on containing asset; sync metadata before review")
        if not simulation:
            if catalog_resolve is None:
                raise WorkspaceError("Current source metadata is required for review")
            current = catalog_resolve(a["id"], ["relation", "columns"] if field else ["relation"])
            selected = current.get("selected", {})
            if current.get("status") != "complete" or not selected.get("relation"):
                raise WorkspaceError("Current source metadata is unavailable for review")
            if field and field not in {c.get("name") for c in selected.get("columns", {}).get("value", [])}:
                raise WorkspaceError("Mapped field is absent from current source metadata")
        m["status"] = "Approved"
        invalidate(s)
        return m
    if name == "mapping.remove":
        m = item(s, "mappings", payload["id"])
        if m["status"] != "Draft":
            raise WorkspaceError("Only draft mappings can be removed")
        s["mappings"].remove(m)
        invalidate(s)
        return True
    if name == "relationship.save":
        r = payload["relationship"]
        old = item(s, "relationships", r["id"])
        for key in ["label", "scope"]:
            text(r.get(key), key)
        old.update({k: r[k] for k in ["label", "scope", "cardinality"]})
        old.update(approval="Draft", provenance="UOL reviewed workspace edit")
        invalidate(s)
        return old
    if name == "page.save":
        page = deepcopy(payload["page"])
        for f in ["name", "owner", "body"]:
            text(page.get(f), f)
        item(s, "domains", page["domain"])
        allowed = {a["id"] for a in s["assets"] if permitted(a, reader)}
        if not set(page["relatedAssets"]) <= allowed:
            raise WorkspaceError("Related asset unavailable")
        old = next((p for p in s["pages"] if p["id"] == page["id"]), None)
        if old:
            old.update(page)
        else:
            s["pages"].append(page)
        return page
    if name == "target.refresh":
        if simulation:
            raise WorkspaceError("Native observations require a real workspace")
        target = item(s, "targets", payload["id"])
        asset = next((a for a in s["assets"] if a["id"] == target["id"]), None)
        if asset and not permitted(asset, reader):
            raise WorkspaceError("Target unavailable")
        return refresh_native_target(target, native_adapter)
    if name in ["proposal.check", "proposal.reconcile"]:
        if simulation:
            raise WorkspaceError("Native observations require a real workspace")
        p = item(s, "proposals", payload["id"])
        if native_adapter is None:
            raise WorkspaceError(
                "No authenticated native observation adapter configured"
            )
        origin = item(s, "knowledge", p["originId"])
        asset = next((a for a in s["assets"] if a["id"] == p["targetId"]), None)
        if not permitted(origin, reader) or asset and not permitted(asset, reader):
            raise WorkspaceError("Proposal unavailable")
        proposal = native_proposal(s, p)
        checked = (
            validate_proposal(proposal, native_adapter)
            if name == "proposal.check"
            else verify_readback(proposal, native_adapter)
        )
        p["nativeResult"] = {**checked, "operation": name, "observed_at": s["clock"]}
        if checked["status"] == "conflict":
            p["state"] = "Conflict"
        # Matching observed values are not a save acknowledgement or delivery.
        return p["nativeResult"]
    if name == "proposal.create":
        if not simulation:
            target = item(s, "targets", payload["proposal"]["targetId"])
            if target["kind"] in [
                "genie",
                "table",
                "view",
                "unity_catalog",
            ] and not target.get("nativeObservation"):
                raise WorkspaceError(
                    "Observe the native target before preparing an exact proposal"
                )
        return create_proposal(s, payload["proposal"], reader)
    if name == "projection.propose":
        ds = ancestors(s, payload["domainId"])
        choice = payload["choice"]
        names = [d["name"] for d in ds[1:]]
        if choice not in ["ancestor", "flatten", "uol-only"]:
            raise WorkspaceError("Choose an explicit projection")
        sub = (
            "-".join(names[1:])
            if choice == "flatten"
            else (names[1] if len(names) > 1 else None)
        )
        proj = dict(
            uolId=payload["domainId"],
            fullPath=" / ".join(d["name"] for d in ds),
            choice=choice,
            nativeDomain=(
                None if choice == "uol-only" else (names[0] if names else None)
            ),
            nativeSubdomain=None if choice == "uol-only" else sub,
            lostDepth=max(0, len(names) - 2),
            tags=(
                {}
                if choice == "uol-only" or not names
                else {names[0]: "", **({names[0] + "/" + sub: ""} if sub else {})}
            ),
        )
        origin = next(
            (k for k in s["knowledge"] if k["domain"] == payload["domainId"]), None
        )
        target = next((t for t in s["targets"] if t["kind"] == "domain"), None)
        if not origin or not target:
            raise WorkspaceError(
                "No configured native domain target and owned definition; export the projection for review"
            )
        return create_proposal(
            s,
            dict(
                originId=origin["id"],
                targetId=target["id"],
                field="projection",
                after=proj,
                reason="Explicit deep hierarchy projection",
            ),
            reader,
        )
    if name == "proposal.review":
        p = item(s, "proposals", payload["id"])
        k = item(s, "knowledge", p["originId"])
        if (
            p["state"] not in ["Draft", "Conflict"]
            or k["version"] != p["originRevision"]
        ):
            raise WorkspaceError("Proposal or origin changed; revise before review")
        p.update(
            state="Reviewed",
            reviewedAt=s["clock"],
            reviewDecision="Reviewed by local workspace owner",
        )
        return p
    if name == "proposal.rebase":
        p = item(s, "proposals", payload["id"])
        t = item(s, "targets", p["targetId"])
        if p["field"] == "serialized_space":
            raise WorkspaceError(
                "Reopen Genie editor and preserve latest complete configuration"
            )
        p.update(
            before=deepcopy(t["content"].get(p["field"])),
            expectedRevision=t["revision"],
            state="Draft",
        )
        if t.get("nativeObservation"):
            p["nativeBaseFingerprint"] = t["nativeObservation"]["fingerprint"]
        p.pop("reviewDecision", None)
        p.pop("nativeResult", None)
        return p
    if name == "proposal.export":
        p = item(s, "proposals", payload["id"])
        if p["state"] not in ["Reviewed", "Unsupported", "Exported"]:
            raise WorkspaceError("Review before exporting selected change")
        p["state"] = "Exported"
        return {
            "schema_version": 1,
            "simulation": simulation,
            "review_required": True,
            "native_write_performed": False,
            "proposal": deepcopy(p),
            "manual_step": "Verify native permissions, audience and current revision before applying; read back actual native state.",
        }
    if name == "target.simulate":
        if not simulation:
            raise WorkspaceError("Simulation is disabled")
        t = item(s, "targets", payload["id"])
        scenario = payload["scenario"]
        if scenario == "drift":
            t["revision"] += 1
            t["content"]["description"] = "Changed independently after review"
        elif scenario == "failure":
            t["failNext"] = True
        elif scenario == "mismatch":
            t["mismatchNext"] = True
        elif scenario == "unsupported":
            t["capability"] = "unsupported"
        else:
            raise WorkspaceError("Unknown simulation")
        return t
    if name == "proposal.deliver":
        for id in payload["ids"]:
            p = item(s, "proposals", id)
            if p["state"] not in ["Reviewed", "Failed"]:
                continue
            t = item(s, "targets", p["targetId"])
            k = item(s, "knowledge", p["originId"])
            ack = False
            readback = "unknown"
            message = ""
            if k["version"] != p["originRevision"] or k["status"] != "Approved":
                p["state"] = "Conflict"
                message = "Pinned origin revision or approval changed"
            elif t["revision"] != p["expectedRevision"]:
                p["state"] = "Conflict"
                message = "Native target changed since review"
            elif p["audience"] != t["audience"] or (
                k.get("restricted") and t["audience"] != "Finance stewards"
            ):
                p["state"] = "Failed"
                message = "Audience unsuitable"
            elif any(
                item(s, "proposals", dep)["state"] != "Verified"
                for dep in p["dependencies"]
            ):
                p["state"] = "Failed"
                message = "Dependency not verified"
            elif not simulation:
                checked = validate_proposal(native_proposal(s, p), native_adapter)
                p["state"] = (
                    "Conflict" if checked["status"] == "conflict" else "Unsupported"
                )
                message = (
                    "Read-only native preflight: "
                    + checked["status"]
                    + ". Export reviewed changes; no native write is enabled."
                )
            elif t["capability"] == "unsupported":
                p["state"] = "Unsupported"
                message = "Reviewed handoff required"
            elif t["permission"] != "permitted" or t["capability"] != "permitted":
                p["state"] = "Failed"
                message = "Permission or capability unavailable"
            elif t["failNext"]:
                t["failNext"] = False
                p["state"] = "Failed"
                message = "Simulated write failed; retry selected item only"
            else:
                t["content"][p["field"]] = deepcopy(p["after"])
                t["revision"] += 1
                t["origins"][p["field"]] = {
                    "originId": k["originId"],
                    "revision": k["version"],
                }
                ack = True
                if t["mismatchNext"]:
                    t["mismatchNext"] = False
                    t["content"][p["field"]] = "Divergent simulated read-back"
                readback = (
                    "matches" if t["content"][p["field"]] == p["after"] else "mismatch"
                )
                p["state"] = "Verified" if readback == "matches" else "Mismatch"
                message = "Simulated store read-back " + readback
            s["deliveries"].append(
                dict(
                    id=ident(s, "delivery"),
                    proposalId=id,
                    at=s["clock"],
                    state=p["state"],
                    acknowledged=ack,
                    readback=readback,
                    indexing="unknown",
                    answerUse="unknown",
                    message=message,
                )
            )
        return [p for p in s["proposals"] if p["id"] in payload["ids"]]
    raise WorkspaceError("Unsupported application command")
