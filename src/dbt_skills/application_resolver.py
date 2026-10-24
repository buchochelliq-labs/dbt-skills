"""Policy-first resolver for canonical application state, with explicit simulation."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import time


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _scope(k, simulation):
    scope = k.get("scope", "")
    if scope in ("Enterprise", "Commercial"):
        return ""
    return "Billing" if simulation and scope == "Collections" else scope


def _ttl(state, knowledge, provider):
    if knowledge.get("ttl") is not None:
        return knowledge["ttl"]
    domains = {d["id"]: d for d in state.get("domains", [])}
    current, seen = knowledge.get("domain"), set()
    while current in domains and current not in seen:
        seen.add(current)
        domain = domains[current]
        if domain.get("ttl") is not None:
            return domain["ttl"]
        current = domain.get("parent")
    return provider.get("ttl", 24)


def _legacy_provider(k):
    if k.get("source") == "Unity Catalog":
        return "uc-finance" if k.get("domain") == "revenue" else "uc-customer"
    return "openmetadata" if k.get("source") == "OpenMetadata" else "authored"


def resolve_context(
    state, request, *, reader="steward", simulation=False, catalog_resolve=None
):
    """Resolve approved semantics; mutate only cache and observations.

    ``reader`` is trusted server identity, never the request's asserted reader.
    A mapped source is re-authorized by the core resolver even on a cache hit.
    """
    now = state.get("clock", 0) if simulation else int(time.time() * 1000)
    base = dict(
        schema_version=1,
        simulation=simulation,
        state="missing",
        message="No available meaning matches this request.",
        facts=[],
        trace=[],
    )

    def outcome(status, message, **extra):
        return {**base, "state": status, "message": message, **extra}

    term = re.sub(
        r"^(what is|define|explain|what does) (the |an? )?",
        "",
        _norm(request.get("question", "")),
    )
    term = re.sub(r" mean$", "", term)
    candidates = [
        k
        for k in state.get("knowledge", [])
        if not k.get("hidden")
        and (
            k["id"] == request["objectId"]
            if request.get("objectId")
            else any(_norm(n) == term for n in [k["name"], *k.get("synonyms", [])])
        )
    ]
    if not candidates:
        return base
    # Denial precedes scope hints; undiscoverable objects never enter candidates.
    inspectable = [
        k for k in candidates if not (reader == "restricted" and k.get("restricted"))
    ]
    if not inspectable:
        return outcome(
            "denied",
            "This reader cannot inspect the requested metadata. No replica or cache fallback.",
        )
    candidates = inspectable
    scope = request.get("scope", "")
    if len(candidates) > 1:
        scoped = [k for k in candidates if _scope(k, simulation) == scope]
        if len(scoped) != 1:
            return outcome(
                "ambiguous",
                "Choose a business scope to distinguish these meanings.",
                choices=[
                    dict(id=k["id"], name=k["name"], scope=k["scope"])
                    for k in candidates
                ],
            )
        candidates = scoped
    k = candidates[0]
    providers = state.get("providers", [])
    mappings = [m for m in state.get("mappings", []) if m["knowledgeId"] == k["id"]]
    assets = {a["id"]: a for a in state.get("assets", [])}
    bound = [assets[m["assetId"]] for m in mappings if m["assetId"] in assets]
    if any(a.get("hidden") for a in bound):
        return base
    if any(reader == "restricted" and a.get("restricted") for a in bound):
        return outcome("denied", "Source metadata access denied. No cache fallback.")
    origin_ids = {a["providerId"] for a in bound}
    if simulation:
        origin_ids.add(_legacy_provider(k))
    elif not mappings and k.get("source") not in ("Unity Catalog", "OpenMetadata"):
        origin_ids.update(p["id"] for p in providers if p.get("kind") == "authored")
    if any(p["id"] in origin_ids and p.get("health") == "denied" for p in providers):
        return outcome(
            "denied", "Origin policy denied access. No replica or cache fallback."
        )
    if k.get("status") != "Approved":
        return outcome(
            "withheld", "Unapproved definition values are withheld by UOL policy."
        )
    if _scope(k, simulation) and _scope(k, simulation) != scope:
        return outcome(
            "scopeMismatch", f"Choose the {_scope(k, simulation)} business scope."
        )
    day = datetime.fromtimestamp(now / 1000, timezone.utc).date().isoformat()

    def valid(item):
        return item.get("validFrom", "") <= day and (
            not item.get("validTo") or day <= item["validTo"]
        )

    if not valid(k):
        return outcome(
            "withheld",
            "The approved definition is outside its business-valid interval.",
        )

    source = None
    if not simulation and mappings:
        approved = [m for m in mappings if m.get("status") == "Approved" and valid(m)]
        if not approved:
            return outcome(
                "incomplete", "An approved, business-valid source mapping is required."
            )
        for mapping in approved:
            asset = assets.get(mapping["assetId"])
            provider = next(
                (p for p in providers if asset and p["id"] == asset["providerId"]), None
            )
            if (
                not asset
                or not provider
                or not provider.get("enabled")
                or catalog_resolve is None
            ):
                return outcome("incomplete", "Mapped source metadata is unavailable.")
            if (
                provider.get("scope")
                and "*" not in provider["scope"]
                and k.get("domain") not in provider["scope"]
            ):
                return outcome("incomplete", "Mapped source is outside provider scope.")
            if provider.get("health") == "malformed":
                return outcome("error", "Source metadata failed validation.")
            if provider.get("health") == "outage":
                return outcome("incomplete", "Mapped source metadata is unavailable.")
            fields = (
                ["relation", "columns"] if mapping.get("fieldPath") else ["relation"]
            )
            try:
                resolved = catalog_resolve(asset["id"], fields)
                if resolved.get("status") in ("denied", "error"):
                    return outcome(
                        resolved["status"],
                        "Resolution blocked; no context values exported.",
                    )
                if resolved.get("status") != "complete":
                    return outcome(
                        "incomplete", "Required mapped source evidence is unavailable."
                    )
                selected = resolved["selected"]
                field = mapping.get("fieldPath")
                if field and not any(
                    c.get("name") == field for c in selected["columns"]["value"]
                ):
                    return outcome(
                        "incomplete",
                        "Mapped field is absent from current source metadata.",
                    )
                provenance = selected["columns" if field else "relation"]["provenance"]
                provider = next((p for p in providers if p["id"] == provenance["provider"]), None)
                if not provider or not provider.get("enabled"):
                    return outcome("incomplete", "Selected source provider is unavailable.")
                if (provider.get("scope") and "*" not in provider["scope"]
                        and k.get("domain") not in provider["scope"]):
                    return outcome("incomplete", "Selected source is outside provider scope.")
                # Do not replace the selected provider/locator with frontend fixture metadata.
                source = (provider, asset, mapping, provenance)
            except Exception:
                return outcome("error", "Source metadata failed validation.")
    elif not simulation:
        # Unmapped curated knowledge is authored context, not external verification.
        if k.get("source") in ("Unity Catalog", "OpenMetadata"):
            return outcome("incomplete", "An approved source mapping is required.")
        provider = next(
            (p for p in providers if p.get("kind") == "authored" and p.get("enabled")),
            None,
        )
        if not provider or not k.get("sourcePath"):
            return outcome("incomplete", "Authored context is unavailable.")
        if provider.get("health") in ("denied", "malformed"):
            return outcome(
                "denied" if provider["health"] == "denied" else "error",
                "Authored context access blocked.",
            )
        if provider.get("health") == "outage":
            return outcome("incomplete", "Authored context is unavailable.")
        source = (provider, None, None, None)

    fingerprint = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in state.items()
                if key not in ("clock", "cache", "observations")
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    required = ["definition", "grain", "scope", "source"] + (
        ["formula", "unit", "aggregation"] if k.get("type") == "Metric" else []
    )
    keys = required + [
        key for key in ("dimensions", "logic", "exclusions") if k.get(key)
    ]
    missing = False
    state.setdefault("cache", [])
    state.setdefault("observations", [])
    for key in keys:
        value = (
            k.get("sourcePath")
            if key == "source"
            else (
                f'{k.get("scope", "")} · {k.get("grain", "")}'
                if key == "scope"
                else k.get(key)
            )
        )
        if isinstance(value, list):
            value = ", ".join(value)
        if not isinstance(value, str) or not value.strip():
            missing = missing or key in required
            continue
        choices = (
            [source]
            if source
            else [
                (p, None, None, None)
                for p in providers
                if p.get("enabled")
                and (
                    p["id"] == _legacy_provider(k)
                    or k["id"] == "active-customer"
                    and p["id"] == "authored"
                )
                and ("*" in p.get("scope", []) or k.get("domain") in p.get("scope", []))
            ]
        )
        fact = None
        for provider, asset, mapping, provenance in choices:
            if provider.get("health") in ("denied", "malformed"):
                return outcome(
                    "denied" if provider["health"] == "denied" else "error",
                    "Resolution blocked; no context values exported.",
                    facts=[],
                )
            if simulation:
                asset = next(
                    (
                        a
                        for a in state.get("assets", [])
                        if a.get("name") == k.get("sourcePath")
                        and a.get("providerId") == _legacy_provider(k)
                    ),
                    None,
                )
            replica = (
                simulation
                and k["id"] == "active-customer"
                and provider["id"] == "authored"
            )
            evidence = dict(
                originId=k["originId"],
                originRevision=k["version"],
                providerId=provider["id"],
                assetId=asset["id"] if asset else "",
                sourcePath="terms/active-customer.yaml" if replica else k["sourcePath"],
                observedAt=now,
                sourceRevision=f'{k["originId"]}@{k["version"]}',
                validFrom=k["validFrom"],
                approval=k["status"],
                origin=k["origin"],
                reader=reader,
                policyVersion=state.get("policyVersion", 1),
                replica=replica,
                confidence="declared",
                authority="not assessed",
            )
            if k.get("validTo"):
                evidence["validTo"] = k["validTo"]
            if provenance:
                try:
                    evidence.update(
                        providerId=provenance["provider"],
                        sourceRevision=provenance["revision"],
                        sourcePath=provenance["document"] + "#" + provenance["locator"],
                        observedAt=int(
                            datetime.fromisoformat(
                                provenance["retrieved_at"].replace("Z", "+00:00")
                            ).timestamp()
                            * 1000
                        ),
                    )
                except (KeyError, ValueError, TypeError):
                    return outcome(
                        "error", "Source provenance failed validation.", facts=[]
                    )
                if mapping.get("fieldPath"):
                    evidence["fieldPath"] = mapping["fieldPath"]
            cache_key = "|".join(
                map(
                    str,
                    [
                        k["id"],
                        k["version"],
                        key,
                        scope,
                        evidence["providerId"],
                        reader,
                        state.get("policyVersion", 1),
                        state.get("configVersion", 1),
                        simulation,
                        fingerprint,
                        # Identical bytes at a different source are not the same
                        # evidence. Reauthorization time alone may change on a hit.
                        hashlib.sha256(json.dumps(
                            {key: value for key, value in provenance.items() if key != "retrieved_at"},
                            sort_keys=True,
                        ).encode()).hexdigest() if provenance else "",
                    ],
                )
            )
            cached = next(
                (
                    e
                    for e in state["cache"]
                    if e["key"] == cache_key and e["expiresAt"] > now
                ),
                None,
            )
            if not cached and provider.get("health") == "outage":
                continue
            fact = (
                deepcopy(cached["fact"])
                if cached
                else dict(id=key, value=value, evidence=evidence)
            )
            state["observations"].append(
                dict(
                    knowledgeId=k["id"],
                    factId=key,
                    providerId=evidence["providerId"],
                    at=now,
                    hit=bool(cached),
                )
            )
            if not cached:
                state["cache"] = [
                    e
                    for e in state["cache"]
                    if e["key"] != cache_key and e["expiresAt"] > now
                ]
                state["cache"].append(
                    dict(
                        key=cache_key,
                        knowledgeId=k["id"],
                        fact=deepcopy(fact),
                        retrievedAt=now,
                        expiresAt=now + _ttl(state, k, provider) * 3600000,
                        configVersion=state.get("configVersion", 1),
                        reader=reader,
                        scope=scope,
                    )
                )
            base["trace"].append(
                f'{key}: {evidence["providerId"]} → {"cache" if cached else "sufficient"}'
            )
            break
        if fact:
            base["facts"].append(fact)
        elif key in required:
            missing = True
    return outcome(
        "incomplete" if missing else "sufficient",
        (
            "Required evidence is missing."
            if missing
            else "Required facts resolved with their original provenance. Declared semantics remain unverified."
        ),
    )
