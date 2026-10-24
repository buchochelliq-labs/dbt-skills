# Native publication observation

Native validation and readback are read-only. No native write method, SQL execution,
query results, row samples, or simulated save receipts exist in this adapter.

The operator constructs `native_observation.adapter_from_config(config,
origin_revision_reader=backend_reader, authorization_reader=authorization_reader)`.
Configuration is trusted deployment configuration and must never come from a proposal:

```json
{"workspace_url":"https://your-workspace.azuredatabricks.net",
 "trusted_hosts":["your-workspace.azuredatabricks.net"],
 "token_env":"DATABRICKS_TOKEN",
 "targets":[{"kind":"genie","id":"exact-space-id","origin_id":"stored-uol-id"},
            {"kind":"unity_catalog","id":"catalog.schema.table","origin_id":"stored-uol-id"}]}
```

The token is resolved from the environment on each request. HTTPS, exact trusted
host and target checks, redirect rejection, 15-second timeouts, 2 MiB response limits,
and bounded tag pagination apply. Remote failure details and credentials are never
returned by the publication validator. The injected transport is only for local tests.

`origin_revision_reader(origin)` must read the current UOL revision from the backend;
it must not echo the revision supplied in a request. Target-to-origin mapping comes
from operator configuration and is checked against the proposal. The independent
`authorization_reader(target)` must freshly verify the relevant write permissions
and complete effective audience, returning `{"write":true,"audience":["principal"]}`.
Missing or incomplete permission/audience evidence blocks review. A successful
metadata GET alone does not establish permission to change metadata or its audience.
Do not substitute configured audience expectations for current authorization evidence.

Unity Catalog reads the exact table and its tag assignments. Only `comment` and
`tags` enter the editable document; unrelated table metadata is discarded. Native
conditional updates are unsupported and no timestamp/hash is presented as a native
conditional token. Genie reads the exact space with `include_serialized_space=true`.
The document preserves the entire parsed `serialized_space` and the returned title,
description, warehouse ID, and parent path. Selected paths merge into this complete
snapshot. An actual nonempty `etag` from that GET is required for conditional support;
missing ETags produce export-only validation. Permission checks can still block it.

Two independent native observations plus two backend origin revision reads detect
drift during validation. Readback performs another native GET and compares selected
values, audience and current origin revision. It does not infer that this application
performed a save: `native_write_performed` is always false and
`saved_acknowledgement` remains `unknown`, including after matching readback.

Official endpoint references checked on 2026-10-24:

- [Genie space API](https://docs.databricks.com/api/genie/v1/genie-space): GET `/api/2.0/genie/spaces/{space_id}`; serialized export requires CAN EDIT; optional native ETag is supported for conditional updates.
- [Table API](https://docs.databricks.com/api/uc-tables/v1/get-table): GET `/api/2.1/unity-catalog/tables/{full_name_arg}`.
- [Entity tag assignments](https://docs.databricks.com/api/uc-entity-tag-assignments/v1/list-entity-tag-assignments): GET `/api/2.1/unity-catalog/entity-tag-assignments/tables/{entity_name}/tags`; follow `next_page_token` until absent.

Tests use a fake HTTP transport only. No live credentials or writes are needed.

## Application actions

The browser and agent application command contract exposes these independent actions:

- `target.refresh {id}` reads the operator-allowlisted native destination, persists its exact metadata snapshot and fingerprint, and updates the editable local target view. UC `comment` is shown as `description` in the editor.
- `proposal.create` pins that snapshot's fingerprint and local target revision. Refreshing later does not alter a proposal's pin. Native proposals require an initial observation and the configured UOL origin binding.
- `proposal.check {id}` performs fresh native preflight and records its result on the proposal. It preserves unrelated native metadata in the suggested merged document.
- `proposal.reconcile {id}` independently reads back selected values. It records the observed result without creating a delivery receipt, save acknowledgement, or `Verified` delivery state.

The Changes screen provides separate controls for these actions. Imported application
exports discard native observations, fingerprint pins and validation results: they
must be observed again under current credentials. Current application audience UI
represents one audience; multi-principal observations stay `Unknown` and fail closed
until a complete audience review UI is available.
