# Offline backend spike — first measured pass (#62)

**Status: exploratory, not a production adapter or a completed selection.**
Measured 2026-10-23 on Linux x86-64 / Python 3.12.14 in a shared container.
No product source or dependency requirements changed. No real source data used.

**Update:** [Second-pass evidence](SECOND_PASS.md) now exercises the real Cognee
graph-only pipeline, permission checks, source deletion and branching graphs.
Further reports: [policy/encryption fit](POLICY_FIT.md) and
[generation recovery](RECOVERY.md), and [real index activation](PROJECTION.md).
The observations below describe the initial pass.

## Interim decision

Keep the current SQLCipher-based persistence default. These measurements do not
justify replacing it, nor building a universal database abstraction. SQLite with
FTS5 and indexed relational edges is a credible baseline for project-local context.
A graph-shaped domain does not by itself require a dedicated graph database.

Keep **Cognee as a genuine reuse candidate**. Its released adapter successfully
stores and retrieves structured conflicting claims without an LLM, retains explicit
observation fields, traverses a relationship, reopens the graph and deletes one
claim without deleting the other. It already has source-reference ownership support.
The next useful Cognee experiment is its supported graph-only pipeline with dataset
context, deletion and access rules, not another tiny raw graph benchmark.

Ladybug remains a candidate for richer traversals. The tested FTS binding has a
reproducible native crash, however, and its process ownership model needs integration
work. DuckDB has not demonstrated an advantage for this workload, and its observed
FTS update behavior requires an explicit rebuild in this experiment. Neither is
rejected for all workloads; neither earns a default switch on this evidence.

## Measured workload and results

Fixture: 500 or 5,000 relations, 20 columns each, one cyclic table-dependency chain,
column-to-table edges and one foreign-project search decoy. Respectively 10,501 /
105,001 nodes and 10,500 / 105,000 edges. Node properties include a synthetic original
provenance record. This is a **sparse graph**, not a realistic dense ontology.

Each row below is the median of three fresh-process runs. Each run samples 100
lookups and three-hop traversals, and 20 lexical searches. Values are the median of
run-level p95s, **not** a pooled p95. Complete observations are in `results/`.

| Relations | Engine | Lookup p95 ms | Three-hop p95 ms | Text top-20 p95 ms | Peak RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: |
| 500 | SQLCipher / SQLite | 0.008 | 0.023 | 0.540 | 29.1 |
| 500 | DuckDB | 0.588 | 3.292 | 19.342 | 123.7 |
| 500 | Ladybug | 0.138 | 11.088 | 3.631 | 122.2 |
| 5,000 | SQLCipher / SQLite | 0.011 | 0.031 | 7.784 | 90.7 |
| 5,000 | DuckDB | 2.877 | 13.720 | 31.133 | 200.0 |
| 5,000 | Ladybug | 0.183 | 62.776 | 19.779 | 186.4 |

Versions: SQLCipher Python package 0.6.4, reported SQLite 3.53.4; DuckDB 2.0.0;
Ladybug 0.21.2. Cognee 1.6.5 pins Ladybug 0.19.0 in the separate Linux environment.
The versions are deliberately not forced to match: overriding Cognee's dependency
would not test its supported installation. Direct engine dependencies and the full
Cognee environment are recorded in the two `*-freeze.txt` files.

**Interpretation limits:**

- One query formulation per operation, one sparse topology and two sizes. This is
  not evidence of general graph-engine superiority/inferiority, dense-path behavior
  or relationship-reasoning quality. Ladybug query-plan tuning remains untested.
- The SQLite query was corrected after EXPLAIN revealed a full node scan in the
  first formulation. Reported runs use indexed membership lookup; discarded runs
  are not mixed into the summary. We must scrutinize benchmark code too.
- All use one thread and a nominal 256 MiB cache/memory setting, whose meaning
  differs by engine. SQLCipher measurements are encrypted; DuckDB/Ladybug are not.
  Encryption overhead for those alternatives was not tested. No encryption parity
  claim is made.
- RSS includes Python, native modules, generated fixtures and indexes; it is not
  engine-only allocation. Open timings include imports on first open. Reopen is
  OS-cache-warm, not a cold-disk measurement, and some engines open lazily.
- Text query is `stg xyz`, returning scoped top 20 IDs. Tokenizers/ranking can differ;
  no search relevance/recall benchmark or synonym implementation is claimed.
- One-percent delta changes **relation labels**, not one percent of all nodes.
  Exact lookup and traversal results, search exclusion of the decoy, original
  provenance, deletion and restart have assertions. Permission/TTL/LRU policy
  integration is not implemented in these disposable adapters.
- FTS extensions were installed beforehand. Benchmarks make no explicit download
  calls, but native network isolation has not been proven. `unshare -n` is forbidden
  by this execution environment. Do not call these fully air-gapped acceptance tests.

## Reproduced issues and operational findings

### DuckDB FTS update

`repro_fts.py duckdb` creates one document and the FTS index with `incremental=1`,
changes its label and queries the new term. The base table changes; the search score
is NULL. Recreating the index with `overwrite=1, incremental=1` returns a score.
This also occurred in all six DuckDB benchmark runs. The harness records
`fts_update_visible=false`, then measures a rebuild before deletion checks.

This conflicts with the expectation from the current 2.0 documentation. It could
involve extension implementation/version semantics; we have not established an
upstream root cause. Do not turn this into the universal claim that DuckDB lacks
incremental FTS. Validate INSERT/UPDATE/DELETE separately before adoption.

### Ladybug parameterised FTS crash

`repro_fts.py ladybug` creates one node and repeats a parameterised FTS query.
On this Linux wheel/extension combination, call 0 succeeds and call 1 segfaults
(exit 139); the faulthandler stack points into `Connection._execute_with_pybind`.
The same query with a fixed literal completed 30 iterations. The full benchmark
initially failed in the repeated search phase too.

To continue measuring, `bench.py` permits **only two fixed synthetic literals**.
It does not offer a general string-interpolation workaround for user queries.
Results using literals do not demonstrate safe parameterised search. This issue
needs version/platform reproduction and an upstream-compatible fix before using
that search path in the product. Cognee uses a different Ladybug version; this
failure must not be attributed to Cognee without a separate reproduction.

### Process ownership

`lock_probe.py` keeps one database connection open while a second process opens
and writes. SQLite succeeded; DuckDB raised `IOException`; Ladybug raised
`RuntimeError`. This is a deliberately narrow file-ownership probe, not a stress
or simultaneous-transaction benchmark. It matches their documented embedded-mode
constraints. CLI + MCP would need coordinated access/one owner for those alternatives;
introducing an owner process has an operational cost for a lightweight local tool.

## Cognee proof of concept

`cognee_probe.py` uses the released Ladybug adapter and `DataPoint`, with two
separately identified, contradictory grain claims and an edge between them. It
calls no extraction or embedding operation, disables telemetry, configures local
model endpoints and blocks Python socket connect/DNS/sendto calls. There were no
attempts observed by that hook; native networking is not covered by the hook.

Verified:

- Both conflicting claims and their original `observed_at` values survive retrieval.
- One-hop neighborhood returns both claims and their relationship.
- Source ownership is stamped by `add_nodes` / `add_edges`; ordinary `get_nodes`
  does not expose those references, but `get_node_delete_data` does.
- Close/reopen retains values. Deleting one claim removes its incident edge and
  retains the other claim.
- A low-level getter can retrieve a node from another project. This is expected
  for this layer; our scope filter or Cognee's higher-level dataset/access machinery
  is still required. It is not a demonstrated high-level ACL defect.

Measured in the single tiny probe: import ~4.43 seconds, peak RSS ~348 MiB, graph
write ~87 ms. Installed Cognee environment: 176 distributions and ~1.43 GB of
site-packages (including pip/psutil and bytecode, no downloaded model weights).
The direct DuckDB+Ladybug+psutil environment totals ~111 MB. These are environment
footprints, not minimum package sizes or like-for-like throughput benchmarks.

Source inspection also found `add_data_points(..., graph_only=True)` in the pinned
Cognee wheel, explicitly skipping vector-engine initialization for deterministic
ingestion. That is a promising supported path. It has **not** been executed with
our project/dataset context in this pass. Do not conclude that full Cognee adoption
requires embeddings, or that low-level success proves full provenance/ACL parity.

Critical adoption questions:

1. Can the graph-only pipeline preserve original claim identity, observation times,
   contradictory evidence and human approval without awkward translations?
2. Can we retrieve evidence and enforce project/snapshot/permission constraints
   together, including deleting derived artifacts after revocation or quarantine?
3. Does the integration remove enough storage/retrieval/upgrade code to justify its
   footprint and dependency surface? Counting adapter lines alone is insufficient.
4. Can dependencies be optional for users who only need basic local context?
5. Does its supported API give bounded traversal/cancellation? The released adapter
   warns that edge-type-filtered neighborhoods enumerate paths and filter in Python;
   dense graphs require a separate experiment.

## Proposed interface experiment (not approved product configuration)

Start with independent capabilities, not a generic `execute(query)` interface:

- `ClaimStore`: atomic generation write/read, delete by scope/source, original
  provenance, lifecycle/capacity reporting; human decisions outside evictable cache.
- `TextIndex`: build/update generation, scoped search with result budget, report
  freshness/rebuild requirements. Return claim IDs, not new authoritative claims.
- `GraphIndex`: bounded neighbors/paths with edge types, generation, project scope
  and supporting claim IDs. Return explicit truncation/unsupported status.

A backend can implement several capabilities. Keep permission checks, retention,
quarantine and evidence authority above it. Switching backend should explicitly
rebuild/import, validate and activate a generation, with rollback. No live hot-swap
or arbitrary plugin module loading is needed to prove value.

Illustrative future selection, not currently accepted by the product:

```yaml
local_context:
  persistence: {backend: sqlcipher}
  text_index: {backend: sqlite_fts5}
  graph_index: {backend: sqlite_edges} # alternatives evaluated, not implemented
```

Cognee may own several of those responsibilities behind the context interface;
that remains a real alternative to maintaining direct engine adapters ourselves.

## Reproduce

These scripts currently require a Unix-like Python runtime (`resource` metrics).
Use disposable environments. Do not install spike dependencies into the product.

```sh
python -m venv /tmp/direct-spike
/tmp/direct-spike/bin/pip install -r experiments/offline_backends/direct-freeze.txt
python -m venv /tmp/cognee-spike
/tmp/cognee-spike/bin/pip install -r experiments/offline_backends/cognee-freeze.txt
```

Pre-stage DuckDB and Ladybug FTS extensions using the pinned engines' official
`INSTALL fts` commands before disconnecting. SQLCipher baseline uses the existing
product environment (`sqlcipher3==0.6.4`); FTS5 availability is a required build check.
Run each engine/size three times in separate processes, using distinct result paths:

```sh
python experiments/offline_backends/bench.py sqlcipher --relations 500 --output /tmp/sqlcipher.json
/tmp/direct-spike/bin/python experiments/offline_backends/bench.py duckdb --relations 500 --output /tmp/duckdb.json
/tmp/direct-spike/bin/python experiments/offline_backends/bench.py ladybug --relations 500 --output /tmp/ladybug.json
/tmp/cognee-spike/bin/python experiments/offline_backends/cognee_probe.py /tmp/cognee.json
/tmp/direct-spike/bin/python -X faulthandler experiments/offline_backends/repro_fts.py ladybug
/tmp/direct-spike/bin/python experiments/offline_backends/repro_fts.py duckdb
/tmp/direct-spike/bin/python experiments/offline_backends/lock_probe.py ladybug
```

Repeat at 5,000 relations. The Ladybug reproducer may crash its own process; it uses
only a temporary synthetic database. No benchmark asserts a universal performance
threshold. Frozen dependencies describe this Linux/Python installation, not a
validated cross-platform lock file.

## Remaining before a selection ADR

Keep #62 open. Required follow-ups include dense/skewed/cyclic domain graphs,
relevance evaluation, high-level Cognee graph-only pipeline/dataset integration,
permission/TTL/LRU/quarantine integration, snapshot consistency, interruption/recovery,
migration/rollback, encryption of all derived/temp data, Windows/macOS packaging,
true network-denied runtime tests, and cost/benefit of a local owner process.
Oxigraph, DuckPGQ and optional vector search remain desk-screen candidates with no
measurements here. A one-million-node stress run is not needed to justify this
interim decision and has not been performed.

## Evidence sources

Package wheel/source inspected: `cognee==1.6.5` —
`infrastructure/databases/graph/ladybug/adapter.py`,
`infrastructure/engine/models/DataPoint.py`, `tasks/storage/add_data_points.py`.
Released wheel metadata is the dependency evidence, rather than repository main.

- https://sqlite.org/fts5.html
- https://sqlite.org/lang_with.html
- https://duckdb.org/docs/2.0/core_extensions/full_text_search
- https://duckdb.org/docs/2.0/connect/concurrency
- https://docs.ladybugdb.com/concurrency/
- https://docs.ladybugdb.com/extensions/full-text-search/
- https://docs.cognee.ai/guides/graph-engine-adapters
- https://docs.cognee.ai/guides/local-setup
- https://docs.cognee.ai/setup-configuration/graph-stores
- Original research matrix and wider source list: issue #62.
