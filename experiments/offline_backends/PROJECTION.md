# Interrupted derived-index build and activation

2026-10-23. Fifth #62 spike slice; a disposable adapter, not a supported product
feature or a Cognee acceptance result. Follows [canonical recovery](RECOVERY.md).

## Real storage exercised

`projection_probe.py` creates two source generations using the real encrypted
ontology store. Both sources deliberately use the same local claim ID; the index
stores source-qualified identities. Only source A is changed in the next snapshot,
so the projection must bind the generation vector for both A and B.

The projection is a separate SQLCipher database containing a real FTS5 virtual
table. A second encrypted database holds the desired generation vector, active
filename and revision. The prototype builds a new immutable file, validates its
exact contents and FTS query against canonical values, marks it complete, then
updates the active pointer in a transaction. Index rows commit incrementally to
make partial builds observable. All database connections use the existing protected
SQLCipher primitive; synthetic keys use the test-only FileKeyStore.

After canonical publication, the old index is withheld until a matching validated
index becomes active. The reader obtains claim IDs from FTS and returns values from
canonical storage. This avoids promoting indexed text to authoritative evidence.

## Results

Each scenario runs in a fresh temporary directory. A child process calls
`os._exit(74)` at the selected boundary, bypassing Python cleanup. The parent opens
new database connections and queries the real FTS index.

| Child exit boundary | Result after restart | Recovery |
| --- | --- | --- |
| After first committed index row | Unavailable, no claims | Rebuild and activate |
| After complete index validation, before activation | Unavailable, no claims | Rebuild and activate |
| After pointer update, before its commit | Unavailable, no claims | Rebuild and activate |
| After activation commit, before success response | Complete new result | Already active |

All four cases passed. Each verifies both source-qualified IDs and exact canonical
values. Every scenario also checks that a revision change injected after the FTS
query causes the whole result to be withheld. Serial cleanup removes abandoned
files and their WAL/SHM companions; a subsequent read still returns the exact active
generation. Raw results: [projection.json](results/projection.json).

```sh
python experiments/offline_backends/projection_probe.py /tmp/projection.json
```

The script imports the previous spike's helpers and existing test fixtures. Product
dependencies are sufficient; it needs neither Cognee nor a new dependency. Children
have a 30-second timeout. No real metadata or catalog credentials are used.

## What this does not prove

- This tests SQLCipher/FTS5, not Cognee, Ladybug or DuckDB activation semantics.
- The revision callback simulates a permission/scope-change notification. It does
  not revoke a remote permission or model the resulting authorization decisions.
  Subsequent reads require a real policy layer; incrementing a revision alone is
  not authorization enforcement.
- The final revision check detects the injected interleaving, but does not hold a
  lock through host delivery. Changes after that check and concurrent multi-source
  snapshot capture remain untested. A production snapshot/revision protocol must
  define the exact point at which a response is authorized.
- The fixture's canonical snapshot is captured serially while no writer runs.
  Repeated per-source reads are not claimed to be an atomic multi-source read.
- Cleanup runs after all builders and readers stop. Real concurrent garbage
  collection needs leases or another reader-lifetime protocol.
- Crashes are process exits, not power-loss or corrupted-file tests. Immutable
  filenames, path validation, full schema/version validation, index tampering,
  exhaustive FTS completeness and migration are not production-hardened here.
- SQLCipher is used for the index and registry, but this is not a new full audit
  of filesystem artifacts or key management. The test-only key file is deliberately
  unsuitable for real metadata. No alternative backend encryption parity is implied.
- Search is a two-document fixture with one fixed query. It establishes activation
  behavior, not relevance, ranking quality, scale or bounded graph traversal.

## Architectural conclusion

A separate derived index can use validated immutable generations and a transactional
pointer without coordinating a distributed transaction with the canonical store.
Generation mismatch makes temporary unavailability explicit. Rebuilding an abandoned
candidate is simpler than attempting to resume an uncertain partial index.

That does not make a separate store the preferred default. It adds file lifecycle,
generation vectors, revision handling, temporary duplication and cleanup. For the
current SQLite-family backend, keeping canonical claims and indexes in one encrypted
transaction remains a simpler baseline. Use a separate projection only when a
measured retrieval capability earns those costs.

Next useful selection work is bounded path/evidence retrieval and relevance on
representative metadata, followed by a selection ADR. Do not turn successive spike
prototypes into an unrequested production framework. Any optional adapter still
needs the unproven policy/concurrency and encryption gates above.
