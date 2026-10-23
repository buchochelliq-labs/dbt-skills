# Customer/order metadata-only design session

Positive two-entity companion to `examples/catalog-workflow`. No source rows or SQL
implementation files. Physical metadata supplies columns; curated metadata declares
keys and the order-to-customer relationship. The synthetic manifest binds both sources
and describes an existing legacy customer filename for the exception scenario.
It is not a dbt parse result or proof of lineage in a real project.

```sh
PYTHONPATH=src python -m dbt_skills.modelling_mcp \
  --project-dir examples/data-model-workflow --target-path artifacts \
  --policy modelling.yml --catalog-config catalogs.json
```

Ask Copilot to design the customer/order data model using `design-request.json`,
clarify grain and relationship meaning, and explain the applicable 3NF target.
Expected: two entity candidates and a declared FK whose endpoints match metadata;
cardinality, uniqueness and normal form remain unverified. Names resolve using
`system=xyz` and `concept=customer` or `order`. Compare the existing customer model:
`customer_legacy.sql` differs from the template. Ask for a one-model compatibility
exception; the tool prepares a pending proposal and must not change files/standards.

Select only orders: customer evidence is not silently fetched. In a disposable copy,
change the FK target column to a nonexistent name and refresh: old context IDs fail
and new planning asks for reconciliation instead of suggesting the join is safe.

`tests/test_data_model_workflow.py` exercises this exact fixture through real MCP
stdio, including file non-mutation. Live Copilot UI/reasoning remains unverified.
For a populated source DB and UC loader, see [Northwind-style source](../northwind-source/README.md).
