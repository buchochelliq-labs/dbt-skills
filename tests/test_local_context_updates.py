import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dbt_skills.business_context import load_business_context, BusinessContextError
from dbt_skills.business_context_proposals import prepare_business_update
from dbt_skills.local_context_updates import prepare_update, accept_update, ContextUpdateError, _digest


def concept(identifier='customer'):
    return {'id': identifier, 'name': identifier.title(), 'definition': 'A scoped business concept.',
            'scope': {'domain': 'sales'}, 'status': 'proposed', 'rationale': 'Confirmed in conversation.',
            'recorded_by': 'developer', 'recorded_at': '2026-10-25T12:00:00Z'}


def document():
    return {'schema_version': 1, 'kind': 'business_context', 'concepts': [concept(), concept('order')], 'relationships': []}


class LocalUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'business.json'
        self.path.write_text(json.dumps(document()))
        self.loaded = load_business_context(self.path)
        self.changed = copy.deepcopy(self.loaded['document'])
        self.changed['concepts'][0]['definition'] = 'Clarified customer meaning.'
        self.proposal = prepare_update(self.loaded, self.changed)

    def accept(self, proposal=None, target='business.json', digest=None):
        proposal = proposal or self.proposal
        return accept_update(self.root, target, proposal, accepted_digest=digest or proposal['proposal_sha256'])

    def test_prepare_does_not_write_and_preserves_other_records(self):
        before = self.path.read_bytes()
        result = prepare_business_update(self.loaded, {'section': 'concepts', 'record': self.changed['concepts'][0], 'replace_record_id': 'customer'})
        self.assertEqual(result['local_update'], self.proposal)
        self.assertEqual(result['proposed_document']['concepts'][1], concept('order'))
        self.assertEqual(result['business_context_patch'][0]['op'], 'test')
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_accept_replay_and_mode(self):
        self.path.chmod(0o640)
        result = self.accept()
        self.assertEqual(result['status'], 'saved')
        self.assertTrue(result['refresh_required'])
        self.assertEqual(result['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(json.loads(self.path.read_text()), self.changed)
        with self.assertRaises(ContextUpdateError):
            self.accept()
        self.assertEqual([p.name for p in self.root.iterdir()], ['business.json'])

    def test_wrong_digest_and_tampered_document(self):
        with self.assertRaises(ContextUpdateError):
            self.accept(digest='0' * 64)
        self.proposal['proposed_document']['concepts'][0]['definition'] = 'Tampered'
        with self.assertRaises(ContextUpdateError):
            self.accept()
        self.assertEqual(load_business_context(self.path), self.loaded)

    def test_rehashed_false_diff_rejected(self):
        self.proposal['review_diff'] = 'Nothing changed'
        self.proposal['proposal_sha256'] = _digest({k: v for k, v in self.proposal.items() if k != 'proposal_sha256'})
        with self.assertRaises(ContextUpdateError):
            self.accept()

    def test_stale_raw_bytes_rejected(self):
        self.path.write_text(json.dumps(self.loaded['document'], indent=4))
        with self.assertRaises(ContextUpdateError):
            self.accept()
        with self.assertRaises(BusinessContextError):
            prepare_business_update(self.loaded, {'section': 'concepts', 'record': concept('new')})

    def test_target_redirection_parent_and_symlink_rejected(self):
        other = self.root / 'other.json'
        other.write_bytes(self.path.read_bytes())
        for target in ['other.json', '../escape.json', str(self.root.parent / 'escape.json')]:
            with self.subTest(target=target), self.assertRaises(ContextUpdateError):
                self.accept(target=target)
        other.unlink()
        other.symlink_to(self.path)
        with self.assertRaises(ContextUpdateError):
            self.accept(target='other.json')
        self.path.unlink()
        self.path.symlink_to(other)
        with self.assertRaises(ContextUpdateError):
            self.accept()

    def test_create_only_and_replay(self):
        proposal = prepare_update(None, document())
        result = self.accept(proposal, target='new.json')
        self.assertEqual(result['status'], 'saved')
        self.assertEqual((self.root / 'new.json').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ContextUpdateError):
            self.accept(proposal, target='new.json')
        with self.assertRaises(ContextUpdateError):
            self.accept(proposal)

    def test_creation_race_never_overwrites(self):
        proposal = prepare_update(None, document())
        original_link = os.link
        def race(source, target):
            Path(target).write_text('other writer')
            return original_link(source, target)
        with patch('dbt_skills.local_context_updates.os.link', side_effect=race), self.assertRaises(ContextUpdateError):
            self.accept(proposal, target='new.json')
        self.assertEqual((self.root / 'new.json').read_text(), 'other writer')
        self.assertFalse((self.root / 'new.json.lock').exists())

    def test_last_stale_check_and_cooperating_lock(self):
        lock = self.path.with_name(self.path.name + '.lock')
        lock.write_text('another operator')
        with self.assertRaises(ContextUpdateError):
            self.accept()
        self.assertEqual(lock.read_text(), 'another operator')
        lock.unlink()
        with patch('dbt_skills.local_context_updates._raw', return_value=b'changed'), self.assertRaises(ContextUpdateError):
            self.accept()
        self.assertEqual(load_business_context(self.path), self.loaded)

    def test_unchanged_invalid_kind_and_missing_endpoint(self):
        for new in [self.loaded['document'], {**document(), 'kind': 'policy'}]:
            with self.assertRaises(ContextUpdateError):
                prepare_update(self.loaded, new)
        relationship = {k: v for k, v in concept('placed_by').items() if k != 'name'}
        relationship.update({'from': 'order', 'to': 'missing', 'predicate': 'placed_by'})
        with self.assertRaises(BusinessContextError):
            prepare_business_update(self.loaded, {'section': 'relationships', 'record': relationship})
        relationship['to'] = 'customer'
        result = prepare_business_update(self.loaded, {'section': 'relationships', 'record': relationship})
        self.assertEqual(result['business_context_patch'][0]['op'], 'add')

    def test_no_upsert_or_renamed_replacement(self):
        for request in [
            {'section': 'concepts', 'record': concept()},
            {'section': 'concepts', 'record': concept('new'), 'replace_record_id': 'customer'},
            {'section': 'concepts', 'record': concept('new'), 'replace_record_id': 'new'},
        ]:
            with self.assertRaises(BusinessContextError):
                prepare_business_update(self.loaded, request)

    def test_directory_sync_failure_reports_saved(self):
        original = os.fsync
        count = 0
        def sync(fd):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('directory not supported')
            return original(fd)
        with patch('dbt_skills.local_context_updates.os.fsync', side_effect=sync):
            result = self.accept()
        self.assertEqual(result['status'], 'saved')
        self.assertFalse(result['directory_synced'])
        self.assertEqual(json.loads(self.path.read_text()), self.changed)

    def test_real_cli_exact_acceptance_and_static_error(self):
        proposal_path = self.root / 'review.json'
        proposal_path.write_text(json.dumps(self.proposal))
        args = [sys.executable, '-m', 'dbt_skills.local_context_updates', '--project-dir', str(self.root), '--target', 'business.json', '--proposal', str(proposal_path), '--accept-sha256', self.proposal['proposal_sha256']]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'saved')
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {'status': 'error', 'code': 'context_update_not_saved', 'reason': 'stale_base'})
