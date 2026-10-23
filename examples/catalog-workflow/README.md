# Customer model-design walkthrough

This is a small fictional, metadata-only project. It contains no source records.
The SQL/YAML files are **illustrative review drafts**, not generated or validated by
the catalog tools. No dbt command or warehouse query is executed by this example.

Business request: “Create a customer staging model from XYZ, following our naming
and modelling conventions.” Start the existing MCP server with this project:

```sh
PYTHONPATH=src python -m dbt_skills.modelling_mcp \
  --project-dir examples/catalog-workflow \
  --policy modelling.yml --catalog-config catalogs.json
```

Use it through the [Copilot setup](../../docs/COPILOT_VSCODE.md); add
`--catalog-config`, `catalogs.json` to the server arguments and select this project.
A missing manifest is reported honestly. Create one through your normal dbt setup
if existing-model inference/comparison is needed; do not fabricate lineage.

1. `modelling_context` returns the context ID. Use that ID on all following calls.
2. `catalog_status` identifies the ordered `physical` and `curated` file providers.
3. `catalog_search(provider_id="physical", query="customers")` finds the explicit
   asset ID `urn:demo:xyz:customers`. The same ID in curated.json is a human assertion
   that both records describe the same asset; names alone are never matched.
4. `catalog_resolve(asset_id="urn:demo:xyz:customers", fields=["relation", "columns",
   "primary_key", "foreign_keys"])` obtains columns from physical and a key declaration
   from curated. It reports **partial** because neither declares foreign keys.
   Missing foreign keys mean unknown, not “there are no relationships”. The key is
   explicitly not enforced. Fact provenance identifies each file, revision and time.
5. Ask the human: Is the grain one current row per customer? Can multiple rows share
   customer_id? Is history required? Does XYZ map to the declared dbt source? Are any
   functional dependencies missing? Do not infer 3NF from the file names or key.
6. `modelling_rules` supplies the staging template and modelling target. With
   `modelling_render(rule_id="staging_file", values={})`, missing token questions are
   returned. After the user confirms `system=xyz`, `concept=customer`, render again:
   `models/staging/stg_xyz_customer.sql`.
7. Review the included SQL/YAML draft **only under the explicit assumption** that one
   current row per customer is intended and the source mapping is correct. The model
   is a projection, with proposed unique/not-null checks; it does not deduplicate or
   resolve history. If the human needs history or a different grain, redesign it.
8. The 3NF target remains unproved. Implementation and dbt checks belong to the
   host agent and existing dbt tooling. No passing tests or approval are
   implied by these files. Any warehouse validation must respect the no-raw-data
   boundary; ordinary test failure output may expose values and is not a safe tool.

Try removing primary_key from curated.json and refresh: that fact becomes missing.
Try conflicting column declarations while another field is still unresolved: both
claims are retained and resolution reports conflict. Providers below an already
sufficient result are unqueried, not verified as agreeing.
