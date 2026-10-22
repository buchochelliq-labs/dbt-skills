# dbt v2 local column-lineage verification

**Checked:** 2026-10-22  
**Tested distribution:** `dbt-oss` 2.0.8, Windows x86_64, installed into an isolated Python 3.14 virtual environment  
**Result:** the Apache-2.0-only distribution does not generate column lineage in this test.

**Project direction:** use OpenDataSuite's Apache-2.0 static SQL lineage as an optional provider through its read-only stdio MCP, rather than require dbt's full product distribution or duplicate ODS's analyzer. This reproduction remains important because dbt Information Schema may be empty even when ODS can independently analyze compiled SQL. A minimal `dbt-oss` 2.0.8 artifact and ODS MCP wire contract are now smoke-tested; a dbt-skills runtime client and broader source/catalog cases remain unverified.

**ODS smoke test:** ODS v0.0.2 (release commit `f18ed9aad5e5121509fd4b649d336990ff605000`) successfully produced lineage for its dbt v1.10/v2.0.5 fixtures and a committed four-model `dbt-oss` 2.0.8 project. The 2.0.8 fixture passed through both manifest/compiled SQL and Parquet Information Schema paths; a raw stdio MCP test returned project summary, lineage, impact, and opaque-model results. One `select *` model without catalog columns was correctly reported opaque. The earlier, larger reproduction project was rejected with `ODS-E0202` because a seed and a source both declared the same relation. These results establish basic artifact/wire compatibility, not a dbt-skills runtime client or support for arbitrary project shapes. See the reproducible [fixture](../../tests/fixtures/ods-dbt-oss-2.0.8), [MCP contract check](../../tests/check_ods_mcp_interop.py), and [workflow prototype](../WORKFLOW_PROTOTYPES.md#ods-v002-local-smoke-test-evidence).

## Reproduction

1. Install `dbt-oss==2.0.8` in an isolated environment. Its PyPI project description distinguishes the Apache-2.0 subset (`dbt-oss`) from `dbt`, the default distribution with the full feature set.
2. Initialize the built-in `jaffle-shop` sample without interactive profile setup and configure a local DuckDB target.
3. Run:

   ```powershell
   dbt compile --generate-info-schema --static-analysis strict --project-dir <project> --profiles-dir <project> --no-version-check
   dbt show --info column_lineage --format json --project-dir <project> --profiles-dir <project> --no-version-check
   ```

4. The compile completed successfully and processed the sample project, but emitted:

   ```text
   static analysis was requested with `--static-analysis strict` but did not run:
   this distribution of dbt OSS does not include the static analysis engine.
   Install the full dbt distribution to enable it: dbt system upgrade-distribution
   ```

5. The generated `target/info_schema/v1/dbt.column_lineage.parquet` existed, but querying it with `dbt show --info column_lineage --format json` returned:

   ```json
   []
   ```

The empty table/file must not be interpreted as evidence of no column dependencies. The consumer should report column lineage unavailable because the required analysis did not run.

As a separate check, running `dbt parse --generate-info-schema` emitted an `InfoSchemaIncomplete` warning stating that parse does not write column-level lineage, and the same `dbt show --info column_lineage --format json` query again returned `[]`.

## What this establishes

- Local dbt v2 Information Schema is written as versioned Parquet output.
- In `dbt-oss` 2.0.8, strict static analysis is not included; the command's exit success does not mean lineage was generated.
- The PyPI `dbt-oss` 2.0.8 project identifies itself as the subset with only Apache-2.0 open-source code; the separate `dbt` distribution is described as having the full feature set and a dbt product license.
- A capability check must inspect whether lineage rows exist and whether the source distribution/generation details are known.
- This reproduces the Apache-2.0 subset boundary on one OS and one release; it does not test the full product distribution.
- This dbt Information Schema reproduction does not, by itself, prove ODS compatibility. ODS v0.0.2 also passed on its own dbt v1.10/v2.0.5 fixtures and the committed dbt-oss 2.0.8 fixture described below. Treat ODS as a separate evidence provider with its own version, confidence, diagnostics, and compatibility validation.

## Reproducing ODS interoperability

The minimal dbt project and standard-library stdio MCP check are committed under `tests/`. With `dbt-oss` 2.0.8 and ODS 0.0.2 installed, run from the repository root:

```powershell
python tests\check_ods_mcp_interop.py --dbt <path-to-dbt.exe> --ods <path-to-ods.exe>
```

The check compiles the fixture with strict dbt static analysis requested, verifies the expected OSS warning, then negotiates MCP protocol `2025-06-18` and checks summary, exact lineage, downstream impact, and opaque diagnostics using both manifest and Parquet Information Schema inputs. The fixture expects three analyzable models plus one opaque source-wildcard model. This is a wire-contract smoke test, not an implementation of the dbt-skills runtime.

## What remains unresolved

- Full dbt distribution lineage terms are no longer a dependency decision for this product because the user selected ODS as the optional open-source local lineage provider. This is not a legal conclusion about dbt's full distribution; it must not be required or redistributed by dbt-skills without separate review.
- ODS v0.0.2 accepts a minimal `dbt-oss` 2.0.8 manifest and Parquet Information Schema and returns useful lineage over stdio. A dbt-skills client/runtime contract test is still needed; ODS marks its lineage/MCP features preview and warns that 0.0.x interfaces can change.
- Broader source-heavy projects need catalog/schema evidence where `select *` depends on columns not available from compiled SQL or manifest context; validate ODS compatibility and the intended dbt-skills behavior for those cases.
- Cross-platform behavior and other dbt v2 releases.
- The exact license/terms for the full distribution must be reviewed for the version being considered; it must not be treated as part of the Apache-2.0-only source subset.

## Sources

- [dbt Information Schema generation and query documentation](https://docs.getdbt.com/docs/build/dbt-information-schema)
- [dbt Information Schema tables](https://docs.getdbt.com/reference/info-schema)
- [`dbt-oss` 2.0.8 package metadata and description](https://pypi.org/project/dbt-oss/2.0.8/)
- [`dbt` 2.0.8 package metadata](https://pypi.org/project/dbt/2.0.8/)
- [dbt v2 repository and Apache-2.0 source](https://github.com/dbt-labs/dbt)
- [ODS column-lineage design](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0008-column-level-lineage.md)
- [ODS MCP tool contract](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0010-mcp-server.md)
- [ODS lineage limitations and usage](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/lineage.md)
- [Hosted dbt Catalog pricing/feature tiers](https://www.getdbt.com/pricing)
