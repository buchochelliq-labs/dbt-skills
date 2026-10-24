# Complete application persistence

`dbt_skills.application_store.ApplicationStore` stores the original UOL `State`, not a generic authored-record substitute. The encrypted SQLCipher database retains domains, knowledge and its revision history, provider configuration, source metadata, relationships, mappings, cache entries, observations, publication proposals, native target observations, delivery attempts, pages, and all clock/configuration preferences. It uses the existing OS keyring and SQLCipher primitives; missing encryption support fails closed. No source data rows are needed or accepted as source-asset fields.

```python
store = ApplicationStore(path, key_store=None, initial_state=None, simulation=False)
snapshot = store.read()  # {revision, state}
updated = store.transact(snapshot['revision'], mutate, reason='Reviewed edit')
# mutate(state) modifies its isolated candidate and may return a JSON result.
# updated is {revision, state, result}.
store.history()  # all committed revision numbers and reasons, newest first
export = store.export()  # schema_version=1, kind=uol-application, simulation, revision, state
preview = store.preview_import(export)  # preview_id, expected_revision, diff, state
snapshot = store.apply_import(preview['preview_id'])  # revision, state
```

`initial_state` is used only when initializing the database. The default is `empty_state()`. The simulation flag is durable database metadata, never inferred from user records; reopening with another flag does not relabel an existing store. Explicit simulation fixtures should use a separate database with `simulation=True`. Simulation and live imports cannot be mixed.

Every transaction takes a SQL `BEGIN IMMEDIATE` lock, checks its expected revision, runs the mutation on a detached state, validates the complete candidate, and inserts one immutable revision. Exceptions, invalid records, and stale revisions roll back the whole transaction. SQL locking protects against separate store objects/processes as well as the in-process lock. The revision log survives restart. `ApplicationError` and `ApplicationConflict` alias the existing workspace error classes.

Validation enforces the complete frontend contract with closed record schemas, bounded strings/arrays/maps, a one MiB serialized limit, nesting and node limits, unique collection IDs, valid internal references, distinct source field paths, domain/source hierarchy acyclicity, and acyclicity for each hierarchical relationship type. Target IDs may intentionally equal source asset IDs. Knowledge `related` links may reference knowledge, pages, domains or assets. The legacy optional `freshness` display string from the original data fixture is preserved. Additional memberships must be unique, reference existing domains, and exclude the primary owner. Provider scopes, source paths, mapping field expressions and page sources are declarations and need not be locally discoverable; they never establish native permissions.

## Import trust policy

Preview validates the original full envelope before any changes. An Approved mapping to a field absent from a supplied nonempty source-field inventory is rejected before that inventory is sanitized. Empty/redacted inventories and historical Draft/Needs review pointers remain representable; they confer no source authority. It produces the complete candidate, before/after collection counts, changed collection flags, changed preference names, and a `security_resets` list of every affected record/field. Nothing changes until applying that preview. Preview tokens are single use, process-local, limited to sixteen pending previews, and bound to the current revision. Any intervening committed edit makes application fail with a conflict.

Authored knowledge (including its full revision history), domains, mappings, relationships, page content, provider connection/scope/TTL preferences and application preferences are restored. Imported historical approval labels describe authored records only; they do not authorize a native action. External observations and native authority claims are reset as follows:

- Cache entries and cache observations are cleared, with their counts reported.
- Providers are disabled, their health set to denied, and all capability outcomes set to unknown. Connection preferences remain for explicit revalidation.
- Source assets become hidden, restricted identity placeholders. IDs, native IDs, provider IDs, names, types, hierarchy and authored association references remain so mappings and pages retain valid references. Owner, description, tags, fields, observation time and source revision are cleared; imported per-group `sourceEvidence` is removed. These placeholders are not trusted discovery results and must be replaced by authorized adapter discovery.
- Targets retain identity and audience preferences, but content/origin receipts are cleared, revision is zero, permission and capability are unknown, and atomic/failure simulation switches are false. Native adapters must reread targets and authorize actions.
- Proposals retain authored before/after payloads and evidence for review, but become Draft, lose review decisions/timestamps and reset expected native revision. No imported proposal is ready to publish.
- Delivery attempts remain historical records with their message and timestamp, but their state becomes Draft, acknowledgement is false and readback is unknown. Imported historical messages are never permission or delivery receipts.

The sanitized candidate is validated again. The exact reset details and resulting state are visible in the preview, so imported external metadata is never silently discarded. Normal authenticated local transactions persist the complete state without this import sanitization; import is a separate trust boundary. Export contains the current application state, including nested knowledge history and delivery history; database audit revision rows remain local and are never replaced by imported revision claims.

## Source-dependent observations

Actual source sync stores canonical provenance separately for relation and column fact groups. Outward snapshots and exports reauthorize these groups through the project core and withhold dependent cache/observation records when the source is unavailable, denied, changed or outside project scope. Raw durable history remains retained. Cache identity includes canonical source identity as well as revision; a byte-identical file at a different document path does not reuse facts citing the old path. Provider TTL is selected from the provider that supplied the fact group.

Legacy real snapshots without per-group evidence need one explicit Sync catalog. A removed field changes its mapping approval to Needs review; restoring the field does not reapprove it. Current evidence and explicit review are required.
