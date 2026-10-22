# dbt v2 local column-lineage verification

**Checked:** 2026-10-22  
**Tested distribution:** `dbt-oss` 2.0.8, Windows x86_64, installed into an isolated Python 3.14 virtual environment  
**Result:** the Apache-2.0-only distribution does not generate column lineage in this test.

**Project direction:** use OpenDataSuite's Apache-2.0 static SQL lineage as an optional provider through its read-only stdio MCP, rather than require dbt's full product distribution or duplicate ODS's analyzer. This reproduction remains important because dbt Information Schema may be empty even when ODS can independently analyze compiled SQL. ODS interoperability still needs verification against exact artifact versions and its preview MCP contract.

**ODS smoke test:** ODS v0.0.2 (release commit `f18ed9aad5e5121509fd4b649d336990ff605000`) successfully produced column lineage for its dbt v1.10 and v2.0.5 fixtures, and its stdio MCP returned lineage plus an explicit opaque-model explanation. The pre-existing dbt-oss 2.0.8 reproduction project was rejected with `ODS-E0202` because a seed and a source both declare the same relation; therefore this is not yet a valid dbt-oss 2.0.8 compatibility test. Detailed evidence is in [the workflow prototype](../WORKFLOW_PROTOTYPES.md#ods-v002-local-smoke-test-evidence).

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
- This dbt Information Schema reproduction does not prove ODS compatibility. ODS v0.0.2 passed on its own dbt v1.10 and v2.0.5 fixtures, but a valid dbt-oss 2.0.8 fixture still needs to be tested. Treat ODS as a separate evidence provider with its own version, confidence, diagnostics, and compatibility validation.

## What remains unresolved

- Full dbt distribution lineage terms are no longer a dependency decision for this product because the user selected ODS as the optional open-source local lineage provider. This is not a legal conclusion about dbt's full distribution; it must not be required or redistributed by dbt-skills without separate review.
- ODS MCP's exact release/schema compatibility with supported dbt versions and a dbt-skills client still requires an interoperability test. ODS marks its lineage/MCP features preview and warns that 0.0.x interfaces can change.
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
