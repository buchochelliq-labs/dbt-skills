# Local Unified Ontology Layer

The local UOL core provides an indexed SQLite graph, opt-in source sync, claim-level provenance, source scopes, and a separate user-authored overlay. Development sources include local JSON snapshots, a project-matched dbt manifest, and optional ODS MCP column-lineage analysis. The local stdio MCP bridge lets a compatible agent query this cache and invoke separately exposed sync/cache controls. No Ontos, OntoBricks, Unity Catalog, or Genie adapter is included; this prototype does not imply that those systems can currently be synchronized.

## Encrypted local cache

The local database is encrypted with SQLCipher 4 and a random 256-bit key stored in the current user's native credential store (Windows Credential Locker, macOS Keychain, or Linux Secret Service/KWallet). The application refuses to open or create a cache if SQLCipher, an approved OS key-store backend, or filesystem access protections are unavailable; there is no plaintext fallback. Linux requires an active Secret Service or supported KWallet session. The database, WAL/SHM sidecars, and SQL temporary storage are encrypted or memory-only. The cache directory and files are restricted to the current user (and Windows SYSTEM); startup fails if ACLs or POSIX permissions cannot be established and verified.

Install the pinned dependencies before using the CLI or MCP server:

```powershell
python -m pip install -r requirements.txt
```

Existing caches created by earlier versions are plaintext and are intentionally rejected. Stop every UOL CLI/MCP process using the cache, then migrate it explicitly:

```powershell
python -m dbt_skills.ontology_cli --db .\.uol-cache\ontology.sqlite3 protect-cache
```

By default, migration keeps an encrypted recovery copy beside the database at `<database>.encrypted-backup`. You can choose another path with `protect-cache --backup <path>`. The command verifies the source and encrypted result before replacing the original file, checkpoints and removes legacy plaintext WAL/SHM sidecars, and leaves the original untouched if verification fails. Do not remove the recovery copy until the encrypted cache has been verified and backed up according to your retention policy. Restore it to the original database path: the key-store entry is bound to that path. The migration cannot erase historical plaintext copies, filesystem snapshots, backups, or flash-storage remnants; find and protect or remove those separately.

The encryption key is not stored in the database, repository, or logs. Losing or deleting the OS key-store entry makes the cache and its encrypted recovery copy unrecoverable; retain an OS-protected backup of the credential store as part of the user's system backup plan. Key rotation is not yet exposed. Encryption protects cache files at rest, not data from a compromised user account, an authorized process while the key is loaded, or an unlocked credential-store session. Do not store provider credentials in the cache.

## Run the CLI

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m dbt_skills.ontology_cli --help
```

The default database is stored in the current user's application-data directory, outside the repository. Set `--db <path>` before the command to select another database. Keep the database in a private user-owned location; do not commit it.

Registering a JSON snapshot does not enable it:

```powershell
python -m dbt_skills.ontology_cli source add-json finance .\examples\ontology.json
python -m dbt_skills.ontology_cli source enable finance
python -m dbt_skills.ontology_cli sync finance
python -m dbt_skills.ontology_cli status
python -m dbt_skills.ontology_cli search "net bookings"
python -m dbt_skills.ontology_cli neighbors "finance:net_bookings"
```

The snapshot is synchronized only when the user runs `sync`. Use `--full-refresh` to replace the synchronized generation; `--restart` discards any incomplete staged sync and starts a fresh full refresh. A changed JSON file invalidates an in-progress cursor rather than mixing claims from different snapshot versions. A failed sync leaves the last published generation available with stale/partial status.

## dbt manifest and ODS sources

Registering a dbt manifest checks that its project name matches the selected local dbt project. The source starts disabled; enable and refresh it explicitly:

```powershell
python -m dbt_skills.ontology_cli source add-manifest dbt_project .
python -m dbt_skills.ontology_cli source enable dbt_project
python -m dbt_skills.ontology_cli sync dbt_project --full-refresh
```

The manifest contributes dbt resources and **resource-level** `depends_on` edges, not column lineage. The optional ODS adapter asks the configured ODS MCP server for static SQL column-lineage/impact evidence and preserves its coverage, diagnostics, version, and opaque-model details. Register it with the ODS MCP launch command and the exact project/target and focus/change inputs required by that analysis:

```powershell
python -m dbt_skills.ontology_cli source add-ods ods_lineage <ods-mcp-command> . .\target --focus orders --change orders.order_id=changed
python -m dbt_skills.ontology_cli source enable ods_lineage
python -m dbt_skills.ontology_cli sync ods_lineage --full-refresh
```

Replace the example focus/change with the requested analysis. Both source types are snapshot providers and require full refresh; no incremental sync is implied. Missing ODS, opaque SQL, or unavailable output is reported as unavailable/partial coverage, never as zero impact. Neither source is enabled or synchronized automatically.

## Local stdio MCP bridge

Install the pinned runtime dependencies with `python -m pip install -r requirements.txt`, then configure Copilot CLI from the repository root:

```powershell
copilot mcp add dbt-skills-uol --env PYTHONPATH=src -- python -m dbt_skills.uol_mcp --project-dir .
```

The server uses the same default user-profile database as the UOL CLI; `--db <path>` can select another database. The selected project directory is used to validate manifest/ODS identity. Restart or reload the MCP server after changing source registrations. Copilot CLI installation and live discovery have not yet been smoke-tested in this environment.

The bridge exposes three bounded, local-only read tools: `uol_status`, `uol_search`, and `uol_neighbors`. State-changing tools are separate: `uol_sync_source` (incremental providers only), `uol_full_refresh_source`, `uol_set_source_enabled`, `uol_set_cache_reads_enabled`, `uol_purge_source`, and `uol_purge_all_sources`. Configure sources and scopes through the CLI; MCP does not provide source registration or overlay editing. Read results include local sync status and scope with provider provenance. MCP annotations and tool descriptions are advisory, not authorization: configure the host to require user approval for sync, cache changes, and purge, and do not auto-approve state-changing tools.

## Scope and cache controls

`source add-json` and `source scope` accept `--include-namespace`, `--exclude-namespace`, `--include-entity-type`, `--exclude-entity-type`, `--include-property`, `--exclude-property`, `--include-record-id`, and `--exclude-record-id` (each option can be repeated). Exclusions take precedence. Changing scope discards that source's synchronized snapshot; the local overlay is unaffected.

```powershell
python -m dbt_skills.ontology_cli source scope finance --include-namespace finance --exclude-record internal_note
python -m dbt_skills.ontology_cli cache-reads off
python -m dbt_skills.ontology_cli purge --source finance
python -m dbt_skills.ontology_cli cache-reads on
```

Turning cache reads off hides provider-derived claims from local reads but leaves user-authored overlay claims visible. `purge` deletes synchronized provider data but not the overlay. `overlay-clear` explicitly deletes local user-authored claims. `--db` must precede the command, for example `python -m dbt_skills.ontology_cli --db .\.uol-cache\dev.uol.sqlite3 status`.

## Local overlay

User-authored facts require an author and remain separate from provider claims:

```powershell
python -m dbt_skills.ontology_cli overlay-add --subject finance:net_bookings --predicate owner_note --object-json '{"team":"Finance Analytics"}' --author analyst --evidence-json '{"ticket":"FIN-12"}'
python -m dbt_skills.ontology_cli overlay-link --subject-source finance --subject-claim net_bookings --predicate same_as --object-source dbt_project --object-claim fct_bookings_net --evidence-json '{"stable_identifier":"net_bookings"}' --author analyst
```

Links require explicit evidence and existing endpoint claims; replace the example source and claim IDs with ones already in the local store. They preserve both source-qualified endpoint references. Use `overlay-delete <claim_id>` or `overlay-clear` for explicit overlay removal; provider-cache purge never deletes these facts.

## JSON snapshot format

The top-level object contains a `claims` array and may include a `version` string:

```json
{
  "version": "catalog-export-2026-10",
  "claims": [
    {
      "claim_id": "net-bookings-definition",
      "subject_id": "finance:net_bookings",
      "predicate": "definition",
      "object_value": "Bookings net of cancellations",
      "object_kind": "literal",
      "namespace": "finance",
      "entity_type": "measure",
      "native_id": "semantic-layer:net_bookings",
      "evidence": {
        "exported_from": "semantic-layer",
        "url": "https://example.invalid/metrics/net-bookings"
      }
    }
  ]
}
```

Each claim needs a non-empty `claim_id`, `subject_id`, `predicate`, and JSON `object_value`. `object_kind` is `literal` or `entity`; remaining provenance fields are optional. The adapter stamps a snapshot version when supplied and retains the native record identifiers and evidence.

## Adapter contract and current limits

Providers implement the `OntologyProvider` protocol in `src/dbt_skills/ontology.py`: a stable `provider_name`, an incremental-sync capability flag, and an async paginated `fetch_page` that returns claims, a next cursor, completion status, and optional deleted claim IDs. A provider cursor must be stable for the same source snapshot; a full refresh must be fully paginated before the new generation is published. Provider adapters must also enforce the requested source scope and preserve permission/revocation failures rather than silently returning partial data as complete.

The local core uses encrypted SQLCipher WAL storage and indexed token search. Sync is opt-in per source, staged generations are published atomically, and user overlay facts and reviewed links retain separate authorship and evidence. Encryption and permissions reduce offline exposure but do not solve permission revocation for cached data, compromised user accounts, key loss, performance benchmarking, or the absence of remote provider adapters. See the product requirements and issue #30 for platform CI and production-hardening status.

Calls made through one `LocalOntologyStore` instance serialize syncs for the same source. Until cross-process sync leasing is added, do not run overlapping CLI syncs for one source from separate processes.
