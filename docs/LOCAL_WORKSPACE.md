# Run the original UOL workspace locally

The original React screens now use `OntologyApplication` through authenticated loopback HTTP. The existing project/catalog MCP core supplies metadata context. The SQLCipher application store persists complete domains, knowledge revisions, memberships, mappings, provider preferences, Pages, proposals, observations and history. No separate workbench is required.

From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd frontend
npm ci
cd ..
python scripts/run-local.py --frontend frontend --demo --ephemeral
```

Open http://127.0.0.1:5173. This explicit demo runs actual Python commands and encrypted persistence over fictional metadata. `--ephemeral` discards its encrypted test database and process-held key when stopped. Remove that flag for durable local demo storage backed by OS keyring. For a real configured project, replace `--demo --ephemeral` with `--project-dir /absolute/project`.

The launcher starts both processes, generates a process-only loopback session token, checks the backend and frontend API readiness, and stops both on Ctrl+C. An already occupied port is rejected before reporting readiness; recently closed ports can be reused normally. No VS Code is involved. `--data-dir`, `--backend-port`, `--port` and `--no-browser` are available. `--key-env NAME` selects an externally managed base64 32-byte key instead of the native keyring. Losing the key makes the encrypted database unreadable; there is no plaintext fallback. Never keep production keys beside the database or in browser variables.

## Project and provider configuration

The project supplies `modelling.yml`, `catalogs.json`, and `artifacts/manifest.json`. Choose **Sync catalog** to ingest only project-referenced sources and outputs; ambiguous identities remain quarantined. Configure UC/OpenMetadata endpoints, exact identities, trusted hosts and credential-environment names in the operator-owned catalogs configuration. Free-form domain provider-policy text is descriptive governance, not an executable ordering language. Browser controls can reorder/enable configured instances and change TTL; they cannot add endpoints or change source scope. See UNITY_CATALOG.md, OPENMETADATA.md, CATALOG.md#project-membership-delta-sync-and-quarantine and CATALOG_CACHE.md.

Removing or renaming a configured provider retains a disabled reference so existing mappings and history remain valid. Its source assets and native targets are withheld. Restore the provider in operator configuration and sync to make it available again; browser controls cannot reactivate a removed provider.

The launcher uses conventional filenames. For different paths or native observation configuration, start the service directly with `python -m dbt_skills.workspace_service --help` and give the frontend the same `UOL_LOCAL_TOKEN` (or owner-only `UOL_TOKEN_FILE`). API binds 127.0.0.1, checks host/origin/token, bounds JSON and rejects unknown commands. The frontend proxy enforces same-origin POST. This is a single-user local product; not a multi-user production server.

## Contracts and authority

- POST `/api/application/read`: server-filtered snapshot, revision, trusted reader and simulation flag.
- POST `/api/application/command`: `{name,payload,expected_revision}`. Atomic validated commands, conflict on stale revision.
- `context.resolve`: canonical visibility/permission/approval/validity checks, per-fact provenance and reader-scoped cache.
- `workspace.export`, `workspace.import.preview`, `workspace.import.apply`: bounded schema and reference validation, exact replacement preview, revision checked apply. Imported permissions and native evidence cannot confer authority.
- `/api/context`, `/api/tools`, `/api/tool`: existing core contracts. Model planning attaches only ontology facts passing canonical resolution.

Legacy generic authored-document endpoints remain compatibility interfaces; original screens use the complete application repository. Static fixtures and old mutation helpers are no longer the browser's active repository/resolver. Real readers cannot switch trusted server identity with a request parameter; fixture mode alone exposes simulated readers.

## Existing source snapshots and field reviews

After upgrading, a real source snapshot without separate relation/column provenance is withheld until one explicit **Sync catalog**. Sync preserves source identities and original observation times when evidence is unchanged. Changed source identity/revision, source denial and unavailability withhold dependent cached facts and observations from reads and exports.

If a mapped declared field disappears, sync retains its mapping as **Needs review**. Reapproval is rejected while the field is absent or its current source cannot be authorized, without advancing the repository revision. Restore the source field, sync, and explicitly choose **Review mapping**. Returning source metadata alone does not restore approval.

## Native observations

Use `--native-config` for exact UC/Genie target allowlists. Native observation, preflight and readback are separate UI actions. Add `provider_id` to configured Genie targets when multiple UC instances exist; no instance is guessed. Matching readback never asserts the app saved anything. Live writes are disabled and unknown permission/audience blocks publication. Review/export remains available. See NATIVE_PUBLICATION.md.

## Testing without VS Code

```sh
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python tests/agent_flow_acceptance.py
```

The acceptance scripts exercise the actual local application without VS Code.

The managed preview bundles a frozen Python executable in its Node container, so browser regressions run against the same Python application instead of an in-browser substitute. Rebuild with `scripts/build-preview-backend.py --frontend PATH` after backend edits. Normal local use needs no frozen binary. Credentialed tenant integration remains unverified; protocol tests use injected HTTP transports.
