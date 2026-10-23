"""Disposable encrypted FTS5 generation activation experiment; not a product API."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from recovery_probe import open_store, claim, MemoryProvider, FileKeyStore
from dbt_skills.cache_security import open_encrypted_database

EXIT = 74


def connect(root, name):
    path = root / name
    key = FileKeyStore(root / 'test-key.json').get_or_create_key(path, create=True)
    return open_encrypted_database(path, key)


def state(root):
    db = connect(root, 'registry.db')
    try:
        return db.execute('SELECT target,active,revision FROM state').fetchone()
    finally:
        db.close()


def change(root, target=None):
    db = connect(root, 'registry.db')
    try:
        with db:
            db.execute('UPDATE state SET target=coalesce(?,target),revision=revision+1', (target,))
    finally:
        db.close()


def snapshot(root):
    store = open_store(root)
    generations, claims = {}, {}
    for source in ('source-a', 'source-b'):
        generations[source] = store.source_status(source)['generation']
        record = store.get_claim(source, 'shared-id')
        # The same local ID in different sources must remain distinct.
        claims[source + '#shared-id'] = record.claim.object_value
    return json.dumps(generations, sort_keys=True), claims


def build(root, name, point=None):
    target, _, revision = state(root)
    vector, claims = snapshot(root)
    assert vector == target
    db = connect(root, name)
    try:
        db.execute('CREATE VIRTUAL TABLE docs USING fts5(claim_id UNINDEXED, body)')
        db.execute('CREATE TABLE metadata(generation TEXT, complete INTEGER)')
        db.execute('INSERT INTO metadata VALUES (?,0)', (vector,))
        for n, (identity, value) in enumerate(sorted(claims.items())):
            db.execute('INSERT INTO docs VALUES (?,?)', (identity, value))
            db.commit()  # intentionally incremental build, not one all-or-nothing write
            if point == 'partial_build' and n == 0:
                os._exit(EXIT)
        actual = dict(db.execute('SELECT claim_id,body FROM docs'))
        assert actual == claims
        assert {r[0] for r in db.execute("SELECT claim_id FROM docs WHERE docs MATCH 'customer'")} == set(claims)
        db.execute('UPDATE metadata SET complete=1')
        db.commit()
    finally:
        db.close()
    if point == 'before_activation':
        os._exit(EXIT)
    registry = connect(root, 'registry.db')
    try:
        registry.execute('BEGIN IMMEDIATE')
        assert registry.execute('SELECT target,revision FROM state').fetchone() == (target, revision)
        registry.execute('UPDATE state SET active=?,revision=revision+1', (name,))
        if point == 'during_activation':
            os._exit(EXIT)
        registry.commit()
        if point == 'after_activation':
            os._exit(EXIT)
    finally:
        registry.close()


def read(root, during_read=None):
    before = state(root)
    target, active, _ = before
    vector, canonical = snapshot(root)
    unavailable = {'status': 'unavailable', 'claims': []}
    if target != vector or not active or not (root / active).is_file():
        return unavailable
    db = connect(root, active)
    try:
        if db.execute('SELECT generation,complete FROM metadata').fetchone() != (target, 1):
            return unavailable
        ids = [r[0] for r in db.execute("SELECT claim_id FROM docs WHERE docs MATCH 'customer' ORDER BY claim_id")]
    finally:
        db.close()
    if during_read:
        during_read()
    # This detects the injected revision change; not a lock across host delivery.
    if state(root) != before or snapshot(root)[0] != vector or any(i not in canonical for i in ids):
        return unavailable
    return {'status': 'available', 'claims': [(i, canonical[i]) for i in ids]}


def case(point):
    with tempfile.TemporaryDirectory(prefix='projection-spike-') as tmp:
        root = Path(tmp)
        store = open_store(root)
        for source in ('source-a', 'source-b'):
            store.register_source(source, 'memory', enabled=True)
            asyncio.run(store.sync_source(source, MemoryProvider([
                claim('shared-id', 'customer', 'definition', 'customer old ' + source)]), full_refresh=True))
        target, _ = snapshot(root)
        db = connect(root, 'registry.db')
        db.execute('CREATE TABLE state(target TEXT,active TEXT,revision INTEGER)')
        db.execute('INSERT INTO state VALUES (?,NULL,0)', (target,))
        db.commit()
        db.close()
        build(root, 'old.db')
        assert len(read(root)['claims']) == 2
        # Only one source changes: vector identity must include both sources.
        asyncio.run(store.sync_source('source-a', MemoryProvider([
            claim('shared-id', 'customer', 'definition', 'customer new source-a')]), full_refresh=True))
        target, expected = snapshot(root)
        change(root, target)
        assert read(root) == {'status': 'unavailable', 'claims': []}
        proc = subprocess.run([sys.executable, __file__, '--worker', str(root), point],
                              timeout=30, capture_output=True, text=True)
        assert proc.returncode == EXIT, (proc.returncode, proc.stderr)
        after = read(root)
        activated = point == 'after_activation'
        assert after['status'] == ('available' if activated else 'unavailable')
        if activated:
            assert dict(after['claims']) == expected
        else:
            build(root, 'rebuilt.db')
        assert dict(read(root)['claims']) == expected
        # Simulated permission/scope revision event while a real FTS query is in flight.
        assert read(root, lambda: change(root)) == {'status': 'unavailable', 'claims': []}
        # Serial cleanup after all readers/builders have stopped; not a GC lease protocol.
        active = state(root)[1]
        removed = []
        for name in ('old.db', 'candidate.db', 'rebuilt.db'):
            if name != active and (root / name).exists():
                for suffix in ('', '-wal', '-shm'):
                    path = root / (name + suffix)
                    if path.exists():
                        path.unlink()
                removed.append(name)
        assert dict(read(root)['claims']) == expected
        return {'interruption': point, 'child_exit': proc.returncode,
                'after_restart': after['status'], 'rebuild_or_committed_read_correct': True,
                'two_source_identity_preserved': True, 'stale_projection_withheld': True,
                'injected_revision_change_withheld': True, 'serial_cleanup_preserves_active': True,
                'abandoned_files_removed': removed}


if __name__ == '__main__':
    if sys.argv[1] == '--worker':
        build(Path(sys.argv[2]), 'candidate.db', sys.argv[3])
        raise AssertionError('interruption did not fire')
    output = {'scope': 'real separate SQLCipher FTS5 files and encrypted activation registry; disposable adapter',
              'cases': [case(p) for p in ('partial_build', 'before_activation', 'during_activation', 'after_activation')]}
    Path(sys.argv[1]).write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'completed_cases': len(output['cases'])}))
