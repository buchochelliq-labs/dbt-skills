import tempfile
import unittest
from pathlib import Path
from dbt_skills.application_store import ApplicationStore, ApplicationError, ApplicationConflict, empty_state
from tests.cache_test_support import MemoryKeyStore


def sample():
    s = empty_state()
    s['domains'] = [dict(id='domain', name='Domain', parent=None, description='Private domain', owner=None, technicalOwner=None, ttl=None)]
    s['knowledge'] = [dict(id='concept', name='Concept', type='Concept', domain='domain', memberships=[], summary='Summary', definition='PRIVATE_APPLICATION_SENTINEL', scope='Enterprise', grain='Person', status='Approved', origin='Curated', version=2, owner='Steward', source='Authored', sourcePath='concept.yaml', effective='today', validFrom='2026-01-01', synonyms=['Alias'], related=[], originId='uol:concept', history=[dict(revision=1, definition='Original definition', status='Draft', origin='Curated', changedAt=123)])]
    s['providers'] = [dict(id='provider', name='Provider', kind='uc', enabled=True, ttl=24, health='healthy', scope=['*'], workspace='workspace', metastore='metastore', capabilities={'discovery': 'permitted'})]
    s['assets'] = [dict(id='asset', nativeId='native', providerId='provider', name='Asset', type='table', parent=None, owner='Owner', description='Metadata only', tags={'category': 'test'}, fields=[dict(path='id', type='STRING', nullable=False, comment='Identity', classification='Internal', key='none')], domainIds=['domain'], knowledgeIds=['concept'], observedAt=100, sourceRevision='r1')]
    s['mappings'] = [dict(id='map', knowledgeId='concept', attribute='identity', assetId='asset', fieldPath='id', type='attribute', scope='Enterprise', validFrom='2026-01-01', evidence='Authored', status='Draft')]
    s['targets'] = [dict(id='asset', name='Asset', kind='table', providerId='provider', revision=1, content={'yaml': {'measures': [{'expr': 'COUNT(*)'}]}, 'unrelated_setting': 'preserved'}, capability='permitted', permission='permitted', audience='Internal', atomic=False, failNext=False, mismatchNext=False, origins={})]
    s['proposals'] = [dict(id='proposal', originId='uol:concept', originRevision=2, targetId='asset', field='description', before={'nested': ['old']}, after={'nested': ['new']}, expectedRevision=1, reason='Update', audience='Internal', state='Reviewed', dependencies=[], evidence='Declared', reviewedAt=100)]
    s['deliveries'] = [dict(id='delivery', proposalId='proposal', at=100, state='Verified', acknowledged=True, readback='matches', indexing='unknown', answerUse='unknown', message='Historical attempt')]
    s['pages'] = [dict(id='page', name='Page', domain='domain', owner='Owner', synonyms=[], summary='Summary', body='Body', relatedAssets=['asset'], sources=['source.md'], state='Draft')]
    s['relationships'] = [dict(id='edge', source='page', target='concept', type='dependency', label='documents', scope='Enterprise', cardinality='one', provenance='Authored', approval='Approved')]
    return s


class ApplicationStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'application.db'
        self.keys = MemoryKeyStore()
        self.store = ApplicationStore(self.path, key_store=self.keys, initial_state=sample())

    def test_nested_restart_revision_history_and_encryption(self):
        self.store.transact(0, lambda state: state['knowledge'][0].update(summary='Edited'), 'edit')
        reopened = ApplicationStore(self.path, key_store=self.keys)
        self.assertEqual(reopened.read(), self.store.read())
        self.assertEqual(reopened.read()['state']['targets'], sample()['targets'])
        self.assertEqual(reopened.read()['state']['knowledge'][0]['history'], sample()['knowledge'][0]['history'])
        self.assertEqual(len(reopened.history()), 2)
        self.assertNotIn(b'PRIVATE_APPLICATION_SENTINEL', self.path.read_bytes())

    def test_cas_and_invalid_mutation_rollback(self):
        second = ApplicationStore(self.path, key_store=self.keys)
        self.store.transact(0, lambda s: s.update(sequence=2))
        with self.assertRaises(ApplicationConflict):
            second.transact(0, lambda s: s.update(sequence=99))
        with self.assertRaises(ApplicationError):
            second.transact(1, lambda s: s['domains'][0].update(parent='domain'))
        self.assertEqual(second.read()['revision'], 1)
        self.assertEqual(second.read()['state']['sequence'], 2)
        self.assertEqual(len(second.history()), 2)

    def test_schema_duplicate_reference_and_cycles(self):
        mutations = [lambda s: s.update(unexpected=True), lambda s: s['knowledge'].append(s['knowledge'][0]), lambda s: s['mappings'][0].update(assetId='missing'), lambda s: s['relationships'].append({**s['relationships'][0], 'id': 'reverse', 'source': 'concept', 'target': 'page'}), lambda s: s.update(clock=float('nan'))]
        for mutation in mutations:
            with self.assertRaises(ApplicationError): self.store.transact(0, mutation)
        self.assertEqual(self.store.read()['revision'], 0)

    def test_preview_security_resets_and_staleness(self):
        preview = self.store.preview_import(self.store.export())
        self.assertEqual(self.store.read()['revision'], 0)
        state = preview['state']
        self.assertEqual(state['mappings'], sample()['mappings'])
        self.assertEqual(state['knowledge'], sample()['knowledge'])
        self.assertFalse(state['providers'][0]['enabled'])
        self.assertEqual(state['targets'][0]['permission'], 'unknown')
        self.assertEqual(state['targets'][0]['content'], {})
        self.assertEqual(state['assets'][0]['fields'], [])
        self.assertFalse(state['deliveries'][0]['acknowledged'])
        self.assertTrue(preview['diff']['security_resets'])
        self.store.transact(0, lambda s: s.update(sequence=3))
        with self.assertRaises(ApplicationConflict): self.store.apply_import(preview['preview_id'])
        next_preview = self.store.preview_import(self.store.export())
        # Caller cannot mutate the reviewed stored candidate via response aliasing.
        next_preview['state']['sequence'] = 999
        self.assertEqual(self.store.apply_import(next_preview['preview_id'])['state']['sequence'], 3)

    def test_simulation_label_persists_and_mixing_rejected(self):
        exported = self.store.export()
        exported['simulation'] = True
        with self.assertRaises(ApplicationError): self.store.preview_import(exported)
        self.assertFalse(ApplicationStore(self.path, key_store=self.keys, simulation=True).export()['simulation'])

    def test_duplicate_additional_memberships_rejected_atomically(self):
        child = {**sample()['domains'][0], 'id': 'child', 'parent': 'domain'}
        self.store.transact(0, lambda state: state['domains'].append(child))
        with self.assertRaises(ApplicationError):
            self.store.transact(1, lambda state: state['knowledge'][0].update(memberships=['child', 'child']))
        self.assertEqual(self.store.read()['revision'], 1)
        self.assertEqual(self.store.read()['state']['knowledge'][0]['memberships'], [])
        exported = self.store.export()
        exported['state']['knowledge'][0]['memberships'] = ['child', 'child']
        with self.assertRaises(ApplicationError):
            self.store.preview_import(exported)

    def test_primary_domain_cannot_be_an_additional_membership(self):
        with self.assertRaises(ApplicationError):
            self.store.transact(0, lambda state: state['knowledge'][0].update(memberships=['domain']))
        self.assertEqual(self.store.read()['revision'], 0)
        exported = self.store.export()
        exported['state']['knowledge'][0]['memberships'] = ['domain']
        with self.assertRaises(ApplicationError):
            self.store.preview_import(exported)

    def test_valid_additional_membership_survives_import(self):
        def edit(state):
            state['domains'].append({**state['domains'][0], 'id': 'child', 'parent': 'domain'})
            state['knowledge'][0]['memberships'] = ['child']
        self.store.transact(0, edit)
        preview = self.store.preview_import(self.store.export())
        applied = self.store.apply_import(preview['preview_id'])
        self.assertEqual(applied['state']['knowledge'][0]['domain'], 'domain')
        self.assertEqual(applied['state']['knowledge'][0]['memberships'], ['child'])

    def test_import_rejects_approved_mapping_to_undeclared_known_field(self):
        exported = self.store.export()
        exported['state']['mappings'][0].update(status='Approved', fieldPath='missing')
        with self.assertRaises(ApplicationError):
            self.store.preview_import(exported)
        self.assertEqual(self.store.read()['revision'], 0)
        self.assertEqual(self.store.read()['state']['mappings'][0]['fieldPath'], 'id')

    def test_import_preserves_approved_exact_mapping_but_resets_source_authority(self):
        exported = self.store.export()
        exported['state']['mappings'][0]['status'] = 'Approved'
        preview = self.store.preview_import(exported)
        applied = self.store.apply_import(preview['preview_id'])
        mapping = applied['state']['mappings'][0]
        self.assertEqual((mapping['status'], mapping['fieldPath']), ('Approved', 'id'))
        self.assertEqual(applied['state']['assets'][0]['fields'], [])
        self.assertTrue(applied['state']['assets'][0]['hidden'])
        self.assertFalse(applied['state']['providers'][0]['enabled'])
        self.assertEqual(applied['state']['targets'][0]['permission'], 'unknown')
        self.assertFalse(applied['state']['deliveries'][0]['acknowledged'])
        # An export after authority reset has a redacted inventory, not proof
        # that the historical mapped field never existed.
        repeated = self.store.preview_import(self.store.export())
        self.assertEqual(repeated['state']['mappings'][0]['fieldPath'], 'id')

    def test_import_preserves_mapping_awaiting_review_after_schema_change(self):
        for status in ('Draft', 'Needs review'):
            with self.subTest(status=status):
                exported = self.store.export()
                exported['state']['assets'][0]['fields'] = sample()['assets'][0]['fields']
                exported['state']['mappings'][0].update(status=status, fieldPath='previous_field')
                preview = self.store.preview_import(exported)
                applied = self.store.apply_import(preview['preview_id'])
                mapping = applied['state']['mappings'][0]
                self.assertEqual((mapping['status'], mapping['fieldPath']), (status, 'previous_field'))
                self.assertEqual(applied['state']['assets'][0]['fields'], [])

    def test_import_allows_approved_mapping_with_unknown_inventory(self):
        exported = self.store.export()
        exported['state']['mappings'][0].update(status='Approved', fieldPath='historical_field')
        exported['state']['assets'][0]['fields'] = []
        preview = self.store.preview_import(exported)
        self.assertEqual(preview['state']['mappings'][0]['fieldPath'], 'historical_field')
        self.assertTrue(preview['state']['assets'][0]['hidden'])
