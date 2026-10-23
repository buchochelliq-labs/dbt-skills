# Northwind-style fictional source database

Original deterministic sample data, inspired by a familiar trading-company domain;
not a copy of Microsoft's Northwind database. Python standard library only.

```sh
python examples/northwind-source/build.py --output-dir /tmp/northwind-demo
```

The directory must not already exist. Output includes `northwind.sqlite3`, a
schema-only `catalog.json`, catalog configuration, modelling policy, a design request
and an explicitly synthetic dbt-compatible manifest under `artifacts/`. The manifest
is a context-test fixture, not the output of running dbt and not proven lineage.

| Table | Rows | Purpose |
| --- | ---: | --- |
| categories | 6 | Product categories |
| suppliers | 8 | Product suppliers |
| products | 30 | Products, category/supplier keys, discontinued flag |
| customers | 20 | Fictional customer companies |
| employees | 5 | Staff and optional manager self-reference |
| shippers | 3 | Shipping companies |
| orders | 100 | Customer, employee and shipper relationships; dates/status |
| order_details | 300 | Composite order/line key, product, quantity, sale price and discount |

Amounts are integer cents; discounts are integer basis points. Dates are ISO text.
Line prices are recorded independently of product list prices. The order-line key
allows the same product on multiple lines. Pending/cancelled orders have no shipped
date. Constraints are deliberately straightforward; this is not a claim that every
business invariant is enforced or that a normal form has been proved.

## Agent context

Only the schema export is connected to the modelling server. Its exporter executes
schema PRAGMAs, never reads source rows. The metadata uses `unknown` enforcement
because file declarations do not certify the enforcement state of another system.

```sh
PYTHONPATH=src python -m dbt_skills.modelling_mcp \
  --project-dir /tmp/northwind-demo --target-path artifacts \
  --policy modelling.yml --catalog-config catalogs.json
```

Call `model_plan` with the generated `design-request.json` contents and the current
context ID. Four selected entities have three internally resolved relationships;
other FK targets prompt explicit selection rather than implicit fetching. To inspect
all eight entities, explicitly select all eight URNs `urn:northwind:<table>`.
Grain, cardinality, optionality, history and 3NF reasoning still require review.

## Load the same source into Unity Catalog

1. Build with metadata names matching your intended UC target:

   ```sh
   python examples/northwind-source/build.py --output-dir /tmp/northwind-uc \
     --catalog your_catalog --schema northwind_demo
   ```

2. Upload `northwind.sqlite3` to an existing UC volume using your normal workspace
   upload workflow, for example `/Volumes/your_catalog/tools/fixtures/northwind.sqlite3`.
3. Import `load_unity_catalog.py` as a Databricks Python notebook. Set widgets
   `catalog`, `schema`, and `sqlite_path`. Use UC-enabled compute with volume-read,
   catalog/schema use, schema-create if needed, and table-create permissions.
4. Run the notebook. It copies the uploaded fixture to temporary local storage,
   checks SQLite integrity, validates and loads the eight small tables, and creates
   managed Delta tables with `errorifexists`. It never overwrites existing tables.

The notebook is a source setup utility, not a tool exposed to the agent. It prints
only created table names and synthetic row counts. No secrets are needed in the
repository. A failure during writes may leave some created tables: the eight writes
are not an atomic transaction. Use a fresh schema or explicitly remove only those
fixture tables before retrying. No automatic destructive cleanup is provided.

**Constraint limitation:** DataFrame writes do not transfer SQLite CHECK/UNIQUE/PK/FK
constraints. The file metadata remains declared evidence, not verified UC constraints.
A live Unity Catalog adapter may therefore report fewer key facts; an explicitly
configured file provider can supply the declarations using matching reviewed asset
identities. Do not assume IDs align automatically or bypass a denied catalog read.

The generator, integrity/FK checks, metadata privacy and planner integration are
locally tested. The notebook is syntax-checked but has not been run in Databricks;
UC permissions, compute/filesystem compatibility and live loading remain acceptance
work. Dates intentionally remain strings and money remains cents on both platforms.

References: [UC volume paths](https://docs.databricks.com/aws/en/volumes/),
[saveAsTable modes](https://learn.microsoft.com/en-us/azure/databricks/pyspark/reference/classes/dataframewriter/saveastable).
