import copy
import unittest
from dbt_skills.native_publication import (PublicationError, fingerprint, validate_proposal,
                                           export_handoff, verify_readback)


class FakeAdapter:
    def __init__(self):
        self.document = {'instructions': {'text': 'old', 'examples': ['keep']}, 'warehouse': 'preserve'}
        self.reads = 0
        self.drift = False
        self.origin = 'r1'
        self.conditional = True
        self.permission = True
        self.audience = ['analysts']
        self.failure = False

    def capabilities(self):
        return {'read': True, 'conditional_write': self.conditional}

    def read_origin_revision(self, origin):
        return self.origin

    def read_target(self, target):
        self.reads += 1
        if self.failure:
            raise RuntimeError('secret credential must not escape')
        document = copy.deepcopy(self.document)
        if self.drift and self.reads > 1:
            document['warehouse'] = 'changed elsewhere'
        return {'document': document, 'fingerprint': fingerprint(document),
                'revision_token': 'native-token', 'permissions': {'read': True, 'write': self.permission},
                'audience': self.audience}


def proposal(adapter):
    return {'schema_version': 1, 'target': {'kind': 'genie', 'id': 'space-1'},
            'origin': {'id': 'uol-1', 'revision': 'r1'},
            'base_fingerprint': fingerprint(adapter.document),
            'changes': [{'id': 'text', 'path': ['instructions', 'text'], 'value': 'new'},
                        {'id': 'warehouse', 'path': ['warehouse'], 'value': 'unselected'}],
            'selected_change_ids': ['text'], 'intended_audience': ['analysts']}


class NativePublicationTests(unittest.TestCase):
    def test_review_is_read_only_and_complete(self):
        adapter = FakeAdapter()
        result = validate_proposal(proposal(adapter), adapter)
        self.assertEqual('review_ready', result['status'])
        self.assertFalse(result['native_write_performed'])
        self.assertFalse(result['simulation'])
        self.assertEqual({'instructions': {'text': 'new', 'examples': ['keep']}, 'warehouse': 'preserve'}, result['desired_document'])
        self.assertEqual('old', adapter.document['instructions']['text'])
        self.assertEqual(2, adapter.reads)

    def test_drift_and_origin_conflict(self):
        for drift in ('target', 'origin', 'during'):
            adapter = FakeAdapter()
            p = proposal(adapter)
            if drift == 'target':
                adapter.document['warehouse'] = 'changed'
            elif drift == 'origin':
                adapter.origin = 'r2'
            else:
                adapter.drift = True
            self.assertEqual('conflict', validate_proposal(p, adapter)['status'])

    def test_permissions_audience_failure(self):
        for field, value in [('permission', False), ('audience', ['public']), ('failure', True)]:
            adapter = FakeAdapter()
            p = proposal(adapter)
            setattr(adapter, field, value)
            result = validate_proposal(p, adapter)
            self.assertEqual('blocked', result['status'])
            self.assertNotIn('secret', str(result))

    def test_unsupported_export_and_subset(self):
        adapter = FakeAdapter()
        p = proposal(adapter)
        self.assertEqual('unsupported', validate_proposal(p)['status'])
        adapter.conditional = False
        self.assertEqual('export_only', validate_proposal(p, adapter)['status'])
        self.assertEqual(['text'], [c['id'] for c in export_handoff(p)['proposal']['changes']])

    def test_real_readback(self):
        adapter = FakeAdapter()
        p = proposal(adapter)
        self.assertEqual('readback_mismatch', verify_readback(p, adapter)['status'])
        adapter.document['instructions']['text'] = 'new'
        self.assertEqual('readback_verified', verify_readback(p, adapter)['status'])
        adapter.failure = True
        self.assertEqual('blocked', verify_readback(p, adapter)['status'])

    def test_reject_ambiguous_paths_and_empty_selection(self):
        adapter = FakeAdapter()
        p = proposal(adapter)
        p['selected_change_ids'] = []
        with self.assertRaises(PublicationError):
            export_handoff(p)
        p = proposal(adapter)
        p['changes'][1]['path'] = ['instructions']
        p['selected_change_ids'].append('warehouse')
        with self.assertRaises(PublicationError):
            validate_proposal(p, adapter)
