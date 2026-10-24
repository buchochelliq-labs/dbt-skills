# Application architecture

The original React/Vite/React Flow workspace is retained. Authoritative application commands, context resolution and persistence now run in Python. The UI has no provider credentials or silent fixture fallback. An explicit server-selected fictional mode exercises the same command and storage contracts.

```mermaid
flowchart TB
  UI["Original UOL and UC companion"] --> API["Authenticated loopback application"]
  API --> STORE["SQLCipher revision store"]
  API --> RES["Canonical policy and fact resolver"]
  API --> PLAN["Publication review commands"]
  RES --> CORE["Existing project and catalog core"]
  CORE --> CACHE["Scoped metadata and permission cache"]
  CORE --> UC["Unity Catalog adapter"]
  CORE --> OM["OpenMetadata adapter"]
  CORE --> AUTH["Authored file adapter"]
  PLAN --> OBS["Native observation and preflight"]
  PLAN --> HANDOFF["Reviewed handoff export"]
  PLAN --> DEMO["Explicit simulation target store"]
```

Provider and native interfaces permit metadata only. Original screens send named commands and expected repository revisions. Server filtering precedes snapshots and exports. Model planning reuses canonical resolution for approved mapped ontology evidence. Real native delivery is disabled; preflight/readback are separate from save acknowledgement. Editing and import are atomic and revision checked. No browser state constitutes authority. Real source snapshots retain separate relation/column provenance; current permission and source identity/revision gate dependent facts, observations and exports. Cache identity includes the actual document/locator, and provider-level TTL follows the selected fact provider.

# Domain hierarchy and projection

```mermaid
flowchart TB
  E["Enterprise"] --> C["Customer"]
  E --> F["Finance"]
  C --> L["Lifecycle"]
  L --> R["Retention"]
  F --> RC["Receivables"]
  RC --> CO["Collections"]
  R -. "ancestor choice" .-> NL["Native Customer / Lifecycle"]
  R -. "flatten choice" .-> NR["Native Customer / Lifecycle-Retention"]
```

A third choice retains the hierarchy only in UOL. Dotted edges are alternative
projections, not multiple parents. Stable UOL ID and full path are exported. Native
parent/subdomain governed-tag keys are explicit. A Page's UOL owner domain never moves
as a side effect. Projection is proposed as a tags change, not an invented native
ontology field. Collision detection is limited to the fictional domain inventory.

# Semantic model and evidence

```mermaid
erDiagram
  DOMAIN ||--o{ DOMAIN : parents
  DOMAIN ||--o{ KNOWLEDGE_OBJECT : owns
  DOMAIN }o--o{ KNOWLEDGE_OBJECT : memberships
  KNOWLEDGE_OBJECT ||--o{ KNOWLEDGE_REVISION : versions
  KNOWLEDGE_REVISION ||--o{ FACT : declares
  FACT ||--o{ FACT_EVIDENCE : supported_by
  PROVIDER_INSTANCE ||--o{ FACT_EVIDENCE : supplies
  PROVIDER_INSTANCE ||--o{ SOURCE_ASSET : exposes
  SOURCE_ASSET ||--o{ SOURCE_FIELD : contains
  KNOWLEDGE_REVISION ||--o{ SOURCE_MAPPING : maps_through
  SOURCE_ASSET ||--o{ SOURCE_MAPPING : target
  KNOWLEDGE_OBJECT ||--o{ SEMANTIC_RELATIONSHIP : participates
```

`contracts.ts` defines the records, scoped definitions, evidence, cache observations,
resolution results, target observations, proposals and delivery attempts. Approval,
origin, confidence, authority, freshness, validity and reader policy are separate.
Mappings store `assetId` and `fieldPath` separately. Provider/native IDs disambiguate
identical fully qualified names. Delivery stores original semantic IDs and revisions;
read-back does not create a second fact or increase confidence.

# Typed relationships

```mermaid
flowchart TB
  CUSTOMER["Customer"] -->|holds| ACCOUNT["Account"]
  ACCOUNT -->|groups| SERVICE["Service"]
  INDIVIDUAL["Individual customer"] -->|is_a| CUSTOMER
  ACTIVE["Active customer: Service"] -->|qualifies| CUSTOMER
  BILLING["Active customer: Billing"] -->|qualifies| CUSTOMER
  METRIC["Active customers metric"] -->|defined by| ACTIVE
  CUSTOMER -. "mapped to" .-> TABLE["customer.core.customers"]
  METRIC -. "implemented by" .-> MV["customer.metrics.active_customers"]
```

Graph type colors, dashed semantic/mapping edges, inspectable direction and a keyboard
list distinguish relationships. A separate contract-line part_of edge demonstrates
composition. Native lineage never becomes a declared business relationship.

# Resolution of one fact

```mermaid
flowchart TB
  START["Required fact"] --> VISIBLE{"Identity visible?"}
  VISIBLE -->|No| HIDDEN["Same unavailable result as missing identity"]
  VISIBLE -->|Yes| ACCESS{"Reader and origin policy permit?"}
  ACCESS -->|No| DENIED["Denied; no cache or replica fallback"]
  ACCESS -->|Yes| SCOPE{"Scope, approval and validity eligible?"}
  SCOPE -->|No| HOLD["Clarify or withhold values"]
  SCOPE -->|Yes| NEXT["Next enabled provider in order"]
  NEXT --> CACHE{"Eligible provider-specific cache?"}
  CACHE -->|Yes| RETURN["Fact with original evidence"]
  CACHE -->|No| RESULT{"Adapter outcome"}
  RESULT -->|Sufficient| RETURN
  RESULT -->|Denied| DENIED
  RESULT -->|Malformed| ERROR["Visible error; block packet"]
  RESULT -->|Missing or unavailable or unsupported| MORE{"More providers?"}
  MORE -->|Yes| NEXT
  MORE -->|No| INCOMPLETE["Incomplete required context"]
```

The cache check is provider-specific inside ordered traversal so reordering providers
cannot silently select old lower-priority evidence. Reader/origin policy precedes all
cache use. Cache keys include semantic revision, fact, scope, provider, reader, policy
and configuration versions. In this small demo configuration changes conservatively
clear all provider cache entries; human-owned revisions/decisions remain untouched.

TTL order: object override, nearest explicit domain override, provider default,
workspace 24h. Enterprise has no explicit TTL override. Cache reads retain original
observation times. Recommendations require at least three actual same-fact retrievals
within one mock hour and only apply after acceptance.

# Publication states

```mermaid
stateDiagram-v2
  [*] --> Draft
  Draft --> Reviewed: approve
  Reviewed --> Conflict: target or UOL revision changed
  Reviewed --> Unsupported: capability unavailable
  Reviewed --> Failed: permission, audience, dependency or write failure
  Reviewed --> Saved: mock target acknowledges
  Conflict --> Draft: rebase and review again
  Unsupported --> Exported: reviewed handoff
  Failed --> Saved: selected retry passes checks
  Saved --> Verified: store read-back matches
  Saved --> Mismatch: store read-back differs
```

Checks run synchronously in this mock. Saved is an intermediate state reflected in
acknowledgement receipts. Indexing and answer use remain unknown. Full Genie conflicts
must reopen the complete target snapshot; simple field rebase returns to Draft.

# Catalog-to-publication journey

```mermaid
flowchart TB
  EXPLORER["Catalog explorer"] --> TABLE["Table or metric detail"]
  TABLE --> FIELD["Column or measure inspector"]
  FIELD --> MAP["Semantic mapping workbench"]
  MAP --> TERM["UOL definition"]
  MAP --> PROPOSAL["Exact native field proposal"]
  TERM --> CONTEXT["Agent context preview"]
  PROPOSAL --> REVIEW["Review and audience checks"]
  REVIEW --> DELIVERY["Selected delivery and reconciliation"]
  DELIVERY --> TABLE
```
