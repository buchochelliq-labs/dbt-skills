import copy
import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.catalog import load_catalog
from dbt_skills.project import discover_project
from dbt_skills.project_artifacts import inspect_artifacts


class MetadataFixture(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        example = Path(__file__).resolve().parents[1] / 'examples' / 'catalog-workflow'
        for name in ('dbt_project.yml', 'modelling.yml', 'catalogs.json', 'physical.json', 'curated.json'):
            shutil.copyfile(example / name, self.root / name)
        policy = self.root / 'modelling.yml'
        import yaml
        doc = yaml.safe_load(policy.read_text())
        doc['naming'] = [r for r in doc['naming'] if r['target'] != 'properties_file']
        doc['naming'].append({'id': 'properties', 'target': 'properties_file', 'template': 'models/staging/{concept}.yml'})
        policy.write_text(yaml.safe_dump(doc))
        (self.root / 'target').mkdir()
        self.manifest = self.root / 'target/manifest.json'
        self.manifest.write_text(json.dumps({'metadata': {'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json', 'project_name': 'catalog_workflow'}, 'nodes': {}, 'sources': {
            'source.catalog_workflow.xyz.customers': {'resource_type': 'source', 'package_name': 'catalog_workflow', 'name': 'customers', 'source_name': 'xyz', 'identifier': 'customers', 'database': 'demo', 'schema': 'xyz'}}}))
        self.project = discover_project(self.root)
        self.catalog = load_catalog(self.root / 'catalogs.json')
