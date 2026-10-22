# Databricks ontology options for Copilot

**Checked:** 2026-10-22  
**Status:** Documentation research; no Databricks MCP endpoint was connected or called.

## Decision summary

If the requirement is to query **Genie Ontology's own inferred context**, Databricks documents Genie One and Genie Code as consumers of that ontology. Genie One MCP is the exposed integration for an external agent; there is no documented direct API/MCP that exports the complete Genie Ontology for Copilot to query without invoking Genie.

If the requirement is instead to give GitHub Copilot rich business semantics **without Genie at query time**, Databricks Labs' **Ontos** and **OntoBricks** are viable separate ontology/knowledge-graph systems. They do not expose or mirror Genie Ontology automatically. Ontology content must be authored, imported, curated, generated from metadata, or mapped into those systems.

**Recommended architecture: the Unified Ontology Layer (UOL), a provider-neutral ontology context layer with replaceable adapters, a user-controlled local snapshot, and a local user-authored overlay.** Local agents should answer from an indexed cache rather than pay a provider round trip for every ontology lookup. Sync is opt-in by source and scope; users can pause it, disable cache reads, request incremental or full refresh, inspect status, and purge synchronized data. Users can add attributed facts, relationships, and cross-source links locally without modifying provider systems. The UOL is not a universal canonical truth: preserve provider identity, permissions, freshness, claim-level provenance, and disagreements.

For a first direct-ontology adapter, **Ontos is the narrower candidate** for glossary/concept search and dbt-to-asset grounding. OntoBricks is a stronger candidate if the product needs a materialized, instance-level graph mapped from Unity Catalog tables. This recommendation is provisional until a real read-only tool contract is exercised. Neither is a way to fetch Genie’s private inferred snippets.

## Comparison

| Option | What Copilot can access | Genie required? | Main setup / trade-off |
|---|---|---:|---|
| Genie One MCP | Answers and citations grounded in Genie Ontology; the service selects relevant curated and inferred snippets and may generate SQL/query data | Yes, for this exact Ontology | Lowest re-modeling effort if the goal is Genie’s semantics. MCP calls invoke Genie’s answer workflow. |
| Ontos MCP | Ontos knowledge graph, glossary concepts, semantic links, product/contract context, and read-only SPARQL (`SELECT`, `ASK`, `DESCRIBE`, `CONSTRUCT`) | No | Broad governance platform. Ontology and links must exist in Ontos. MCP is HTTP with Ontos-issued scoped tokens; token scopes supplement, not override, Ontos permissions. Local development uses PostgreSQL; production deployment may use Databricks services. |
| OntoBricks MCP | Ontology structure/raw OWL-Turtle (`describe_ontology`) even before graph build; entity types, entity descriptions, graph status, GraphQL schema and queries, and selected quality/context tools after publication/build | No | Ontology is designed and mapped to UC assets, with graph materialization. Docs list Databricks App, SQL Warehouse, Lakebase Autoscaling, and UC as prerequisites. More suitable for an instance-rich mapped knowledge graph than a narrow term lookup. |

### Proposed provider-neutral contract

The agent-facing layer should expose stable read operations independent of provider-specific tool names, for example:

- `search_concepts(query, source_filters?)`
- `get_concept(concept_id, source_id)`
- `get_relationships(concept_id, source_id, depth?)`
- `resolve_asset(concept_id, source_id)` or provider-backed asset references
- `list_ontology_sources()`

Normal reads use the local snapshot. A separate sync-control interface configures sources and inclusion/exclusion rules, reports status, runs incremental or full refresh, pauses/resumes sync, disables cache reads, and clears synchronized data. User-authored overlay changes and overlay deletion are separate operations. Keep provider-specific cursors, retries, filtering, pagination, persistence, and atomic generation publication behind the UOL implementation.

Normalized records should carry at least `source_id`, provider-native concept IRI/ID, preferred label, definition, synonyms, typed relationships, linked asset identifiers, observed/freshness metadata, and access scope. Cache records also retain the successful sync generation/time, configured scope, and coverage. Attach provenance to every fact and edge, including source/native IDs, version, observation/sync time, and transformation or mapping evidence. A cross-source link is its own typed, attributed claim with endpoint identities, evidence, and review state. Keep the native payload or a stable source reference for traceability. Never collapse different concepts solely because their labels match. Cross-source equivalence requires an explicit stable identifier or reviewed mapping; conflicting definitions remain multiple attributed claims. If evidence is ambiguous, leave the claims unlinked rather than manufacturing a relation.

Sync defaults off until the user explicitly selects sources and scopes and enables it. Scope can include/exclude sources, namespaces, entity types, properties, or explicit record IDs; exclusions always win. Distinguish pausing refresh while preserving a snapshot from disabling cache reads and from purging synchronized data. Do not contact a source when sync and online fallback are disabled. Synchronize only data readable to the configured principal, retain the sync-time access scope, and define TTL/revalidation and revocation behavior before treating local records as currently authorized.

Make refresh resumable and idempotent. Use source change feeds/cursors only when their semantics are reliable; otherwise describe the operation as a full scan. Build a candidate generation separately and atomically publish it after validation. If a refresh fails, keep the last known-good generation and clearly mark it stale/partial; do not replace it with a partial graph. Apply confirmed source deletions and revocations, or surface when the provider cannot confirm them. Store cache data in user-scoped, protected local storage without credentials, and exclude it from version control.

Keep user-authored augmentation in a logically separate local overlay. Users may add attributed facts and relationships or review/create a typed link between provider claims when they have evidence. Record authorship, creation/update time, rationale/evidence, and link type; make it explicit that the overlay is a user assertion, not provider endorsement. Provider sync and synchronized-cache purge must preserve this overlay. Overlay deletion is a separate explicit action. Do not write user additions back to Ontos, OntoBricks, Unity Catalog, or other providers in the initial design.

Keep indexed local search and bounded relationship traversal independent of network availability and sync. Sync must not block interactive reads. Benchmark representative graph sizes and set numerical latency, scale, and recovery targets from evidence rather than choosing arbitrary thresholds.

## What “no Genie” does and does not mean

- **No Genie runtime:** Ontos or OntoBricks can serve their own semantics to Copilot through their MCP interfaces.
- **No Genie Agent:** Genie One MCP does not require creating a separate user-configured Genie Agent, but its `genie_ask` tool still invokes Genie One.
- **No access to Genie’s inferred ontology:** The documented Genie Ontology comprises curated Unity Catalog semantics (including metric views, domains, Pages) and inferred snippets from assets and usage. Databricks documents Genie One/Genie Code as the ontology consumers and does not document a direct endpoint to dump that inferred layer.
- **Direct UC semantics:** Metric views, domains, Pages, comments, and table metadata may be read through their supported Unity Catalog surfaces when permissions allow. This yields explicit modeled assets, not Genie’s full inferred snippets or its authority/relevance ranking.

## Fit for dbt-skills

The narrow POC should keep GitHub Copilot as the agent and exercise the generic context and sync contracts against one read-only ontology source, starting with Ontos:

1. Define the provider-neutral read contract and source/provenance fields before binding to a vendor tool.
2. Discover the configured backend's tools and inspect schemas. For Ontos, use a dedicated token scoped only for semantic reads and SPARQL queries; do not grant semantic write scopes.
3. Let the user select a small ontology scope containing business terms and links to fixture catalog assets; keep sync disabled until enabled. Resolve a term to a UC table/column and then to the matching dbt source/model using local manifest evidence.
4. Verify local indexed reads, scope filters, offline behavior, sync status, pause, cache-read disablement, incremental/full refresh, and synchronized-cache purge.
5. Inject pagination, interruption, rate-limit, and permission-revocation cases. Confirm sync can resume, repeated sync is idempotent, failed refresh leaves the last good snapshot intact, and stale permissions are not represented as current.
6. Verify provenance on every source fact and edge, including derived mappings; add a user-attributed local claim and review a cross-source link while preserving provider claims separately.
7. Test stable-ID links, reviewed mappings, name-only matches, conflicts, and ambiguous links. Only sufficiently evidenced or reviewed links become asserted graph edges.
8. Confirm user overlay additions survive provider refresh and synchronized-cache purge, and that overlay deletion is separate.
9. Return semantic claims and dbt evidence as separate attributed records. Do not infer a dbt model mapping from a business term alone.
10. Test conflicting terms from two providers as separate results; do not collapse them by label.
11. Keep Genie One as an optional answer provider only if the user wants Genie Ontology. Its answer/citations can be retained as attributed response evidence, but it is not a structured ontology backend until Databricks documents such an interface.

This tests whether the UOL can improve dbt source/model mapping. It does **not** test Genie Ontology itself. If the desired outcome is to use existing Genie-curated and inferred context without rebuilding it, the POC must instead call Genie One MCP. Future Genie enrichment can be added behind the same layer only if a structured, permission-aware source becomes available; until then, do not pretend that Genie One answers are a complete ontology feed.

## Cost, license, and authentication guardrails

- Databricks Free Edition is a no-cost, quota-limited offering. Its current documented limits include one 2X-Small SQL warehouse, up to three Apps, and one Lakebase project with scale-to-zero compute. Exceeding fair-use quotas can suspend compute; Apps and Lakebase/warehouse operations still consume limited resources. Availability can vary by region and workspace.
- OntoBricks documents SQL Warehouse and Lakebase Autoscaling as prerequisites; graph builds execute mappings through SQL. Do not use LLM generation, auto-mapping, graph builds, or Databricks-hosted models in the initial schema-only check. A later graph POC may fit within Free Edition, but confirm feature availability and quota before deploying or running it.
- Ontos supports local development with PostgreSQL and also documents Databricks deployment. A local setup can reduce Databricks compute use, but catalog access or remote deployment may still use Databricks resources. Do not promise zero cost without checking the actual path.
- Both repositories identify their license as the **Databricks License**, not an OSI-approved permissive license. Its terms restrict use to use within or connected to Databricks Services. This project may document or interoperate with them as optional external services, but must not make either an assumed unrestricted dependency; review the license before redistributing code or derivatives.
- Databricks recommends interactive OAuth/U2M for supported CLI and SDK use. However, the documented manual GitHub Copilot CLI MCP configuration uses a Databricks PAT as an HTTP Authorization header; the Databricks Unity Gateway `ug copilot` route signs in with Databricks but configures a Databricks-hosted model. If the user wants Copilot CLI and its normal model, prefer Copilot’s native MCP config and a short-lived, least-privilege **user** PAT stored outside the repository. OAuth CLI token caching is not automatically wired into Copilot’s static MCP headers; do not build a token bridge for this POC.
- Ontos MCP uses an Ontos-issued MCP token in `X-API-Key` and limits tools with token scopes. OntoBricks offers a local stdio server or a remote HTTP server; its per-domain MCP policy can control exposed tools. In either case, expose only read tools for the POC.
- No secrets, endpoints, or workspace identifiers belong in committed configuration. No MCP call that queries data, mutates an ontology, invokes a function/job, generates ontology content, or builds a graph is part of schema-only validation.

## Evidence reviewed

- [Genie Ontology](https://docs.databricks.com/aws/en/genie/genie-ontology)
- [Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Ontos repository and license](https://github.com/databrickslabs/ontos)
- [Ontos MCP and Ask Ontos](https://github.com/databrickslabs/ontos/blob/development/docs/handbook/mcp-and-ask-ontos.md)
- [Ontos ontology and knowledge graph](https://github.com/databrickslabs/ontos/blob/development/docs/handbook/ontology-and-knowledge-graph.md)
- [Ontos semantic-model MCP tools](https://github.com/databrickslabs/ontos/blob/development/src/backend/src/tools/semantic_models.py)
- [OntoBricks repository and license](https://github.com/databrickslabs/ontobricks)
- [OntoBricks MCP tools](https://github.com/databrickslabs/ontobricks/blob/master/docs/mcp.md)
- [OntoBricks prerequisites](https://github.com/databrickslabs/ontobricks/blob/master/docs/getting-started.md)
- [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
- [Databricks Apps billing overview](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Copilot CLI MCP setup](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)
- [Databricks Copilot CLI setup](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-copilot)
- [Databricks MCP authentication](https://docs.databricks.com/aws/en/agents/mcp-tools/authentication-networking)
