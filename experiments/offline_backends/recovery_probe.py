"""Disposable #62 crash probe of the real SQLCipher store + proposed read gate.

Synthetic metadata only. FileKeyStore is test-only; never a production key option.
The projection gate is an experiment, not shipped policy or a Cognee integration.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / 'src')]
from dbt_skills.ontology import LocalOntologyStore
from tests.cache_test_support import FileKeyStore
from tests.test_ontology import MemoryProvider, claim

EXIT = 73
IDS = ('keep', 'remove', 'added')


def open_store(root, kind=LocalOntologyStore):
    return kind(root / 'claims.db', key_store=FileKeyStore(root / 'test-key.json'))


def replacement():
    p = MemoryProvider([claim('keep', 'customer', 'grain', 'new grain'),
                        claim('added', 'customer', 'definition', 'new definition')], page_size=1)
    p.deleted_claim_ids = ['remove']
    return p


def values(store):
    return {i: record.claim.object_value for i in IDS
            if (record := store.get_claim('source-a', i)) is not None}


def worker(root, point, mode):
    class InterruptedStore(LocalOntologyStore):
        def _stage_page(self, *args):
            super()._stage_page(*args)
            if point == 'after_stage':
                os._exit(EXIT)

        def _upsert_provider_claim(self, *args):
            super()._upsert_provider_claim(*args)
            if point == 'during_publish':
                os._exit(EXIT)  # transaction is open; no Python cleanup

        def _publish_generation(self, *args):
            super()._publish_generation(*args)
            if point == 'after_commit':
                os._exit(EXIT)

    asyncio.run(open_store(root, InterruptedStore).sync_source(
        'source-a', replacement(), full_refresh=mode == 'full', page_size=1))
    raise AssertionError('interruption did not fire')


def projection_gate(envelope, *, project, generation, claims, allowed, quarantined,
                    permission_expires, now):
    """Proposed whole-result rejection; inputs represent a captured policy snapshot.

    No values from the index are trusted. Real integration must additionally bind
    policy revision atomically and revalidate before returning to the host.
    """
    if envelope['project'] != project:
        return {'status': 'unavailable', 'reason': 'project_mismatch', 'claims': []}
    if now >= permission_expires:
        return {'status': 'unavailable', 'reason': 'permission_expired', 'claims': []}
    if envelope['generation'] != generation:
        return {'status': 'unavailable', 'reason': 'generation_mismatch', 'claims': []}
    if not envelope['complete']:
        return {'status': 'unavailable', 'reason': 'incomplete_projection', 'claims': []}
    ids = envelope['claim_ids']
    if any(i not in allowed or i in quarantined or i not in claims for i in ids):
        return {'status': 'unavailable', 'reason': 'invalid_evidence', 'claims': []}
    return {'status': 'available', 'claims': [claims[i] for i in ids]}


def run_case(mode, point):
    with tempfile.TemporaryDirectory(prefix='generation-probe-') as tmp:
        root = Path(tmp)
        store = open_store(root)
        store.register_source('source-a', 'memory', enabled=True)
        asyncio.run(store.sync_source('source-a', MemoryProvider([
            claim('keep', 'customer', 'grain', 'old grain'),
            claim('remove', 'customer', 'definition', 'old definition')]), full_refresh=True))
        old_generation = store.source_status('source-a')['generation']
        expected_old = {'keep': 'old grain', 'remove': 'old definition'}
        expected_new = {'keep': 'new grain', 'added': 'new definition'}
        proc = subprocess.run([sys.executable, __file__, '--worker', str(root),
                               '--point', point, '--mode', mode], timeout=30,
                              capture_output=True, text=True)
        assert proc.returncode == EXIT, (proc.returncode, proc.stderr)
        reopened = open_store(root)
        after = values(reopened)
        committed = point == 'after_commit'
        assert after == (expected_new if committed else expected_old), after
        recovered_generation = reopened.source_status('source-a')['generation']
        assert (recovered_generation != old_generation) == committed
        # Verify the lexical index participates in the same recovery boundary.
        assert bool(reopened.search('old grain')) == (not committed)
        assert bool(reopened.search('new grain')) == committed
        if not committed:
            asyncio.run(reopened.sync_source('source-a', replacement(),
                                            full_refresh=mode == 'full', page_size=1))
        assert values(reopened) == expected_new
        final_generation = reopened.source_status('source-a')['generation']
        assert final_generation != old_generation
        assert reopened.get_claim('source-a', 'keep').claim.observed_at == '2026-10-22T00:00:00Z'
        assert open_store(root).source_status('source-a')['generation'] == final_generation
        assert values(open_store(root)) == expected_new
        # Prototype stale/unauthorized projection handling over the real recovered values.
        base = dict(project='p', generation=final_generation, claim_ids=['keep', 'added'], complete=True)
        policy = dict(project='p', generation=final_generation, claims=values(reopened),
                      allowed={'keep', 'added'}, quarantined=set(), permission_expires=20, now=10)
        checks = {}
        cases = [
            ('matching', {}, {}, 'available'),
            ('stale_generation', {'generation': old_generation}, {}, 'unavailable'),
            ('wrong_project', {'project': 'q'}, {}, 'unavailable'),
            ('permission_boundary', {}, {'now': 20}, 'unavailable'),
            ('revoked', {}, {'allowed': set()}, 'unavailable'),
            ('removed_asset', {}, {'allowed': {'keep'}}, 'unavailable'),
            ('quarantined', {}, {'quarantined': {'added'}}, 'unavailable'),
            ('partial', {'complete': False}, {}, 'unavailable'),
            ('unknown_claim', {'claim_ids': ['keep', 'unknown']}, {}, 'unavailable'),
        ]
        for name, env_change, pol_change, expected in cases:
            response = projection_gate(base | env_change, **(policy | pol_change))
            assert response['status'] == expected
            if expected == 'unavailable':
                assert response['claims'] == []
            else:
                assert response['claims'] == ['new grain', 'new definition']
            checks[name] = response['status']
        return dict(mode=mode, interruption=point, child_exit=proc.returncode,
                    reopened_snapshot='new' if committed else 'old',
                    lexical_index_consistent=True, resume_and_second_reopen_complete=True,
                    original_observation_preserved=True, prototype_gate=checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--point')
    parser.add_argument('--mode')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.point, args.mode)
    else:
        results = [run_case(mode, point) for mode in ('full', 'incremental')
                   for point in ('after_stage', 'during_publish', 'after_commit')]
        output = {'scope': 'real SQLCipher ontology crash/reopen; prototype projection policy',
                  'crash_method': 'os._exit(73) in child; not power-loss simulation',
                  'cases': results}
        args.output.write_text(json.dumps(output, indent=2) + '\n')
        print(json.dumps({'completed_cases': len(results), 'prototype_gate_checks': len(results)*9}))
