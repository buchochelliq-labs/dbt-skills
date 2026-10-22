# dbt v2 local column-lineage verification

**Checked:** 2026-10-22  
**Tested distribution:** `dbt-oss` 2.0.8, Windows x86_64, installed into an isolated Python 3.14 virtual environment  
**Result:** the Apache-2.0-only distribution does not generate column lineage in this test.

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

## What remains unresolved

- Whether the full dbt distribution's locally generated column lineage is available to all self-hosted users, requires particular product terms, or has any usage/plan restriction. The documented local generation flow and the hosted dbt Catalog Enterprise entitlement are separate questions; no conclusion about one should be inferred from the other.
- Whether redistribution/invocation of the full distribution is suitable for this project's open-source product. The dbt Product Licensing Agreement allows use under its own terms and contains restrictions and requirements relevant to redistribution; obtain legal review before relying on it as a dependency.
- Cross-platform behavior and other dbt v2 releases.
- The exact license/terms for the full distribution must be reviewed for the version being considered; it must not be treated as part of the Apache-2.0-only source subset.

## Sources

- [dbt Information Schema generation and query documentation](https://docs.getdbt.com/docs/build/dbt-information-schema)
- [dbt Information Schema tables](https://docs.getdbt.com/reference/info-schema)
- [`dbt-oss` 2.0.8 package metadata and description](https://pypi.org/project/dbt-oss/2.0.8/)
- [`dbt` 2.0.8 package metadata](https://pypi.org/project/dbt/2.0.8/)
- [dbt v2 repository and Apache-2.0 source](https://github.com/dbt-labs/dbt)
- [dbt Product Licensing Agreement](https://www.getdbt.com/dbt-product-license-agreement)
- [Hosted dbt Catalog pricing/feature tiers](https://www.getdbt.com/pricing)
