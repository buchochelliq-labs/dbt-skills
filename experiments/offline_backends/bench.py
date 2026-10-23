"""Disposable #62 microbenchmark, synthetic metadata only; NOT a product adapter.

Run each engine/size in a fresh process. No automatic extension installation.
Raw results distinguish unencrypted engine measurements from SQLCipher baseline.
"""
import argparse
import csv
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import tempfile
import time


def timed(fn):
    start = time.perf_counter()
    value = fn()
    return value, (time.perf_counter() - start) * 1000


def sample(fn, count=100):
    measurements = [timed(lambda: fn(i))[1] for i in range(count)]
    return {'p50_ms': statistics.median(measurements),
            'p95_ms': sorted(measurements)[math.ceil(count * .95)-1], 'samples': count}


def fixture(count):
    nodes, edges = [], []
    for i in range(count):
        tid = f'p:table:{i}'
        provenance = json.dumps({'provider': 'synthetic', 'asset_id': tid,
            'retrieved_at': '2026-10-23T00:00:00Z', 'revision': 'fixture-v1'}, sort_keys=True)
        nodes.append((tid, 'p', f'stg_xyz_customer_{i}', provenance))
        edges.append((tid, f'p:table:{(i+1)%count}', 'p'))
        for col in range(20):
            cid = f'{tid}:column:{col}'
            nodes.append((cid, 'p', f'customer_attribute_{col}', provenance))
            edges.append((cid, tid, 'p'))
    # Deliberately identical labels in another project: search must exclude them.
    nodes.append(('q:table:0', 'q', 'stg_xyz_customer_0', 'other-project'))
    return nodes, edges


class SQL:
    def __init__(self, root, engine, key=None):
        self.engine, self.root = engine, root
        if engine == 'duckdb':
            import duckdb
            self.version = duckdb.__version__
            self.db = duckdb.connect(str(root/'store.db'), config={'threads': 1, 'memory_limit': '256MB'})
            self.db.execute('LOAD fts')  # must be preinstalled for an offline run
        else:
            if engine == 'sqlcipher':
                from sqlcipher3 import dbapi2 as sqlite
            else:
                import sqlite3 as sqlite
            self.version = sqlite.sqlite_version
            self.db = sqlite.connect(root/'store.db')
            if key:
                self.db.execute('PRAGMA key="x\'' + key + '\'"')
            self.db.execute('PRAGMA cache_size=-262144')
        self.is_duck = engine == 'duckdb'

    def load(self, nodes, edges):
        self.db.execute('CREATE TABLE nodes(id VARCHAR PRIMARY KEY, project VARCHAR, label VARCHAR, provenance VARCHAR)')
        self.db.execute('CREATE TABLE edges(src VARCHAR, dst VARCHAR, project VARCHAR)')
        if self.is_duck:
            for name, rows in [('nodes', nodes), ('edges', edges)]:
                path = self.root/(name+'.csv')
                with path.open('w', newline='') as f:
                    csv.writer(f).writerows(rows)
                self.db.execute(f"COPY {name} FROM '{path}' (HEADER false)")
                path.unlink()
            self.db.execute('CREATE INDEX edge_src ON edges(src,project)')
            self.db.execute("PRAGMA create_fts_index('nodes','id','label',incremental=1)")
        else:
            self.db.executemany('INSERT INTO nodes VALUES (?,?,?,?)', nodes)
            self.db.executemany('INSERT INTO edges VALUES (?,?,?)', edges)
            self.db.execute('CREATE INDEX edge_src ON edges(src,project)')
            self.db.execute("CREATE VIRTUAL TABLE search USING fts5(label, content='nodes', content_rowid='rowid')")
            self.db.executescript('''CREATE TRIGGER node_ai AFTER INSERT ON nodes BEGIN
                INSERT INTO search(rowid,label) VALUES(new.rowid,new.label); END;
                CREATE TRIGGER node_ad AFTER DELETE ON nodes BEGIN
                INSERT INTO search(search,rowid,label) VALUES('delete',old.rowid,old.label); END;
                CREATE TRIGGER node_au AFTER UPDATE ON nodes BEGIN
                INSERT INTO search(search,rowid,label) VALUES('delete',old.rowid,old.label);
                INSERT INTO search(rowid,label) VALUES(new.rowid,new.label); END;''')
            self.db.execute("INSERT INTO search(search) VALUES('rebuild')")
        self.db.commit()

    def lookup(self, id):
        return self.db.execute("SELECT provenance FROM nodes WHERE id=? AND project='p'", [id]).fetchall()

    def graph(self, id):
        return self.db.execute('''WITH RECURSIVE walk(id,depth) AS (
            SELECT dst,1 FROM edges WHERE src=? AND project='p'
            UNION ALL SELECT e.dst,w.depth+1 FROM edges e JOIN walk w ON e.src=w.id
            WHERE e.project='p' AND w.depth<3)
            SELECT n.id FROM nodes n WHERE n.id IN (SELECT id FROM walk)
            AND n.project='p' ORDER BY n.id LIMIT 100''', [id]).fetchall()

    def search(self, term):
        if self.is_duck:
            return self.db.execute('''SELECT id FROM (
                SELECT id,fts_main_nodes.match_bm25(id,?) score FROM nodes WHERE project='p')
                WHERE score IS NOT NULL ORDER BY score DESC,id LIMIT 20''', [term]).fetchall()
        return self.db.execute('''SELECT n.id FROM search JOIN nodes n ON n.rowid=search.rowid
            WHERE search MATCH ? AND n.project='p' ORDER BY bm25(search),n.id LIMIT 20''', [term]).fetchall()

    def change(self, count):
        self.db.execute('BEGIN TRANSACTION')
        for i in range(count):
            self.db.execute('UPDATE nodes SET label=? WHERE id=?', ['updateduniqueterm', f'p:table:{i}'])
        self.db.commit()

    def delete(self, id):
        self.db.execute('BEGIN TRANSACTION')
        self.db.execute('DELETE FROM edges WHERE src=? OR dst=?', [id,id])
        self.db.execute('DELETE FROM nodes WHERE id=?', [id])
        self.db.commit()

    def close(self):
        self.db.close()


class Graph:
    def __init__(self, root, engine, key=None):
        import ladybug
        self.version = ladybug.__version__
        self.root = root
        self.db = ladybug.Database(str(root/'store.db'), buffer_pool_size=256*1024**2, max_num_threads=1)
        self.conn = ladybug.Connection(self.db)
        self.run('LOAD EXTENSION fts')

    def run(self, q, params=None):
        r = self.conn.execute(q, params or {})
        out = []
        while r.has_next():
            out.append(tuple(r.get_next()))
        r.close()
        return out

    def load(self, nodes, edges):
        self.run('CREATE NODE TABLE nodes(id STRING, project STRING, label STRING, provenance STRING, PRIMARY KEY(id))')
        self.run('CREATE REL TABLE edges(FROM nodes TO nodes, project STRING)')
        for name, rows in [('nodes',nodes), ('edges',edges)]:
            path = self.root/(name+'.csv')
            with path.open('w',newline='') as f: csv.writer(f).writerows(rows)
            self.run(f"COPY {name} FROM '{path}' (HEADER=false)")
            path.unlink()
        self.run("CALL CREATE_FTS_INDEX('nodes','node_search',['label'])")

    def lookup(self, id):
        return self.run("MATCH (n:nodes) WHERE n.id=$id AND n.project='p' RETURN n.provenance", {'id':id})

    def graph(self, id):
        return self.run("MATCH (a:nodes)-[e:edges*1..3]->(n:nodes) WHERE a.id=$id AND a.project='p' AND n.project='p' RETURN DISTINCT n.id ORDER BY n.id LIMIT 100", {'id':id})

    def search(self, term):
        # Fixed synthetic terms only: parameterized FTS crashes in pinned 0.21.2.
        if term not in ('stg xyz', 'updateduniqueterm'): raise ValueError('fixture term only')
        return self.run("CALL QUERY_FTS_INDEX('nodes','node_search','" + term + "') WITH node, score WHERE node.project='p' RETURN node.id ORDER BY score DESC, node.id LIMIT 20")

    def change(self, count):
        self.run('BEGIN TRANSACTION')
        for i in range(count):
            self.run('MATCH (n:nodes) WHERE n.id=$id SET n.label=$label', {'id':f'p:table:{i}', 'label':'updateduniqueterm'})
        self.run('COMMIT')

    def delete(self, id):
        self.run('MATCH (n:nodes) WHERE n.id=$id DETACH DELETE n', {'id':id})

    def close(self):
        self.conn.close()
        self.db.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('engine', choices=['sqlite','sqlcipher','duckdb','ladybug'])
    ap.add_argument('--relations', type=int, default=500)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.relations < 10: ap.error('at least 10 relations')
    ctor = Graph if args.engine == 'ladybug' else SQL
    # Ephemeral random key, never written to results. Synthetic metadata only.
    key = os.urandom(32).hex() if args.engine == 'sqlcipher' else None
    nodes, edges = fixture(args.relations)
    result = {'engine':args.engine,'relations':args.relations,'nodes':len(nodes),'edges':len(edges),
              'platform':platform.platform(),'python':platform.python_version(), 'encrypted':bool(key),
              'threads':1, 'configured_cache_or_memory_bytes':256*1024**2,
              'notes':['Single process, synthetic sparse graph; not an end-to-end product benchmark.',
                       'Reopen is OS-cache-warm, not cold disk. Peak RSS includes fixture generation.',
                       'No arbitrary source data or embeddings.']}
    with tempfile.TemporaryDirectory(prefix='offline-spike-') as tmp:
        root = Path(tmp)
        db, result['open_ms'] = timed(lambda:ctor(root,args.engine,key))
        result['version'] = db.version
        if args.engine == 'ladybug': result['notes'].append('Fixed literal FTS query only: repeated parameterized FTS crashes on this build; see repro_fts.py.')
        _, result['build_ms'] = timed(lambda:db.load(nodes,edges))
        rng = random.Random(62)
        ids = [f'p:table:{rng.randrange(args.relations)}' for _ in range(100)]
        assert db.lookup('q:table:0') == []
        assert db.lookup('p:table:0')[0][0] == nodes[0][3]
        assert {r[0] for r in db.graph('p:table:0')} == {f'p:table:{i}' for i in (1,2,3)}
        result['lookup'] = sample(lambda i:db.lookup(ids[i]))
        result['three_hop'] = sample(lambda i:db.graph(ids[i]))
        raw_search = db.search('stg xyz')
        assert all(r[0].startswith('p:') for r in raw_search)
        result['lexical_search'] = sample(lambda _:db.search('stg xyz'), 20)
        _, result['delta_1pct_ms'] = timed(lambda:db.change(max(1,args.relations//100)))
        result['fts_update_visible'] = 'p:table:0' in {r[0] for r in db.search('updateduniqueterm')}
        if not result['fts_update_visible']:
            if args.engine == 'duckdb':
                _, result['fts_rebuild_ms'] = timed(lambda:db.db.execute("PRAGMA create_fts_index('nodes','id','label',overwrite=1,incremental=1)"))
            elif args.engine == 'ladybug':
                db.run("CALL DROP_FTS_INDEX('nodes','node_search')")
                _, result['fts_rebuild_ms'] = timed(lambda:db.run("CALL CREATE_FTS_INDEX('nodes','node_search',['label'])"))
            assert 'p:table:0' in {r[0] for r in db.search('updateduniqueterm')}
        _, result['delete_ms'] = timed(lambda:db.delete('p:table:0'))
        assert db.lookup('p:table:0') == []
        result['fts_delete_visible'] = 'p:table:0' not in {r[0] for r in db.search('updateduniqueterm')}
        db.close()
        result['disk_bytes_after_close'] = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        db, result['reopen_ms'] = timed(lambda:ctor(root,args.engine,key))
        assert db.lookup('p:table:0') == []
        assert db.lookup('p:table:1')[0][0] == nodes[21][3]
        db.close()
    result['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if platform.system()=='Darwin' else 1024)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__': main()
