# Cognee policy and encrypted persistence fit

2026-10-23. Third spike pass for #62; not a production adapter or final selection ADR.
Assesses the pinned Cognee 1.6.5 / Ladybug 0.19.0 configuration used in
[the lifecycle experiment](SECOND_PASS.md). Findings do not describe every Cognee
backend or future release.

## Decision supported by the evidence

Keep SQLCipher as the authoritative local store. Cognee remains a candidate for an
**optional, rebuildable retrieval projection**, subject to encryption and consistency
gates. Do not replace the policy layer with dataset permissions or treat source
ownership as complete claim provenance. No product dependency or behavior changes.

This is a narrower and more useful integration boundary than making a single
swappable backend responsible for storage, catalog authorization, modelling policy,
search, and graph semantics. Backend selection should change mechanics; it must not
change which evidence an agent is allowed to receive.

## Contract mapping

| Requirement | Evidence / fit | Responsibility retained in our core |
| --- | --- | --- |
| Claim identity and contradictory assertions | Previous probe preserves two explicit IDs and conflicting values. DataPoint fields carry our original observation timestamp. | Define canonical IDs and source/asset/field identity; keep assertions separate. Document ownership does not establish source authority or reconcile conflicts. |
| Source ownership and deletion | Real pipeline and public delete preserve shared graph nodes until their last source owner is removed. | Map catalog objects to ingestion documents and retain the original provider provenance; do not rewrite observation time as ingestion time. |
| Local dataset permission | New grant/revoke probe admits a shared reader and denies a fresh read context after revocation. | Require explicit read authorization at every tool boundary. Low-level graph handles are not authorization APIs. |
| Catalog authorization lifetime | Dataset permission is a separate local permission domain. No external catalog permission refresh was exercised. | Preserve independent permission TTL, credential/provider binding and fail-closed behavior. A valid Cognee user permission cannot revive a revoked UC/catalog fact. |
| Metadata TTL / no-TTL / capacity | No parity demonstrated by Cognee lifecycle tests. Current cache separates metadata lifetime from permission lifetime and bounds retained payloads. | Preserve expiry, restart validation, LRU budgets and review-only TTL suggestions. No-TTL never means no authorization expiry. |
| Project scope and quarantine | Project databases isolate the tested datasets. Our ProjectCatalog separately derives allowed assets and quarantines conflicting mappings. | Filter before ingestion and retrieval; invalidate removed assets and changed bindings. Dataset isolation alone is not project-manifest scope. |
| Atomic publication | Our ontology stages claims and publishes a source generation transactionally. Cognee storage supports provenance and rollback machinery, but those are not a demonstrated equivalent to our publication contract. | Stage a derived generation, validate it, then publish a pointer. Never combine partial new graph data with old authoritative claims. |
| Human decisions and exceptions | Current product keeps a separate local overlay and evidence-bound design memory. | Keep these human-owned records independent of catalog TTL, ingestion deletion and derived-index eviction. |
| At-rest protection | New probe finds synthetic plaintext in input documents, relational storage and graph storage for the tested configuration. | Require complete storage protection before projecting real project metadata. SQLCipher protection of one store cannot protect the others. |

The existing catalog cache and ontology are distinct components: the cache binds
facts to project/provider identities and permission freshness; the ontology stages
source generations. This table is a target integration contract, not a claim that
all existing components already share one universal transaction or snapshot API.

## New executable evidence

`cognee_pipeline_probe.py --cached-tokenizer --policy-fit` extends the existing
synthetic lifecycle fixture without patches to Cognee:

1. Owner grants an unrelated user read access using
   `authorized_give_permission_on_datasets`.
2. That user opens an explicit read context and reads the catalog claim.
3. Owner revokes read access using `authorized_revoke_permission_on_datasets`.
4. A new explicit read context raises `PermissionDeniedError`.
5. Before deletion, inspect files under the temporary application roots for two
   known synthetic byte strings and the ordinary SQLite file header.
6. Complete the earlier shared-owner deletion assertions.

The run completed with zero observed Python network attempts. It found:

| Artifact | Positive observation |
| --- | --- |
| Two input `.txt` files | Synthetic input text / claim value readable as bytes |
| Project `.lbug` file | Synthetic `customer-account` value readable as bytes |
| `system/databases/cognee_db` | SQLite header and both synthetic markers readable as bytes |

Raw results: [cognee-policy-fit.json](results/cognee-policy-fit.json). Paths contain
generated fixture IDs, not customer identities. Inspection is of live files,
bounded at 64 MiB per file. Absence of a marker would not prove encryption; positive
matches establish plaintext for these artifacts. This is not an audit of every
log, temp location, vector store, filesystem or native network path. No warehouse
rows or real project metadata were used.

```sh
SPIKE_HF_CACHE=/tmp/dbt-spike-hf-cache /tmp/dbt-cognee-spike/bin/python \
  experiments/offline_backends/cognee_pipeline_probe.py \
  /tmp/cognee-policy-fit.json --cached-tokenizer --policy-fit
```

See SECOND_PASS.md for tokenizer preparation and environment limitations. Revocation
was tested between contexts, not during an active query or against a previously
returned object. No remote catalog revocation, process restart or crash was simulated
in this pass. The initial environment connection was interrupted; a fresh rerun
completed with exit 0 before these findings were recorded.

## Inspected implementation anchors

These are paths in the pinned released wheel, not observations inferred from current
marketing documentation. The pinned environment is recorded in `cognee-freeze.txt`.

- `cognee/context_global_variables.py`, `DatabaseContextManager._bind_dataset_databases`:
  permission checking is conditional on an explicit `permission_type`; storage
  resolves against the dataset owner. This is an internal API boundary, not a claim
  of an authorization vulnerability in the public API.
- `cognee/modules/users/permissions/methods/authorized_give_permission_on_datasets.py`
  and `authorized_revoke_permission_on_datasets.py`: authorize sharing before changing
  the principal's dataset permissions.
- `cognee/infrastructure/databases/relational/create_relational_engine.py`: the tested
  SQLite provider builds a `sqlite+aiosqlite` URL.
- `cognee/tasks/storage/add_data_points.py`: graph-only mode avoids vector writes;
  provenance can use graph source references or a relational rollback ledger.
  Atomic source-reference writes do not by themselves establish whole-generation
  atomic publication across stores.
- Product anchors: `src/dbt_skills/catalog_cache.py`, `catalog_cache_store.py`,
  `project_catalog.py`, `ontology.py`, and `cache_security.py`. The protected store
  validates SQLCipher support, uses native key storage, and disables plaintext fallback.

## What reuse would actually remove

Cognee could supply graph adapters, dataset isolation, source-owner bookkeeping and
reference-aware derived-data deletion. Those are demonstrated benefits. However,
while SQLCipher remains authoritative, they would manage the **projection**, not
remove the existing canonical claim and policy code. Adding Cognee now would add
translation, generation coordination, packaging and a second permission domain.

No net maintenance reduction has yet been demonstrated. A future comparison must
count code actually removed, integration code added, dependencies shipped and
failure modes supported. Do not claim that adopting a framework automatically
reduces our maintenance burden. Conversely, do not reimplement its demonstrated
ownership machinery merely to avoid a dependency.

## Proposed seam and next acceptance gates

Keep catalog provider configuration separate from persistence/search configuration.
An ordered list of catalogs answers where evidence originates; a local projection
answers how already-authorized evidence is retrieved. They are different choices.

A minimal future retrieval adapter would accept a validated generation and return
bounded claim IDs/paths plus generation ID, completeness/truncation and diagnostics.
The core would resolve those IDs against the current authorized canonical snapshot
before exposing values. This is a proposal, not a new implemented interface.

Before any Cognee production adapter:

1. Demonstrate supported encryption for input documents, relational/graph/vector
   artifacts, journals, temporary files and logs. An encrypted volume may be an
   explicit deployment option, but is not equivalent to our current application-level
   protection against readable cache copies. Verify key lifecycle and failure behavior.
2. Prove publication/restart behavior with an interrupted generation and a stale
   projection: readers must get a complete authorized generation or an explicit
   unavailable result. Never silently omit stale graph hits and call the answer complete.
3. Test external permission expiry/revocation, removed project assets and quarantine
   against pinned retrieval; local dataset ACLs alone are insufficient.
4. Measure useful path/evidence retrieval and relevance, not only endpoint traversal.
   Require bounded work, cancellation and explicit truncation.
5. Compare keep-direct, optional projection and selective reuse in a selection ADR,
   including platform packaging and actual maintenance costs. Keep #62 open meanwhile.
