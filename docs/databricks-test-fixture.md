# Databricks integration test fixture

The manually triggered `Create Databricks test fixture` workflow creates and
verifies two synthetic Unity Catalog tables:

- `dbt_skills_test.integration.customers`, with comments and a declared primary
  key.
- `dbt_skills_test.integration.orders`, with comments, a declared primary key,
  and a declared foreign key to `customers`.

The workflow uses the GitHub Actions Environment named `databricks-free` and
reads `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, and
`SQL_WAREHOUSE_ID` from that environment. The OAuth secret must allow the
`sql` API scope. The service principal needs `USE CATALOG` and `CREATE SCHEMA`
on `dbt_skills_test`, then `USE SCHEMA` and `CREATE TABLE` in
`dbt_skills_test.integration`. It also needs `CAN USE` on the selected SQL
warehouse.

The workflow is `workflow_dispatch` only. It creates the schema and tables if
they do not exist, checks that the expected key constraints are present, does
not insert data, and never replaces existing tables. If a table already exists
without the expected constraint, the check fails without modifying that table.
The fixture contains no real or sensitive data.

`HTTP_PATH` is not needed by this workflow because it calls the Databricks SQL
Statement Execution REST API using the warehouse ID. It may be retained for a
future connector-based test.
