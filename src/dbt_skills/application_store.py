"""Encrypted, revisioned persistence for the complete UOL frontend State contract."""

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import secrets
from threading import RLock
from jsonschema import Draft202012Validator
from .cache_security import OSKeyringKeyStore, open_encrypted_database, secure_path
from .context_limits import check_bounds
from .workspace_store import WorkspaceError, WorkspaceConflict
from .catalog import _PROVENANCE

ApplicationError = WorkspaceError
ApplicationConflict = WorkspaceConflict
S = {"type": "string", "maxLength": 32000}
N = {"type": "number", "minimum": 0}
I = {"type": "integer", "minimum": 0}
B = {"type": "boolean"}
ID = {"type": "string", "minLength": 1, "maxLength": 256}
NULLSTR = {"type": ["string", "null"], "maxLength": 32000}
APPROVAL = {"enum": ["Approved", "Draft", "Needs review"]}
OUTCOME = {"enum": ["permitted", "denied", "unsupported", "unknown"]}
PUBLICATION = {
    "enum": [
        "Draft",
        "Reviewed",
        "Conflict",
        "Unsupported",
        "Failed",
        "Saved",
        "Verified",
        "Mismatch",
        "Exported",
    ]
}
READER = {"enum": ["steward", "restricted"]}


def arr(item=S):
    return {"type": "array", "maxItems": 5000, "items": item}


def obj(properties, optional=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [k for k in properties if k not in optional],
    }


def fields(names, **extra):
    return {**{name: S for name in names.split()}, **extra}


def dictionary(value):
    return {"type": "object", "maxProperties": 1000, "additionalProperties": value}


REVISION = obj(fields("definition origin", revision=I, status=APPROVAL, changedAt=N))
DOMAIN = obj(
    fields(
        "name description icon",
        id=ID,
        parent=NULLSTR,
        owner=NULLSTR,
        technicalOwner=NULLSTR,
        steward=NULLSTR,
        providerPolicy=NULLSTR,
        ttl={"type": ["number", "null"], "minimum": 0},
    ),
    ("icon", "steward", "providerPolicy"),
)
KNOWLEDGE = obj(
    fields(
        "name type domain summary definition scope grain origin owner source sourcePath effective validFrom validTo originId formula unit aggregation logic exclusions freshness",
        id=ID,
        memberships=arr(),
        status=APPROVAL,
        version=I,
        synonyms=arr(),
        related=arr(),
        dimensions=arr(),
        ttl=N,
        hidden=B,
        restricted=B,
        history=arr(REVISION),
    ),
    (
        "freshness",
        "validTo",
        "formula",
        "unit",
        "aggregation",
        "dimensions",
        "logic",
        "exclusions",
        "ttl",
        "hidden",
        "restricted",
    ),
)
PROVIDER = obj(
    fields(
        "name workspace metastore",
        id=ID,
        kind={"enum": ["uc", "openmetadata", "authored"]},
        enabled=B,
        ttl=N,
        health={"enum": ["healthy", "outage", "denied", "malformed"]},
        scope=arr(),
        capabilities=dictionary(OUTCOME),
    )
)
FIELD = obj(fields("path type comment classification key", nullable=B))
ASSET = obj(
    fields(
        "nativeId providerId name owner description sourceRevision",
        id=ID,
        type={"enum": ["catalog", "schema", "table", "view", "metric_view"]},
        parent=NULLSTR,
        tags=dictionary(S),
        fields=arr(FIELD),
        domainIds=arr(),
        knowledgeIds=arr(),
        observedAt=N,
        sourceEvidence=obj({"relation": _PROVENANCE.schema, "columns": _PROVENANCE.schema}, ("columns",)),
        hidden=B,
        restricted=B,
        discloseExistence=B,
    ),
    ("hidden", "restricted", "discloseExistence", "sourceEvidence"),
)
RELATIONSHIP = obj(
    fields(
        "source target label scope cardinality provenance sourceField targetField",
        id=ID,
        type={
            "enum": [
                "membership",
                "is_a",
                "part_of",
                "business",
                "mapping",
                "join",
                "lineage",
                "dependency",
            ]
        },
        approval=APPROVAL,
    ),
    ("sourceField", "targetField"),
)
MAPPING = obj(
    fields(
        "knowledgeId attribute assetId fieldPath type scope validFrom validTo evidence",
        id=ID,
        status=APPROVAL,
    ),
    ("validTo",),
)
EVIDENCE = obj(
    fields(
        "originId providerId assetId fieldPath sourcePath sourceRevision validFrom validTo origin",
        originRevision=I,
        observedAt=N,
        approval=APPROVAL,
        reader=READER,
        policyVersion=I,
        replica=B,
        confidence={"const": "declared"},
        authority={"const": "not assessed"},
    ),
    ("fieldPath", "validTo"),
)
FACT = obj({"id": ID, "value": S, "evidence": EVIDENCE})
CACHE = obj(
    fields(
        "key knowledgeId scope",
        fact=FACT,
        retrievedAt=N,
        expiresAt=N,
        configVersion=I,
        reader=READER,
    )
)
OBSERVATION = obj(fields("knowledgeId factId providerId", at=N, hit=B))
PROPOSAL = obj(
    fields(
        "originId targetId field reason audience evidence reviewDecision",
        id=ID,
        originRevision=I,
        before={},
        after={},
        expectedRevision=I,
        state=PUBLICATION,
        dependencies=arr(),
        reviewedAt=N,
        nativeBaseFingerprint=S,
        nativeResult={"type": "object"},
    ),
    ("reviewedAt", "reviewDecision", "nativeBaseFingerprint", "nativeResult"),
)
TARGET = obj(
    fields(
        "name kind providerId audience",
        id=ID,
        revision=I,
        content=dictionary({}),
        capability=OUTCOME,
        permission=OUTCOME,
        atomic=B,
        failNext=B,
        mismatchNext=B,
        origins=dictionary(obj({"originId": S, "revision": I})),
        nativeObservation={"type": "object"},
    ),
    ("nativeObservation",),
)
DELIVERY = obj(
    fields(
        "proposalId message",
        id=ID,
        at=N,
        state=PUBLICATION,
        acknowledged=B,
        readback={"enum": ["matches", "mismatch", "unknown"]},
        indexing={"const": "unknown"},
        answerUse={"const": "unknown"},
    )
)
PAGE = obj(
    fields(
        "name domain owner summary body",
        id=ID,
        synonyms=arr(),
        relatedAssets=arr(),
        sources=arr(),
        state={"enum": ["Draft", "Published", "Archived"]},
    )
)
COLLECTIONS = dict(
    domains=DOMAIN,
    knowledge=KNOWLEDGE,
    providers=PROVIDER,
    assets=ASSET,
    relationships=RELATIONSHIP,
    mappings=MAPPING,
    cache=CACHE,
    observations=OBSERVATION,
    proposals=PROPOSAL,
    targets=TARGET,
    deliveries=DELIVERY,
    pages=PAGE,
)
STATE_SCHEMA = obj(
    {
        **{k: arr(v) for k, v in COLLECTIONS.items()},
        "clock": N,
        "policyVersion": I,
        "configVersion": I,
        "sequence": I,
        "ttlDismissed": B,
    }
)


def empty_state():
    return {
        **{k: [] for k in COLLECTIONS},
        "clock": 0,
        "policyVersion": 1,
        "configVersion": 1,
        "sequence": 1,
        "ttlDismissed": False,
    }


def _acyclic(edges):
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
    visiting, done = set(), set()

    def visit(node):
        if node in visiting:
            raise ValueError("cycle")
        if node in done:
            return
        visiting.add(node)
        for child in adjacency.get(node, []):
            visit(child)
        visiting.remove(node)
        done.add(node)

    for node in adjacency:
        visit(node)


def validate_state(value):
    try:
        check_bounds(value)
        Draft202012Validator(STATE_SCHEMA).validate(value)
        ids = {}
        for collection, records in value.items():
            if collection not in COLLECTIONS or collection in ("cache", "observations"):
                continue
            keys = [r["id"] for r in records]
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate ID")
            ids[collection] = set(keys)
        # Targets intentionally share their corresponding source-asset IDs.
        entity_ids = set().union(
            *(ids[k] for k in ("domains", "knowledge", "assets", "pages"))
        )

        def ref(key, group, nullable=False):
            if nullable and key is None:
                return
            if key not in ids[group]:
                raise ValueError("dangling reference")

        for d in value["domains"]:
            ref(d["parent"], "domains", True)
        for k in value["knowledge"]:
            ref(k["domain"], "domains")
            if len(set(k["memberships"])) != len(k["memberships"]) or k["domain"] in k["memberships"]:
                raise ValueError("invalid additional memberships")
            for m in k["memberships"]:
                ref(m, "domains")
            for related in k["related"]:
                if related not in entity_ids:
                    raise ValueError("dangling related reference")
        for a in value["assets"]:
            ref(a["providerId"], "providers")
            ref(a["parent"], "assets", True)
            for d in a["domainIds"]:
                ref(d, "domains")
            for k in a["knowledgeIds"]:
                ref(k, "knowledge")
            paths = [f["path"] for f in a["fields"]]
            if len(paths) != len(set(paths)):
                raise ValueError("duplicate field")
        for r in value["relationships"]:
            if r["source"] not in entity_ids or r["target"] not in entity_ids:
                raise ValueError("dangling relationship")
        for m in value["mappings"]:
            ref(m["knowledgeId"], "knowledge")
            ref(m["assetId"], "assets")
        for p in value["pages"]:
            ref(p["domain"], "domains")
            for a in p["relatedAssets"]:
                ref(a, "assets")
        origins = (
            {k["originId"] for k in value["knowledge"]}
            | ids["knowledge"]
            | ids["pages"]
        )
        for p in value["proposals"]:
            ref(p["targetId"], "targets")
            if p["originId"] not in origins:
                raise ValueError("dangling origin")
            for d in p["dependencies"]:
                if (
                    d not in origins
                    and d not in ids["proposals"]
                    and d not in entity_ids
                ):
                    raise ValueError("dangling dependency")
        for t in value["targets"]:
            ref(t["providerId"], "providers")
        for d in value["deliveries"]:
            ref(d["proposalId"], "proposals")
        for c in value["cache"]:
            ref(c["knowledgeId"], "knowledge")
            e = c["fact"]["evidence"]
            ref(e["providerId"], "providers")
            if e["assetId"]:
                ref(e["assetId"], "assets")
        for o in value["observations"]:
            ref(o["knowledgeId"], "knowledge")
            ref(o["providerId"], "providers")
        _acyclic(
            (d["id"], d["parent"]) for d in value["domains"] if d["parent"] is not None
        )
        _acyclic(
            (a["id"], a["parent"]) for a in value["assets"] if a["parent"] is not None
        )
        for kind in ("is_a", "part_of", "dependency", "lineage"):
            _acyclic(
                (r["source"], r["target"])
                for r in value["relationships"]
                if r["type"] == kind
            )
    except Exception:
        raise ApplicationError(
            "Invalid application state: bounded contract records, unique IDs, valid references and acyclic hierarchies required"
        ) from None
    return deepcopy(value)


class ApplicationStore:
    def __init__(self, path, *, key_store=None, initial_state=None, simulation=False):
        if type(simulation) is not bool:
            raise ApplicationError("Simulation must be boolean")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        secure_path(self.path.parent, directory=True)
        self.key = (key_store or OSKeyringKeyStore()).get_or_create_key(
            self.path, create=not self.path.exists()
        )
        if not self.key:
            raise ApplicationError("Application encryption key unavailable")
        self.lock, self.previews = RLock(), {}
        with self.connection() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS application_revisions (revision INTEGER PRIMARY KEY, state TEXT NOT NULL, reason TEXT NOT NULL)"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS application_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            if (
                c.execute("SELECT COUNT(*) FROM application_revisions").fetchone()[0]
                == 0
            ):
                state = validate_state(
                    initial_state if initial_state is not None else empty_state()
                )
                c.execute(
                    "INSERT INTO application_revisions VALUES (0,?,?)",
                    (json.dumps(state), "initial"),
                )
                c.execute(
                    "INSERT INTO application_metadata VALUES ('simulation',?)",
                    (json.dumps(simulation),),
                )
            self.simulation = json.loads(
                c.execute(
                    "SELECT value FROM application_metadata WHERE key='simulation'"
                ).fetchone()[0]
            )
        secure_path(self.path)

    @contextmanager
    def connection(self):
        c = open_encrypted_database(self.path, self.key)
        try:
            with c:
                yield c
        finally:
            c.close()

    def read(self):
        with self.lock, self.connection() as c:
            revision, state = c.execute(
                "SELECT revision,state FROM application_revisions ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            return {"revision": revision, "state": json.loads(state)}

    def transact(self, expected_revision, mutate, reason="application edit"):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ApplicationError("Expected revision required")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 256:
            raise ApplicationError("Bounded reason required")
        with self.lock, self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            revision, encoded = c.execute(
                "SELECT revision,state FROM application_revisions ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            if revision != expected_revision:
                raise ApplicationConflict(
                    "Application changed; reload and review before saving"
                )
            state = json.loads(encoded)
            result = mutate(state)
            state = validate_state(state)
            check_bounds(result)
            c.execute(
                "INSERT INTO application_revisions VALUES (?,?,?)",
                (revision + 1, json.dumps(state, allow_nan=False), reason),
            )
            return {
                "revision": revision + 1,
                "state": state,
                "result": deepcopy(result),
            }

    def history(self):
        with self.lock, self.connection() as c:
            return [
                {"revision": r, "reason": reason}
                for r, reason in c.execute(
                    "SELECT revision,reason FROM application_revisions ORDER BY revision DESC"
                )
            ]

    def export(self):
        return {
            "schema_version": 1,
            "kind": "uol-application",
            "simulation": self.simulation,
            **self.read(),
        }

    def preview_import(self, envelope):
        if (
            not isinstance(envelope, dict)
            or set(envelope)
            != {"schema_version", "kind", "simulation", "revision", "state"}
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != 1
            or envelope["kind"] != "uol-application"
            or type(envelope["simulation"]) is not bool
            or type(envelope["revision"]) is not int
            or envelope["revision"] < 0
        ):
            raise ApplicationError("Invalid application export envelope")
        if envelope["simulation"] != self.simulation:
            raise ApplicationError(
                "Simulation and live application imports cannot be mixed"
            )
        state = validate_state(envelope["state"])
        # Validate contradictory approved mappings before imported source fields
        # are redacted. Empty inventories are unknown; mappings awaiting review
        # may intentionally retain a field removed from a later source schema.
        assets = {a["id"]: a for a in state["assets"]}
        for mapping in state["mappings"]:
            fields = assets[mapping["assetId"]]["fields"]
            if (
                mapping["status"] == "Approved"
                and mapping["fieldPath"]
                and fields
                and mapping["fieldPath"] not in {f["path"] for f in fields}
            ):
                raise ApplicationError(
                    "Invalid application import: approved mapping field is not declared by its source asset"
                )
        changes = []

        def reset(collection, record, updates):
            changed = [k for k, v in updates.items() if record.get(k) != v]
            if changed:
                changes.append(
                    {
                        "collection": collection,
                        "id": record.get("id"),
                        "fields": changed,
                    }
                )
            record.update(updates)

        for collection in ("cache", "observations"):
            changes.append(
                {"collection": collection, "cleared": len(state[collection])}
            )
            state[collection] = []
        for p in state["providers"]:
            reset(
                "providers",
                p,
                {
                    "enabled": False,
                    "health": "denied",
                    "capabilities": {k: "unknown" for k in p["capabilities"]},
                },
            )
        for a in state["assets"]:
            reset(
                "assets",
                a,
                dict(
                    owner="",
                    description="",
                    tags={},
                    fields=[],
                    observedAt=0,
                    sourceRevision="",
                    hidden=True,
                    restricted=True,
                    discloseExistence=False,
                ),
            )
            if "sourceEvidence" in a:
                changes.append({"collection": "assets", "id": a["id"], "removed": "sourceEvidence"})
                del a["sourceEvidence"]
        for t in state["targets"]:
            reset(
                "targets",
                t,
                dict(
                    revision=0,
                    content={},
                    capability="unknown",
                    permission="unknown",
                    origins={},
                    atomic=False,
                    failNext=False,
                    mismatchNext=False,
                ),
            )
            if "nativeObservation" in t:
                changes.append(
                    {
                        "collection": "targets",
                        "id": t["id"],
                        "removed": "nativeObservation",
                    }
                )
                del t["nativeObservation"]
        for p in state["proposals"]:
            reset("proposals", p, {"state": "Draft", "expectedRevision": 0})
            for key in (
                "reviewedAt",
                "reviewDecision",
                "nativeBaseFingerprint",
                "nativeResult",
            ):
                if key in p:
                    changes.append(
                        {"collection": "proposals", "id": p["id"], "removed": key}
                    )
                    del p[key]
        for d in state["deliveries"]:
            reset(
                "deliveries",
                d,
                {"acknowledged": False, "readback": "unknown", "state": "Draft"},
            )
        state = validate_state(state)
        current = self.read()
        diff = {
            "collections": {},
            "security_resets": changes,
            "preferences_changed": [],
        }
        for collection in COLLECTIONS:
            old, new = current["state"][collection], state[collection]
            diff["collections"][collection] = {
                "before": len(old),
                "after": len(new),
                "changed": old != new,
            }
        for key in (
            "clock",
            "policyVersion",
            "configVersion",
            "sequence",
            "ttlDismissed",
        ):
            if current["state"][key] != state[key]:
                diff["preferences_changed"].append(key)
        token = secrets.token_urlsafe(24)
        with self.lock:
            if len(self.previews) >= 16:
                self.previews.clear()
            self.previews[token] = (current["revision"], deepcopy(state))
        return {
            "preview_id": token,
            "expected_revision": current["revision"],
            "diff": diff,
            "state": state,
        }

    def apply_import(self, preview_id):
        with self.lock:
            if preview_id not in self.previews:
                raise ApplicationError("Import preview unavailable; preview again")
            revision, state = self.previews.pop(preview_id)

            def replace(destination):
                destination.clear()
                destination.update(state)

            result = self.transact(
                revision,
                replace,
                "Reviewed application import; external observations and permission receipts reset",
            )
            return {"revision": result["revision"], "state": result["state"]}
