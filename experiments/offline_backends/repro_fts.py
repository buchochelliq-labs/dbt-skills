"""Minimal synthetic FTS probes; run Ladybug in a disposable subprocess."""
import argparse
import tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('engine',choices=['duckdb','ladybug']);p.add_argument('--literal',action='store_true');a=p.parse_args()
with tempfile.TemporaryDirectory() as tmp:
    if a.engine=='duckdb':
        import duckdb
        c=duckdb.connect(str(Path(tmp)/'db'));c.execute('LOAD fts')
        c.execute('CREATE TABLE t(id VARCHAR PRIMARY KEY,label VARCHAR)')
        c.execute("INSERT INTO t VALUES ('a','originalword')")
        c.execute("PRAGMA create_fts_index('t','id','label',incremental=1)")
        c.execute("UPDATE t SET label='updateduniqueterm' WHERE id='a'")
        print('base:',c.execute('SELECT * FROM t').fetchall(),flush=True)
        print('incremental:',c.execute("SELECT fts_main_t.match_bm25(id,'updateduniqueterm') FROM t").fetchall(),flush=True)
        c.execute("PRAGMA create_fts_index('t','id','label',overwrite=1,incremental=1)")
        print('rebuilt:',c.execute("SELECT fts_main_t.match_bm25(id,'updateduniqueterm') FROM t").fetchall(),flush=True)
        c.close()
    else:
        import ladybug
        d=ladybug.Database(str(Path(tmp)/'db'),buffer_pool_size=268435456,max_num_threads=1)
        c=ladybug.Connection(d)
        for q in ['LOAD EXTENSION fts','CREATE NODE TABLE t(id STRING, label STRING, PRIMARY KEY(id))',"CREATE (:t {id:'a',label:'customer'})", "CALL CREATE_FTS_INDEX('t','idx',['label'])"]:
            c.execute(q).close()
        for i in range(30):
            q="CALL QUERY_FTS_INDEX('t','idx','customer') RETURN node.id" if a.literal else "CALL QUERY_FTS_INDEX('t','idx',$term) RETURN node.id"
            r=c.execute(q,{} if a.literal else {'term':'customer'})
            rows=[]
            while r.has_next():rows.append(r.get_next())
            r.close();print(i,rows,flush=True)
        c.close();d.close()
