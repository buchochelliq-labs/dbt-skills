# Databricks notebook source
# MAGIC %md
# MAGIC # Load the fictional Northwind-style fixture into Unity Catalog
# MAGIC Upload the generated northwind.sqlite3 to a UC volume first. This is a
# MAGIC source-data setup notebook, not an agent tool. No rows are displayed.
# MAGIC Targets must not exist. A failure can leave some newly created tables;
# MAGIC rerun in a fresh schema or explicitly clean up only those fixture tables.

# COMMAND ----------
dbutils.widgets.text('catalog', '')
dbutils.widgets.text('schema', 'northwind_demo')
dbutils.widgets.text('sqlite_path', '')  # /Volumes/catalog/schema/volume/northwind.sqlite3

# COMMAND ----------
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from pyspark.sql.types import StructType, StructField, LongType, StringType

catalog = dbutils.widgets.get('catalog')
schema = dbutils.widgets.get('schema')
source_path = dbutils.widgets.get('sqlite_path')
for identifier in (catalog, schema):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', identifier):
        raise ValueError('Set simple catalog and schema identifiers before running')
if not source_path.startswith('/Volumes/') or not Path(source_path).is_file():
    raise ValueError('Upload the generated SQLite fixture to a UC volume and set sqlite_path')

tables = ('categories', 'suppliers', 'products', 'customers', 'employees', 'shippers', 'orders', 'order_details')
prefix = f'`{catalog}`.`{schema}`'
# Existing schema must be visible; do not interpret permission errors as absence.
spark.sql(f'CREATE SCHEMA IF NOT EXISTS {prefix}')
existing = [name for name in tables if spark.catalog.tableExists(f'{catalog}.{schema}.{name}')]
if existing:
    raise ValueError('Refusing to overwrite existing target tables: ' + ', '.join(existing))

# COMMAND ----------
# Copy from the volume before SQLite access, avoiding database locking on volume storage.
with tempfile.TemporaryDirectory(prefix='northwind-import-') as tmp:
    local = Path(tmp) / 'source.sqlite3'
    shutil.copyfile(source_path, local)
    db = sqlite3.connect(local.as_uri() + '?mode=ro', uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',) or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Fixture integrity check failed')
        # Fully read/validate this small fixture before the first table write.
        batches = []
        for table in tables:
            columns = db.execute(f'PRAGMA table_info("{table}")').fetchall()
            if not columns or any(c[2] not in ('INTEGER', 'TEXT') for c in columns):
                raise ValueError('Unexpected fixture schema')
            shape = StructType([StructField(c[1], LongType() if c[2]=='INTEGER' else StringType(),
                                           not bool(c[3] or c[5])) for c in columns])
            rows = db.execute(f'SELECT * FROM "{table}" LIMIT 10001').fetchall()
            if len(rows)>10000:
                raise ValueError('This loader is only for the small synthetic fixture')
            batches.append((table, shape, rows))
        for table, shape, rows in batches:
            spark.createDataFrame(rows, shape).write.format('delta').mode('errorifexists').saveAsTable(f'{prefix}.`{table}`')
            print(f'Created {catalog}.{schema}.{table}: {len(rows)} synthetic rows')
    finally:
        db.close()

# COMMAND ----------
# MAGIC %md
# MAGIC SQLite CHECK/UNIQUE/PK/FK definitions are not automatically transferred by
# MAGIC DataFrame writes. Treat the exported schema as declarations, not proof of
# MAGIC UC enforcement. Dates remain ISO strings; amounts are integer cents and
# MAGIC discounts are integer basis points. No rows should enter agent context.
