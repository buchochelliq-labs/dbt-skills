# Local artifact inspection

This is the first inspection slice of issue #12. It provides local evidence when no MCP server is available, without contacting a provider, running dbt, or opening warehouse credentials.

```sh
PYTHONPATH=src python -m dbt_skills.cli inspect --project-dir /path/to/project --artifacts
PYTHONPATH=src python -m dbt_skills.cli inspect --project-dir /path/to/project --artifacts --target-path build/dbt --stale-after-hours 48
```

PowerShell users can set `$env:PYTHONPATH = "src"` before running the same Python commands. Artifact paths are resolved relative to the discovered project root, even when inspection starts in a nested models directory. A literal project `target-path` is honored; the CLI override takes precedence. Jinja is never evaluated. Environment variables and options used by an earlier dbt invocation cannot be reliably reconstructed; pass the actual directory explicitly. Absolute directories are allowed because inspection is read-only and users may keep artifacts outside the project.

## Report contract

`init` and `ask` also accept `--target-path` for projects whose artifact directory needs an explicit resolved value. This override is per invocation and is not persisted by `init`. Existing ontology `--manifest` and ODS target-directory overrides remain authoritative; UOL manifest evidence records the actual resolved file path.

The UOL MCP server accepts `--project-dir PROJECT --target-path PATH` as well. Artifact inspection rejects non-regular files before opening them; concurrent hostile filesystem replacement is outside this read-only inspector's current contract.

The ordinary project JSON is unchanged. With `--artifacts`, an `artifacts` object is added:

| Entry | Supported inspection |
| --- | --- |
| `manifest` | Manifest schema v12, the schema documented for dbt v1.8–1.11 and v2.0. Reads the nodes, sources, exposures, metrics, semantic_models, and saved_queries collections. Emits selected resource metadata and explicit `depends_on.nodes` edges. |
| `catalog` | Catalog schema v1 metadata and resource count. Catalogs without project identity are labeled `identity: unverified`. No automatic association with the manifest or column-lineage interpretation. |
| `information_schema` | Detects the selected target's `info_schema` path. Presence is reported as `unsupported`; no Parquet decoding or lineage inference is performed. |
| `column_lineage` | Always `unavailable` in this inspector. Use the separate optional ODS integration for explicit column evidence. |

This validates the consumed artifact subset, not the entire upstream JSON Schema. Other schema versions are `unsupported`; they are not silently parsed as v12/v1. Synthetic fixtures cover v12 metadata for both dbt 1.11.0 and dbt-oss 2.0.8, not live compilation or every distribution/version. The reported `dbt_version` is the artifact producer, not an installed executable's version. Project `version` remains the project's own version.

JSON artifact statuses distinguish `available`, `missing`, `inaccessible`, `malformed`, `unsupported`, `mismatched`, `unverified`, and `too_large`. A manifest requires matching `metadata.project_name` before resource/edge output. Matching names alone do not prove target, environment, or invocation identity. Each JSON report includes the resolved source path and observation time; readable files also include SHA-256. Only selected metadata is returned: custom environment fields, raw/compiled SQL, and arbitrary parser error excerpts are omitted.

`freshness` is independent of readability: `fresh`, `stale`, `unknown`, or `future`. Age uses the artifact's timezone-aware `metadata.generated_at`, never file modification time. Missing, invalid, or timezone-free timestamps remain unknown. The default stale threshold is 24 hours and accepts only finite positive values. A recent timestamp does not prove the artifact matches current model files; stale artifacts remain available but explicitly labeled. No clock-skew allowance is assumed for future timestamps.

Edges point from the dependent resource to its dependency and carry `kind: resource_dependency`. An unresolved dependency is retained with `target_present: false`, never silently dropped. These edges are not column lineage. Imported names are untrusted data, not instructions.

Reads are capped at 64 MiB per JSON artifact, 10,000 resources, and 100,000 distinct resource edges. Exceeding a bound returns `too_large` without a partial graph. The inspector does not claim a complete graph when records or dependency lists are malformed. Limits are deliberately conservative for interactive output and are separate from UOL sync limits.

The CLI exits successfully when it produces a diagnostic report, including missing or unusable artifact statuses. Invalid project configuration or inspection arguments fail the command. Consumers must inspect each artifact's status and freshness rather than treating exit code zero as proof of usable context. Inspection never changes the input files or sends their contents to the model runtime.

## Remaining issue #12 scope

- Direct versioned Information Schema parsing and supported column evidence.
- Broader real generated artifact fixtures and schema compatibility coverage.
- Reconcile the inspection subset with UOL projection validation without changing existing sync contracts implicitly.
- Stronger target/invocation matching and source-change detection beyond age and project name.

## References

- [dbt artifact metadata and output locations](https://docs.getdbt.com/reference/artifacts/dbt-artifacts)
- [Manifest versions and resource graph](https://docs.getdbt.com/reference/artifacts/manifest-json)
- [Target path overrides](https://docs.getdbt.com/reference/global-configs/json-artifacts)
- [Existing ODS interoperability evidence](research/dbt-v2-column-lineage.md)
