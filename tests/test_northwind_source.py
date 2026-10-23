import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dbt_skills.catalog import load_catalog
from dbt_skills.model_planning import plan_model
from dbt_skills.modelling_policy import load_document
from dbt_skills.project import discover_project

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('northwind_builder', ROOT / 'examples/northwind-source/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class NorthwindSourceTests(unittest.TestCase):
    def test_source_integrity_metadata_privacy_and_design_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fixture'
            path = builder.build(root, 'demo_catalog', 'northwind_demo')
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(db.execute('SELECT count(*) FROM orders').fetchone()[0], 100)
                self.assertEqual(db.execute('SELECT count(*) FROM order_details').fetchone()[0], 300)
                db.execute('PRAGMA foreign_keys=ON')
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute('UPDATE order_details SET product_id=99999 WHERE order_id=1')
                db.rollback()
                # Export must be schema-only: trace makes an accidental row SELECT fail.
                statements = []
                db.set_trace_callback(statements.append)
                out = Path(tmp) / 'metadata'
                out.mkdir()
                builder.export_metadata(db, out, 'demo_catalog', 'northwind_demo')
                self.assertTrue(statements)
                self.assertTrue(all(s.startswith('PRAGMA ') for s in statements), statements)
            raw = (root / 'catalog.json').read_text()
            self.assertNotIn('Fictional Customer', raw)
            catalog = json.loads(raw)
            self.assertEqual(len(catalog['assets']), 8)
            line = next(a for a in catalog['assets'] if a['id']=='urn:northwind:order_details')
            self.assertEqual(line['facts']['primary_key']['columns'], ['order_id', 'line_number'])
            self.assertEqual(line['facts']['relation']['catalog'], 'demo_catalog')
            result = plan_model(discover_project(root, target_path='artifacts'),
                load_document(root / 'modelling.yml'), load_catalog(root / 'catalogs.json'),
                json.loads((root / 'design-request.json').read_text()))
            self.assertEqual(len(result['entities']), 4)
            valid = [r for r in result['relationships'] if r['status']=='declared_endpoints_valid']
            self.assertEqual(len(valid), 3)
            self.assertTrue(all(r['cardinality']=='unverified' for r in valid))
            self.assertNotIn('Fictional Customer', json.dumps(result))
            with self.assertRaises(FileExistsError):
                builder.build(root)


if __name__ == '__main__':
    unittest.main()
