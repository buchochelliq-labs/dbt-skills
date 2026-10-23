# Backend selection options — proposed decision

2026-10-23. Status: **proposed for maintainer selection**, not an accepted ADR or
authorization to change production storage. Evidence is linked from [README.md](README.md).

## Recommendation

Choose option 1 for the current product. Keep a narrow future retrieval seam, and
reconsider option 2 or 3 only when representative queries show a material benefit.
Do not implement multiple backends now just to demonstrate configurability.

Catalog providers remain independently configurable and ordered. Choosing local
SQLCipher does not limit Unity Catalog, OpenMetadata or hand-written metadata inputs.
Human-owned standards and decisions stay separate from evictable provider cache
records even if they share storage technology.

## Options and tradeoffs

| Option | Advantages | Drawbacks / unresolved gates | Assessment |
| --- | --- | --- | --- |
| **1. SQLCipher canonical store; SQLite FTS5 and indexed edges as retrieval baseline** | Existing encrypted-store primitives and key management; lowest added dependency/lifecycle complexity; measured project-sized lookups, lexical queries and endpoint traversal are competitive; real generation crash/restart tests pass. One transaction can maintain canonical facts and their indexes. | We own relevance tuning, path retrieval and budgets. Lexical search does not infer arbitrary paraphrases. Our bounded evidence-path prototype is not product functionality; dense paths still need limits. FTS5 capabilities must remain verified in supported builds. | **Recommended now.** Keep current persistence; make only demonstrated retrieval improvements. This does not mean every prototype is already shipped. |
| **2. SQLCipher canonical store + optional Cognee retrieval projection** | Reuse demonstrated graph-only ingestion, dataset isolation and source-aware shared-node deletion. Provides a route to richer retrieval without handing policy authority to a framework. Optional install can preserve the lightweight default. | Tested setup writes plaintext across input, relational and graph stores. Graph-only deletion needs pre-staged tokenizer artifacts. Measured environment/startup footprint is substantial. Requires identity translation, generation coordination, cleanup and independent catalog authorization. No maintenance reduction or relevance advantage demonstrated yet. | Credible conditional candidate; encryption and useful retrieval benefit are adoption gates. |
| **3. SQLCipher canonical store + direct Ladybug graph projection** | Direct graph API/query control; potentially useful if multi-hop graph work becomes the dominant workload; fewer framework responsibilities than Cognee. | We own adapter lifecycle, provenance/deletion mapping and generation coordination. Tested 0.21.2 parameterized FTS crashes; that finding does not apply automatically to Cognee's 0.19.0. Writable process ownership and encryption coverage need a supported solution. No general performance win demonstrated. | Consider for a specific proven graph requirement, not because the domain is a graph. |
| **4. DuckDB as replacement or analytical projection** | Embedded SQL and an analytical query route; worth reconsidering for substantial bulk metadata analysis. Documented encryption exists, but parity was not tested here. | Current project-context benchmarks do not justify replacement. Tested FTS updates needed rebuild; root cause remains unresolved. Writable multi-process access needs coordination. A replacement also takes on migration, provenance and lifecycle obligations. | No present case for switching. An analytical sidecar would need a concrete user workload. |
| **5. Cognee owns canonical persistence and retrieval** | Largest potential removal of our persistence/ownership machinery if a complete fit can be demonstrated; coherent framework-managed storage lifecycle. | Greatest migration and coupling cost. Dataset ACLs do not replace catalog permission lifetimes; core still owns policy, quarantine and human decisions. Encryption parity, atomic multi-source snapshots, offline lifecycle and net code reduction are not demonstrated. | Do not select now. Not permanently ruled out, but evidence is insufficient. |

RDF/Oxigraph is a separate future option if RDF/SPARQL interoperability becomes a
requirement. It was desk-screened, not benchmarked. Vector stores are not substitutes
for canonical facts or evidence-bearing relationships; consider them only if semantic
retrieval earns its model, storage and offline costs. No vector benchmark was run.

## Final retrieval sanity check

`retrieval_probe.py` uses SQLCipher, real FTS5 and indexed evidence-bearing edges.
Eight synthetic lexical cases cover an underscored identifier, dotted identifier,
normal-form abbreviation, business acronym expansion, curated synonym, ordinary
term, typo and unconfigured paraphrase. Six queries return the expected nonempty
sets; the typo and paraphrase correctly expose lexical misses. Matching foreign-
project text is excluded. Aliases are supplied explicitly as fixture metadata;
the engine did not infer them. This is not a measured semantic-search accuracy score.

The graph fixture has a cycle, two distinct paths to the same endpoint and a foreign
project edge. Three checks establish exact evidence paths, an edge-budget stop and
a path-budget stop. Results report `complete_within_depth` or `truncated` rather
than silently returning a partial complete answer. Each adjacency fetch is limited
to the remaining edge budget plus one lookahead row; a covering index supports it.
There is no measured wall-clock cancellation guarantee. Simple paths omit revisits;
this is not enumeration of every possible cyclic walk.

Raw results: [retrieval.json](results/retrieval.json).

```sh
python experiments/offline_backends/retrieval_probe.py /tmp/retrieval.json
```

This small curated corpus is a baseline sanity check, not representative user
relevance validation or an engine-to-engine quality comparison. Ranking, ambiguity,
larger natural-language corpora and actual user queries remain to be evaluated.
SQLite's documented tokenizer and phrase behavior explains why lexical configuration
matters: https://www.sqlite.org/fts5.html . Conclusions about other engines above
come from our pinned-version experiments, not assumed current-version behavior.

## What would change the recommendation

- Representative queries consistently need paraphrase/semantic retrieval and a
  candidate improves judged relevance without widening scope or weakening evidence.
- Bounded path/evidence workloads show an operationally meaningful advantage that
  survives encryption, startup and index-maintenance costs.
- Cognee removes demonstrably more code and maintenance than its integration adds,
  while satisfying the same permission, generation and encrypted-persistence contract.
- A real analytical workload makes DuckDB useful independently of context lookup.

Next action is maintainer selection of the direction, then a small implementation
issue for the chosen user-facing retrieval gap. Remaining production acceptance
checks belong to that chosen scope. Do not keep expanding this spike into a backend
framework or treat all optional adapters as required work. Keep #62 open until the
selection is recorded and its remaining deliverables are reconciled.
