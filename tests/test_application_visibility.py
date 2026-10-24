"""Durable source snapshots never replace fresh core permission checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from dbt_skills.application_store import ApplicationStore
from dbt_skills.application_api import OntologyApplication
from tests.cache_test_support import MemoryKeyStore
from tests.test_application_store import sample

def provenance(group, revision='1' * 64):
    return dict(provider='provider', asset_id='asset', native_id='native',
                document='catalog.json', locator='/assets/0/facts/' + group,
                revision=revision, scope='local', source_at=None,
                retrieved_at='2026-10-24T00:00:00Z', verified_at=None,
                evidence_type='declaration', derivation=[])

class Bridge:
    status='complete'
    revision='1' * 64
    def preferences(self,_):pass
    def call(self,name,args):
        if name=='modelling_context':return {'context_id':'current'}
        return {'status': self.status, 'selected': {
            'relation': {'value': {'catalog': 'demo', 'schema': 'core', 'name': 'asset'},
                         'provenance': provenance('relation', self.revision)},
            'columns': {'value': [{'name': 'id', 'type': 'string', 'nullable': False}],
                        'provenance': provenance('columns', self.revision)},
        } if self.status == 'complete' else {}}

class VisibilityTest(unittest.TestCase):
    def test_reopened_snapshot_and_export_reauthorize_and_withhold_stale(self):
        fixture=sample()
        fixture['assets'][0].update(sourceRevision='1' * 64, sourceEvidence={
            group: provenance(group) for group in ('relation', 'columns')})
        with tempfile.TemporaryDirectory() as tmp:
            app=OntologyApplication(ApplicationStore(Path(tmp)/'store',key_store=MemoryKeyStore(),initial_state=fixture),bridge=Bridge())
            self.assertTrue(app.read()['state']['assets'])
            for status,revision in [('denied','1' * 64),('error','1' * 64),('complete','2' * 64)]:
                app.bridge.status=status;app.bridge.revision=revision
                self.assertEqual(app.read()['state']['assets'],[])
                exported=app.command('workspace.export',expected_revision=0)['result']['state']
                self.assertEqual(exported['assets'],[])
                self.assertTrue(exported['knowledge'])
            self.assertTrue(app.store.read()['state']['assets'])
