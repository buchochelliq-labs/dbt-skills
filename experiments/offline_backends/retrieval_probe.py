"""Disposable encrypted lexical/evidence retrieval baseline, synthetic metadata."""
from collections import deque
import json
from pathlib import Path
import tempfile
import sys
from projection_probe import connect


def paths(db, start, *, depth=3, edge_budget=20, path_budget=20):
    queue = deque([(start, (start,), ())])
    out, examined = [], 0
    while queue:
        node, visited, evidence = queue.popleft()
        if len(evidence) == depth:
            continue
        remaining = edge_budget - examined
        rows = db.execute('SELECT dst,evidence FROM edges WHERE src=? AND project=? ORDER BY dst,evidence LIMIT ?',
                          (node, 'p', remaining + 1)).fetchall()
        if len(rows) > remaining:
            return {'status': 'truncated', 'paths': out, 'examined': examined, 'reason': 'edge_budget'}
        for dst, proof in rows:
            examined += 1
            if dst in visited:
                continue
            if len(out) == path_budget:
                return {'status': 'truncated', 'paths': out, 'examined': examined, 'reason': 'path_budget'}
            route = (visited + (dst,), evidence + (proof,))
            out.append(route)
            queue.append((dst, *route))
    return {'status': 'complete_within_depth', 'paths': out, 'examined': examined}


def main():
    with tempfile.TemporaryDirectory(prefix='retrieval-spike-') as tmp:
        db = connect(Path(tmp), 'retrieval.db')
        docs = [('stg', 'p', 'stg_xyz_customer', 'customer client'),
                ('dim', 'p', 'dim_customer', 'customer client'),
                ('orders', 'p', 'sales.orders', 'order purchase'),
                ('normal', 'p', '3NF conventions', 'third normal form'),
                ('finance', 'p', 'ARR', 'annual recurring revenue'),
                ('foreign', 'q', 'stg_xyz_customer', 'customer client')]
        db.execute('CREATE TABLE docs(id TEXT PRIMARY KEY, project TEXT, title TEXT, aliases TEXT)')
        db.executemany('INSERT INTO docs VALUES (?,?,?,?)', docs)
        db.execute('CREATE VIRTUAL TABLE lexical USING fts5(title,aliases)')
        db.executemany('INSERT INTO lexical(rowid,title,aliases) VALUES (?,?,?)',
                       [(i, d[2], d[3]) for i, d in enumerate(docs, 1)])
        queries = [('stg_xyz_customer', {'stg'}), ('sales.orders', {'orders'}),
                   ('3NF', {'normal'}), ('annual recurring revenue', {'finance'}),
                   ('client', {'stg', 'dim'}), ('customer', {'stg', 'dim'}),
                   ('custmer', set()), ('people buying things', set())]
        lexical = []
        for query, expected in queries:
            # Treat user input as a literal phrase, not an FTS expression.
            phrase = '"' + query.replace('"', '""') + '"'
            found = [r[0] for r in db.execute('SELECT d.id FROM lexical JOIN docs d ON d.rowid=lexical.rowid WHERE lexical MATCH ? AND d.project=? ORDER BY bm25(lexical),d.id LIMIT 10', (phrase, 'p'))]
            assert set(found) == expected, (query, found)
            lexical.append({'query': query, 'ids': found})
        db.execute('CREATE TABLE edges(src TEXT,dst TEXT,project TEXT,evidence TEXT)')
        db.execute('CREATE INDEX edge_lookup ON edges(src,project,dst,evidence)')
        edges = [('customer', 'order', 'p', 'catalog#customer-order'),
                 ('customer', 'account', 'p', 'human#customer-account'),
                 ('account', 'order', 'p', 'catalog#account-order'),
                 ('order', 'customer', 'p', 'catalog#cycle'),
                 ('customer', 'secret', 'q', 'foreign#edge')]
        db.executemany('INSERT INTO edges VALUES (?,?,?,?)', edges)
        complete = paths(db, 'customer')
        expected = {(('customer', 'account'), ('human#customer-account',)),
                    (('customer', 'order'), ('catalog#customer-order',)),
                    (('customer', 'account', 'order'), ('human#customer-account', 'catalog#account-order'))}
        assert set(complete['paths']) == expected
        assert complete['status'] == 'complete_within_depth'
        limited = paths(db, 'customer', edge_budget=1)
        assert limited['status'] == 'truncated' and limited['reason'] == 'edge_budget'
        limited_paths = paths(db, 'customer', path_budget=1)
        assert limited_paths['status'] == 'truncated' and len(limited_paths['paths']) == 1
        db.close()
        return {'scope': 'small synthetic SQLCipher/FTS5 baseline, not cross-engine relevance ranking',
                'lexical': lexical, 'evidence_paths': complete,
                'edge_budget': limited, 'path_budget': limited_paths}


if __name__ == '__main__':
    result = main()
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + '\n')
    print('8 lexical cases and 3 evidence-path cases passed')
