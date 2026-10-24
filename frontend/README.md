# UOL workspace and Unity Catalog companion

The original React/Vite/React Flow workspace now uses the Python ontology application's authenticated local service. Domains, knowledge revisions, memberships, mappings, provider preferences, Pages and review history persist in encrypted SQLCipher storage. The browser contains no credentials and does not fall back to fixtures if the service fails.

## Run locally

The repository keeps the Python backend at its root and the UI in `frontend/`. Requires Python 3.11+ and Node.js 22+.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
. .venv/bin/activate
pip install -r requirements.txt
cd frontend
npm ci
cd ..
python scripts/run-local.py --frontend frontend --demo --ephemeral
```

Open **http://127.0.0.1:5173**. This explicit fictional demo uses the real Python application and encrypted database, discarding its temporary storage when stopped. No VS Code is required. Remove `--ephemeral` for persistence using the OS keyring, or use `--key-env` with an externally managed base64 32-byte key. Keep production keys outside the database directory.

For your project:

```sh
python scripts/run-local.py --frontend frontend --project-dir /absolute/project/path
```

The project supplies `modelling.yml`, `catalogs.json` and its dbt `artifacts/manifest.json`. Start with **Sync catalog**. Only project-referenced source/produced assets are fetched; ambiguous identities remain quarantined. UC/OpenMetadata credentials are server environment variables referenced by the operator configuration. See [local workspace](../docs/LOCAL_WORKSPACE.md), [Unity Catalog](../docs/UNITY_CATALOG.md), [OpenMetadata](../docs/OPENMETADATA.md) and [persistence](../docs/APPLICATION_PERSISTENCE.md).

The preview's `server/preview-config.json` explicitly chooses fictional fixtures and a frozen Linux backend; the source launcher overrides this configuration. Git excludes the frozen binary and generated UI assets. For a frozen preview, install PyInstaller in the backend environment, then run `python scripts/build-preview-backend.py --frontend frontend` from the repository root and `npm run build` in frontend. Rebuild after backend edits. Normal local use runs Python source. No runtime database, token or encryption key is committed.

## Original workspace

- **Domains:** stable nested identity, create/rename/move, inherited governance, knowledge revisions, approval and additional memberships. Approved edits become drafts; inferred origin stays inferred. Add Page knowledge to start a Page.
- **Knowledge graph:** typed relationships, interactive canvas, evidence inspector, search and keyboard list alternative.
- **Sources:** permitted catalog metadata, tables/columns, semantic mappings, lineage/access and exact proposed description/tag changes. Pages and Genie remain separate from physical schemas. UOL owns the companion screens.
- **Connections:** actual configured provider instances and ordered reading preferences. Credentials and metadata scope stay operator-controlled. Explicit demo mode additionally exposes simulated health and clock controls. TTL suggestions require acceptance. Free-form domain provider-policy text is stored/displayed governance; configured provider order/enablement and numeric TTL settings control resolution.
- **Agent context:** question/selected object, dynamic business scope, readable/JSON facts and export. Canonical server resolution checks visibility, denial, approval, business validity, provenance and cache eligibility. Deterministic matching is not a general LLM.
- **Changes:** pinned revisions and exact differences, separate review, selected delivery, native observation/preflight/readback, and reviewed handoff exports. Real native writes remain disabled. Demo delivery changes its simulated native store and verifies readback.

Ctrl/Cmd+K opens search. Mobile uses navigation drawers and section pickers; graph has a list alternative. Dirty navigation asks to keep/discard edits. Async saves acknowledge server success before clearing drafts.

## Persistence and imports

Use **Import / export workspace**. Export has `schema_version`, `simulation` and state. Import validates shape, references and cycles, shows a server-generated replacement preview, and applies only against the reviewed revision. Imported native observations, permissions and cached facts cannot authorize access: they are reset; providers are disabled and proposals return to draft. Re-sync and review before use. Live and simulation stores cannot be mixed.

Additional memberships appear in the selected domain and, when enabled, its descendant scope; overlapping memberships count once and do not change the primary owner. Reader changes use the same unsaved-edit guard as navigation. Page and domain-projection exports retain the actual server simulation flag.

Legacy real source snapshots without per-group provenance require one explicit **Sync catalog** before becoming visible again. A removed declared field retains its mapping as **Needs review**. After the field returns and is synced, choose **Review mapping** explicitly; restoration does not silently restore approval. Source unavailability, permission denial or changed identity/revision withholds dependent facts and observations from outward reads/exports.

Every application mutation is a named command with optimistic concurrency. The service is a single-user loopback boundary, not a deployed multi-user authorization service.

## Verify

```sh
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python tests/agent_flow_acceptance.py
cd frontend
npm run typecheck
npm run build
npm test
# With the explicit demo running; install Playwright browser once on your machine:
npx playwright install chromium
npm run test:browser -- http://127.0.0.1:5173
```

Six portable browser journeys run through Playwright or the managed browser. Run the connected save/reload/actual-download journey with `npm run test:browser:connected -- http://127.0.0.1:5173`. Additional reader-switch and membership regressions are exported from `tests/browser/reader-switch-regression.mjs` and `tests/browser/membership-regression.mjs` for a Playwright page. Start each suite from a fresh page load.

## Implementation boundaries

`src/store.tsx` is an HTTP repository client. `src/dbt_skills/application_commands.py`, `application_resolver.py` and `application_store.py` own authoritative policy/mutations/persistence. The core modelling/catalog service supplies scoped provider facts; approved mapped ontology context uses the same resolution gate. Presentation helpers remain in `src/services.ts`; its old mutation/fixture functions are regression references and are not called by production screens.

Native observation is authenticated, bounded and metadata-only. Actual write permission/audience remains unknown unless a trusted authorization callback supplies evidence. Unsupported destinations, missing conditional updates and Pages use reviewed handoffs. Live UC/OpenMetadata/Genie tenant compatibility has not been tested with credentials. No source rows, arbitrary query execution, native grants, live writes, ontology-indexing success, Genie answer use or measured cache savings are claimed.

The production `dist/client/index.html` references the current bundle. Serve it with the local API proxy; a standalone HTML file cannot run Python or encrypted storage. `UOL-Workspace.html` is now a local startup guide, not a disconnected mock application. No public deployment was performed.
