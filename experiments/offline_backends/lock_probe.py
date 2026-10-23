"""Can a second local process write while the first owns an open database?"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

def connect(engine,path):
    if engine=='sqlite':
        import sqlite3
        return sqlite3.connect(path,timeout=.1),None
    if engine=='duckdb':
        import duckdb
        return duckdb.connect(path),None
    import ladybug
    d=ladybug.Database(path,buffer_pool_size=268435456,max_num_threads=1)
    return ladybug.Connection(d),d

def close(c,d):
    c.close()
    if d:d.close()

p=argparse.ArgumentParser();p.add_argument('engine');p.add_argument('--child');a=p.parse_args()
if a.child:
    try:
        c,d=connect(a.engine,a.child)
        c.execute("CREATE (:t {id:2})" if d else 'INSERT INTO t VALUES (2)')
        if a.engine=='sqlite':c.commit()
        close(c,d)
        print(json.dumps({'second_writer':'succeeded'}))
    except Exception as e:
        print(json.dumps({'second_writer':'rejected','exception_type':type(e).__name__}))
else:
    with tempfile.TemporaryDirectory() as tmp:
        path=str(Path(tmp)/'db');c,d=connect(a.engine,path)
        c.execute('CREATE NODE TABLE t(id INT64, PRIMARY KEY(id))' if d else 'CREATE TABLE t(id INTEGER)')
        if a.engine=='sqlite':c.commit()
        r=subprocess.run([sys.executable,__file__,a.engine,'--child',path],capture_output=True,text=True,timeout=15)
        close(c,d)
        print(json.dumps({'engine':a.engine,'child_exit':r.returncode,'result':json.loads(r.stdout)}))
