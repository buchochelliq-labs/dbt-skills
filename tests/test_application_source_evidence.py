"""Persisted UI snapshots must remain tied to every actual source fact group."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from dbt_skills.application_api import OntologyApplication
from dbt_skills.application_store import ApplicationStore, empty_state
from dbt_skills.project import discover_project
from dbt_skills.workspace_service import CoreBridge
from dbt_skills.workspace_store import WorkspaceError
from tests.cache_test_support import MemoryKeyStore


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        shutil.copytree(Path(__file__).parents[1] / 'examples/data-model-workflow', self.project)
        physical = json.loads((self.project / 'physical.json').read_text())
        self.columns = deepcopy(physical)
        for asset in physical['assets']:
            asset['facts'] = {'relation': asset['facts']['relation']}
        for asset in self.columns['assets']:
            asset['facts'] = {'columns': asset['facts']['columns']}
        self.write('identity.json', physical)
        self.write('columns.json', self.columns)
        self.write('catalogs.json', {'schema_version': 1, 'providers': [
            {'id': 'identity', 'type': 'file', 'path': 'identity.json', 'scope': 'local'},
            {'id': 'column_facts', 'type': 'file', 'path': 'columns.json', 'scope': 'local'},
        ]})
        initial = empty_state()
        initial['domains'] = [dict(id='root', name='Root', parent=None, description='',
                                   owner=None, technicalOwner=None, steward=None,
                                   providerPolicy=None, ttl=None)]
        self.keys = MemoryKeyStore()
        self.store = ApplicationStore(self.root / 'app.db', key_store=self.keys, initial_state=initial)
        self.bridge = None
        self.addCleanup(lambda: self.bridge.close() if self.bridge else None)
        self.reopen()
        self.command('catalog.sync')
        self.kid = self.command('knowledge.create', {'domain': 'root', 'name': 'Customer name',
                    'type': 'Concept', 'definition': 'Reviewed customer naming semantics.'})['result']['id']
        self.command('knowledge.revise', {'id': self.kid, 'patch': {
            'grain': 'one customer', 'scope': 'Service', 'validFrom': '2026-01-01'}})
        self.command('knowledge.approve', {'id': self.kid})
        self.mid = self.command('mapping.save', {'mapping': {'knowledgeId': self.kid,
                    'attribute': 'definition', 'assetId': 'urn:demo:xyz:customers',
                    'fieldPath': 'customer_name', 'type': 'attribute', 'scope': 'Service',
                    'validFrom': '2026-01-01', 'validTo': '', 'evidence': 'Reviewed field identity.'}})['result']['id']
        self.command('mapping.review', {'id': self.mid})

    def write(self, name, document):
        (self.project / name).write_text(json.dumps(document, indent=2) + '\n')

    def reopen(self):
        if self.bridge:
            self.bridge.close()
        self.bridge = CoreBridge(discover_project(self.project, target_path='artifacts'),
                                 policy_path='modelling.yml', catalog_path='catalogs.json')
        self.store = ApplicationStore(self.root / 'app.db', key_store=self.keys)
        self.app = OntologyApplication(self.store, bridge=self.bridge)

    def command(self, name, payload=None):
        return self.app.command(name, payload or {}, expected_revision=self.store.read()['revision'])

    def resolve(self):
        result = self.command('context.resolve', {'request': {'objectId': self.kid, 'scope': 'Service'}})['result']
        self.assertEqual(result['state'], 'sufficient')
        return result

    def test_unavailable_source_hides_cached_facts_and_observations(self):
        self.resolve()
        self.assertTrue(self.store.read()['state']['cache'])
        (self.project / 'columns.json').unlink()
        for state in (self.app.read()['state'], self.command('workspace.export')['result']['state']):
            self.assertEqual(state['assets'], [])
            self.assertEqual(state['cache'], [], 'Cached source facts must not bypass source visibility')
            self.assertEqual(state['observations'], [], 'Source usage must not disclose unavailable evidence')
            self.assertIn(self.kid, [k['id'] for k in state['knowledge']])

    def test_column_revision_change_requires_sync_after_restart(self):
        self.resolve()
        self.reopen()
        self.assertEqual(len(self.app.read()['state']['assets']), 2, 'Unchanged evidence remains readable after restart')
        self.columns['assets'][0]['facts']['columns'] = [c for c in self.columns['assets'][0]['facts']['columns'] if c['name'] != 'customer_name']
        self.write('columns.json', self.columns)
        self.reopen()
        view = self.app.read()['state']
        self.assertEqual(view['assets'], [], 'Changing the columns provider must invalidate the source snapshot')
        self.assertEqual(view['cache'], [])
        self.assertEqual(view['observations'], [])
        synced = self.command('catalog.sync')['state']
        customer = next(a for a in synced['assets'] if a['id'] == 'urn:demo:xyz:customers')
        self.assertNotIn('customer_name', [f['path'] for f in customer['fields']])
        self.assertEqual(next(m for m in synced['mappings'] if m['id'] == self.mid)['status'], 'Needs review')

    def test_fact_group_provenance_and_selected_provider_ttl(self):
        self.command('provider.update', {'id': 'identity', 'patch': {'ttl': 8}})
        self.command('provider.update', {'id': 'column_facts', 'patch': {'ttl': 1}})
        self.resolve()
        self.assertEqual({c['expiresAt'] - c['retrievedAt'] for c in self.store.read()['state']['cache']}, {3600000})
        asset = next(a for a in self.app.read()['state']['assets'] if a['id'] == 'urn:demo:xyz:customers')
        sources = asset.get('sourceEvidence', {})
        self.assertEqual(sources.get('relation', {}).get('provider'), 'identity')
        self.assertEqual(sources.get('columns', {}).get('provider'), 'column_facts')
        self.assertEqual(sources.get('columns', {}).get('revision'), hashlib.sha256((self.project / 'columns.json').read_bytes()).hexdigest())
        self.assertTrue(sources['columns']['retrieved_at'])

    def test_legacy_source_snapshot_requires_explicit_resync(self):
        def legacy(state):
            for asset in state['assets']:
                asset.pop('sourceEvidence', None)
        self.store.transact(self.store.read()['revision'], legacy, 'Legacy snapshot fixture')
        self.reopen()
        self.assertEqual(self.app.read()['state']['assets'], [], 'Missing group evidence cannot establish source freshness')
        self.assertEqual(len(self.command('catalog.sync')['state']['assets']), 2)

    def test_same_revision_new_source_document_never_reuses_old_provenance(self):
        previous = self.resolve()
        (self.project / 'columns.json').rename(self.project / 'columns-moved.json')
        config = json.loads((self.project / 'catalogs.json').read_text())
        config['providers'][1]['path'] = 'columns-moved.json'
        self.write('catalogs.json', config)
        self.reopen()
        current = self.resolve()
        self.assertEqual(current['facts'][0]['evidence']['sourceRevision'], previous['facts'][0]['evidence']['sourceRevision'])
        for fact in current['facts']:
            self.assertEqual(fact['evidence']['sourcePath'], str((self.project / 'columns-moved.json').resolve()) + '#/assets/0/facts/columns')
        self.assertTrue(all('cache' not in step for step in current['trace']))

    def test_absent_field_cannot_be_reapproved_and_restoration_needs_review(self):
        original = deepcopy(self.columns)
        self.columns['assets'][0]['facts']['columns'] = [c for c in self.columns['assets'][0]['facts']['columns'] if c['name'] != 'customer_name']
        self.write('columns.json', self.columns)
        self.command('catalog.sync')
        revision = self.store.read()['revision']
        with self.assertRaises(WorkspaceError):
            self.command('mapping.review', {'id': self.mid})
        self.assertEqual(self.store.read()['revision'], revision)
        self.assertEqual(next(m for m in self.store.read()['state']['mappings'] if m['id'] == self.mid)['status'], 'Needs review')
        self.command('workspace.import.preview', {'envelope': self.command('workspace.export')['result']})
        self.write('columns.json', original)
        self.command('catalog.sync')
        self.assertEqual(next(m for m in self.store.read()['state']['mappings'] if m['id'] == self.mid)['status'], 'Needs review')
        self.command('mapping.review', {'id': self.mid})
        self.resolve()

    def test_current_source_reauthorized_before_mapping_approval(self):
        (self.project / 'columns.json').unlink()
        revision = self.store.read()['revision']
        with self.assertRaises(WorkspaceError):
            self.command('mapping.review', {'id': self.mid})
        self.assertEqual(self.store.read()['revision'], revision)


if __name__ == '__main__':
    unittest.main()
