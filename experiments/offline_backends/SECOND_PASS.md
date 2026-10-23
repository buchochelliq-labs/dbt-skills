# Second pass: Cognee pipeline lifecycle and branching graphs

**2026-10-23. Exploratory evidence, not a production integration or final ADR.**
Continues [the initial report](README.md) and issue #62. Uses the same pinned Linux
Python environments. No product dependencies or persistence behavior changed.

## What changed in the assessment

Cognee is now demonstrated beyond direct adapter CRUD. Its real graph-only storage
task, local datasets and public dataset-delete API preserve conflicting claims,
source ownership and project separation in this fixture. Explicit dataset permission
checks reject an unrelated user. These capabilities could save meaningful integration
code; dismissing it as merely a heavyweight graph wrapper would be wrong.

There is also a concrete lifecycle dependency: deletion of graph-only relationships
initializes vector/embedding infrastructure and loads a tokenizer. A fresh isolated
cache fails under the Python network guard. Pre-staging two tokenizer files and using
the supported override allows the entire tested flow to finish with no observed
Python network attempts. No vendor code patch, mocked engine or model call was used.

SQLite still earns its place as the simplest baseline. The richer query experiment
also shows why an engine choice based on one SQL formulation would be misleading.

## Cognee pipeline experiment

Run `cognee_pipeline_probe.py` with Cognee 1.6.5 / Ladybug 0.19.0. It:

1. Sets temporary local roots, disables telemetry, configures local model endpoints,
   enables backend access control and disables graph/vector subprocess mode.
2. Creates real local users and two datasets through Cognee's existing setup/add
   paths. Inputs are three synthetic metadata declarations, not warehouse rows.
3. Calls `add_data_points(..., graph_only=True)` with actual `PipelineContext`
   user/dataset/data-item objects inside the dataset database context. No patched
   factories or fake stores are involved.
4. Writes two separately identified contradictory grain claims and a shared concept,
   attributed to two documents. Original `observed_at` values remain explicit fields.
5. Verifies each project database cannot retrieve the other project's claim.
6. Verifies an unrelated user receives the expected `PermissionDeniedError` for
   listing/context entry and `UnauthorizedDataAccessError` for deletion. The probe
   explicitly requests `permission_type` on context entry; a bare internal context
   is not itself an authorization boundary.
7. Calls the public `datasets.delete_data` operation. Deleting the first document
   removes its claim/edge while retaining the shared concept, second source ref,
   other claim and edge. Removing the last owner removes those remaining graph
   artifacts; the other project's claim remains intact.

The successful pre-staged run passed every assertion. Raw evidence:
[`cognee-pipeline-cached.json`](results/cognee-pipeline-cached.json).
This proves the listed scenarios, not exhaustive ACL or provenance parity with our
product. Shared ownership was tested within one dataset; cross-user sharing,
permission revocation after a pinned snapshot, quarantine and TTL were not tested.
No high-level semantic search or automatic fact extraction was exercised.

### Fresh-cache deletion failure

The cold run reaches deletion after ingestion, isolation and access-denial checks
have passed. Its call path is:

`datasets.delete_data` → graph provenance removal → unified delete planner →
legacy triplet-vector collection check → lazy vector engine → embedding gateway →
Ollama tokenizer resolution → HuggingFace tokenizer fetch, then TikToken fallback.

Both DNS attempts were blocked by the Python audit hook. This is a missing offline
artifact/lifecycle dependency, not evidence that an embedding request sent our
metadata to a service. Graph-only ingestion itself did not trigger those attempts.

After the exception, assertions confirmed both claims, both source references and
both source documents remained available. This particular failure did not silently
half-delete the fixture. A product wrapper would still need an explicit failed-sync
state and retry policy rather than claiming deletion succeeded.

Raw evidence: [`cognee-pipeline-cold.json`](results/cognee-pipeline-cold.json).
The cold probe deliberately exits 1 when it reproduces this failure.

### Supported configuration mitigation

The successful run sets:

```text
HUGGINGFACE_TOKENIZER=nomic-ai/nomic-embed-text-v1.5
HF_HUB_OFFLINE=1
HF_HOME=<pre-staged cache>
```

Only `tokenizer.json` (711,396 bytes) and `tokenizer_config.json` (1,191 bytes)
were pre-staged: 712,587 bytes total, no model weights. The exact repository
revision and SHA-256 hashes are recorded in `results/tokenizer-artifacts.json`.
The environment already had Cognee/Ladybug and the required JSON extension from
the earlier experiment; this is not a fresh-machine offline installation proof.

This avoids the download failure without removing the vector/embedding lifecycle
coupling. A supported graph-only deletion path that avoids that initialization
would be a cleaner fit. We should evaluate an upstream fix or packaging the small
required artifacts before rejecting Cognee. Do not change to a no-op vector backend
just to make the test pass: that could hide real derived-data deletion obligations.

Reproduce after creating the pinned Cognee environment from the first report:

```sh
# Explicit online preparation; rejects drift from the recorded artifacts.
/tmp/cognee-spike/bin/python experiments/offline_backends/prestage_tokenizer.py /tmp/dbt-spike-hf-cache
# Expected cold failure, using fresh isolated tokenizer caches.
/tmp/cognee-spike/bin/python experiments/offline_backends/cognee_pipeline_probe.py /tmp/cold.json
# Configuration-only mitigation, using the staged cache.
SPIKE_HF_CACHE=/tmp/dbt-spike-hf-cache /tmp/cognee-spike/bin/python experiments/offline_backends/cognee_pipeline_probe.py /tmp/cached.json --cached-tokenizer
```

The Python audit hook blocks socket connect/DNS/sendto events before imports.
Native library networking is not OS-isolated. Subprocess mode is disabled so
Python instrumentation covers the tested application process. Native egress,
subprocess deployment and crash recovery remain separate acceptance work.

## Branching/convergent graph experiment

`branching_probe.py` adds two deterministic fixtures and an independent Python BFS
oracle. Each engine runs in a fresh child process with a 30-second whole-process
limit, three repetitions, 30 warm traversal measurements per repetition.

- **Cyclic branching:** 500 nodes / 3,000 edges, six outgoing offsets per node,
  65 distinct nodes reachable within three hops from the selected start.
- **Converging paths:** 130 nodes / 4,225 edges: root → 64 branches → 64 shared
  nodes → sink, plus sink → root. There are 129 reachable nodes; queries return
  the first 100 IDs in deterministic lexical order.

All 18 runs completed within the process limit. Every result matched the independent
oracle, including the truncated 100-node result. These are small, intentionally
adversarial topologies, not a large enterprise ontology benchmark.

Median of the three run-level p95 query times, milliseconds:

| Topology | SQLite original | SQLite deduplicated | DuckDB original | DuckDB deduplicated | Ladybug |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cyclic branching | 0.298 | 0.214 | 2.609 | 2.638 | 1.712 |
| Converging paths | 8.328 | 1.252 | 3.108 | 2.879 | 5.082 |

The original recursive SQL uses `UNION ALL`; the second variant uses `UNION` to
collapse equal `(node, depth)` states before the next expansion. Both are verified
against the same oracle. This optimization is valid for **endpoint reachability**;
it is not interchangeable with returning every distinct path and its evidence.
Ladybug uses the original Cypher endpoint query; alternative Cypher formulations,
query-plan tuning and graph algorithms remain untested.

Without the second SQL variant, this fixture would suggest switching to DuckDB.
With it, SQLite is faster here. The useful lesson is to specify the retrieval
semantics and inspect duplicate work before adding another storage engine.

These branching runs use plaintext SQLite, DuckDB and Ladybug. They are separate
from the first report's encrypted SQLCipher baseline. FTS is loaded during fixture
setup but is not queried/timed here. Peak RSS includes setup and fixtures. Raw
results: [`branching.json`](results/branching.json).

`LIMIT 100` does not bound internal traversal work. The process-level timeout is a
spike safeguard, not implemented product cancellation. Also, the oracle tells us
there are 129 reachable nodes; the prototype query itself does not report a
truncation flag. A production graph contract must do so and distinguish incomplete
context from a complete answer.

```sh
/tmp/direct-spike/bin/python experiments/offline_backends/branching_probe.py --output /tmp/branching.json
```

## Updated direction and remaining decision gates

**Keep the current default. Continue the Cognee reuse evaluation.** There is now
positive pipeline evidence to weigh against its footprint, lifecycle dependencies
and adapter work. No evidence yet justifies building several production backends.

Next gates, in order:

1. Map our canonical claim IDs, source permissions, pinned snapshots, quarantine,
   TTL/no-TTL retention and human decision ownership onto Cognee's dataset/source
   ownership model. Identify code genuinely removed versus translation code added.
2. Verify local encryption of relational, graph, vector, log/temp and derived files.
   Current product SQLCipher protection must not silently become partial protection.
3. Prove denial/revocation and interrupted sync cannot expose stale facts; test restart
   and migration/rebuild with real generation boundaries, not isolated CRUD calls.
4. Measure bounded path/evidence retrieval and search relevance on representative
   projects; test native cancellation, subprocess mode and cross-platform packaging.
5. Produce a selection ADR choosing keep-direct / optional Cognee integration /
   selective component reuse, with an explicit maintenance and packaging cost.

No native graph/embedding framework is made mandatory by these experiments. Issue
#62 remains open; source code under this directory is disposable evidence, not a
new supported persistence API.
