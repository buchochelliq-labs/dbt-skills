# Generation recovery and proposed projection gate

2026-10-23. Fourth slice of #62. Disposable experiment; no product changes.
Continues [the policy assessment](POLICY_FIT.md).

## What was actually exercised

`recovery_probe.py` uses the real `LocalOntologyStore`, SQLCipher connection and
generation publication implementation. It creates a tiny synthetic source, then
updates one claim, deletes another and adds a third. Full and incremental modes
are each tested at three interruption points, using a fresh temporary database.

A child subclass inserts `os._exit(73)` hooks after real store operations. This
terminates the process without exception handling or connection cleanup. The
parent verifies the exit code, opens a new store instance, checks exact claim values
and generation identity, and checks lexical search. An incomplete sync is resumed;
a second reopen checks the final generation and original observation timestamp.

| Interruption point | Full sync on reopen | Incremental sync on reopen |
| --- | --- | --- |
| After first page is committed to staging | Complete old generation | Complete old generation |
| After first claim upsert, inside uncommitted publication transaction | Complete old generation | Complete old generation |
| After publication commit, before successful return to caller | Complete new generation | Complete new generation |

All six cases passed. Every interrupted pre-commit case resumed to the exact new
claim set. Search results agreed with the recovered claim generation. Committed
updates survived loss of the caller's success response. Raw results:
[recovery.json](results/recovery.json).

These results support retaining the existing encrypted generation writer. They
do not prove power-loss durability, concurrent-reader behavior, corrupt-file
recovery, keychain availability, remote cursor stability or cross-store atomicity.
The provider fixture is deterministic across restart. Test-only `FileKeyStore`
shares a synthetic key between processes and is not a supported product key store.
An `os._exit` test does not simulate a machine losing unflushed filesystem writes.

The product preserves the last published source generation during staging; this
experiment does not reinterpret that as freshly verified remote authorization.
Catalog permission validity remains a separate check above any retrieval result.

## Proposed gate: contract exercise, not adapter acceptance

The same script contains a small **prototype** gate over the recovered claim set.
It accepts an envelope with project, generation, claim IDs and completeness, plus
a captured policy snapshot. It resolves values from canonical claims, never from
an index payload. The following nine cases run for each recovered scenario:

| Case | Expected response |
| --- | --- |
| Matching complete generation and valid permission | Canonical values |
| Previous generation | Unavailable; no claims |
| Wrong project | Unavailable; no claims |
| Permission at its expiry boundary | Unavailable; no claims |
| Revoked allowlist | Unavailable; no claims |
| One asset removed from scope | Whole result unavailable; no claims |
| One claim quarantined | Whole result unavailable; no claims |
| Incomplete projection | Unavailable; no claims |
| Unknown evidence ID | Whole result unavailable; no claims |

All 54 case checks passed. These are checks of the proposed rule, not independent
evidence that the shipped host tools or Cognee already enforce it. There is no real
projection database in this script. One synthetic source uses local IDs; a production
adapter must use source-qualified claim identities and multi-source generation
bindings. It must also validate input shape, budgets, policy revision and completeness
of the index itself, rather than trust a boolean supplied by an untrusted adapter.

A production implementation needs an atomic captured snapshot or a final revision
check to handle permission changes during retrieval. This fixture changes policy
between requests only. It does not test an in-flight revocation race. Removing a
denied hit from a ranked result is not sufficient to claim the remaining answer is
complete: it may change ranking, paths or the evidence needed for the answer.

## Reproduce

Use the existing product dependencies, including SQLCipher; no Cognee installation
is needed. Run from the repository root:

```sh
python experiments/offline_backends/recovery_probe.py --output /tmp/recovery.json
PYTHONPATH=src:tests python -m unittest test_ontology test_catalog_cache_restart -q
```

The script imports existing test fixture providers and the test-only key store. It
sets a 30-second child timeout. Each child owns only a temporary synthetic database;
no source data, network provider or real key store is contacted by this probe.

## Recommendation and next boundary

The simplest safe initial strategy is to withhold retrieval when its generation
does not match the authorized canonical snapshot, then rebuild and validate before
activation. This trades availability for an explicit result; it avoids creating a
distributed transaction between the canonical store and each optional engine.

Still needed before adapter acceptance:

1. A real derived-index build interrupted before and after pointer activation,
   including restart and cleanup of abandoned generations. The present work proves
   only the canonical writer's recovery and a prototype gate.
2. Multi-source generation identity and policy revision binding, including scope,
   quarantine and permission changes while retrieval is in flight.
3. Encrypted artifacts throughout the selected adapter and supported deployment.
4. Useful bounded path/evidence retrieval and explicit incomplete-result reporting.

Keep #62 open. Do not turn this probe into an additional production persistence
layer or claim Cognee recovery/encryption parity from the SQLCipher results.
