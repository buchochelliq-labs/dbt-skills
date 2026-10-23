"""Build a local fictional source DB and schema-only agent context, with no dependencies."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3

TABLES = ('categories', 'suppliers', 'products', 'customers', 'employees', 'shippers', 'orders', 'order_details')
STAMP = '2026-10-23T00:00:00Z'  # fixed fixture revision, not a live observation time


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def export_metadata(db, root, catalog="northwind", schema="main"):
    """Reads schema PRAGMAs only. Never SELECTs business rows or exports examples."""
    assets, sources = [], {}
    for table in TABLES:
        columns = db.execute(f'PRAGMA table_info("{table}")').fetchall()
        pk = [c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5]]
        grouped = {}
        for fk in db.execute(f'PRAGMA foreign_key_list("{table}")'):
            grouped.setdefault(fk[0], []).append(fk)
        fks = []
        for group in grouped.values():
            group.sort(key=lambda f: f[1])
            fks.append({'columns': [f[3] for f in group], 'target_asset': 'urn:northwind:' + group[0][2],
                        'target_columns': [f[4] for f in group], 'enforcement': 'unknown', 'rely': False})
        assets.append({'id': 'urn:northwind:' + table, 'native_id': catalog + '.' + schema + '.' + table,
            'facts': {'relation': {'catalog': catalog, 'schema': schema, 'name': table},
                      'columns': [{'name': c[1], 'type': {'INTEGER': 'int64', 'TEXT': 'string'}[c[2]], 'nullable': not bool(c[3] or c[5])} for c in columns],
                      'primary_key': {'columns': pk, 'enforcement': 'unknown', 'rely': False},
                      'foreign_keys': fks}})
        sources['source.northwind_demo.northwind.' + table] = {
            'resource_type': 'source', 'package_name': 'northwind_demo', 'source_name': 'northwind',
            'name': table, 'identifier': table, 'database': catalog, 'schema': schema}
    write_json(root / 'catalog.json', {'schema_version': 1, 'generated_at': STAMP, 'assets': assets})
    (root / 'artifacts').mkdir()
    write_json(root / 'artifacts/manifest.json', {'metadata': {
        'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json',
        'project_name': 'northwind_demo', 'generated_at': STAMP}, 'nodes': {}, 'sources': sources})
    write_json(root / 'catalogs.json', {'schema_version': 1, 'providers': [
        {'id': 'northwind_schema', 'type': 'file', 'path': 'catalog.json', 'scope': 'northwind_demo'}]})
    write_json(root / 'design-request.json', {'intent': 'Design a sales data model with customers, orders, line items and products; explain grain, relationships and evidence gaps.',
        'assets': [{'asset_id': 'urn:northwind:' + name, 'scope': {'layer': 'core'}}
                   for name in ('customers', 'orders', 'order_details', 'products')]})
    (root / 'dbt_project.yml').write_text('name: northwind_demo\nversion: "1.0"\nconfig-version: 2\nprofile: northwind_demo\nmodel-paths: [models]\n', encoding='utf-8')
    (root / 'modelling.yml').write_text('''schema_version: 1
kind: policy
tokens:
  source: Which source-system identifier is agreed?
  concept: Which business concept is represented?
naming:
- id: staging_file
  target: model_file
  template: models/staging/stg_{source}_{concept}.sql
modelling:
- id: core_relational
  scope: {layer: core}
  style: relational
  normal_form: 3NF
''', encoding='utf-8')


def build(root, catalog="northwind", schema="main"):
    import re
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in (catalog, schema)):
        raise ValueError("Use simple catalog and schema identifiers")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)  # refuse overwrite, including partial previous runs
    db = sqlite3.connect(root / 'northwind.sqlite3')
    try:
        db.executescript(Path(__file__).with_name('schema.sql').read_text())
        with db:
            db.executemany('INSERT INTO categories VALUES (?,?)', [(i, f'Category {i:02}') for i in range(1, 7)])
            db.executemany('INSERT INTO suppliers VALUES (?,?,?)', [(i, f'Fictional Supplier {i:02}', 'GB' if i % 2 else 'PT') for i in range(1, 9)])
            db.executemany('INSERT INTO products VALUES (?,?,?,?,?,?)', [(i, f'Fictional Product {i:03}', (i-1)%8+1, (i-1)%6+1, 250+i*75, int(i%13==0)) for i in range(1, 31)])
            db.executemany('INSERT INTO customers VALUES (?,?,?)', [(i, f'Fictional Customer {i:03}', ('GB','PT','FR')[i%3]) for i in range(1, 21)])
            db.executemany('INSERT INTO employees VALUES (?,?,?)', [(i, f'Fictional Employee {i:02}', None if i==1 else 1) for i in range(1, 6)])
            db.executemany('INSERT INTO shippers VALUES (?,?)', [(i, f'Fictional Shipper {i:02}') for i in range(1, 4)])
            for i in range(1, 101):
                day = date(2025,1,1) + timedelta(days=i)
                status = 'cancelled' if i%11==0 else ('pending' if i%7==0 else 'shipped')
                shipped = (day+timedelta(days=2)).isoformat() if status=='shipped' else None
                db.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)', (i,(i-1)%20+1,(i-1)%5+1,(i-1)%3+1,day.isoformat(),shipped,status,300+i%5*100))
                for line in range(1,4):
                    product = (i+line-2)%30+1
                    db.execute('INSERT INTO order_details VALUES (?,?,?,?,?,?)', (i,line,product,1+(i+line)%5,250+product*75,500 if line==3 else 0))
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        export_metadata(db, root, catalog, schema)
    finally:
        db.close()
    return root / 'northwind.sqlite3'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument("--catalog", default="northwind", help="Physical catalog name in exported metadata")
    parser.add_argument("--schema", default="main", help="Physical schema name in exported metadata")
    args = parser.parse_args()
    print(build(args.output_dir, args.catalog, args.schema))
