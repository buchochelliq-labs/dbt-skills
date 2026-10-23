"""Disposable correctness/latency probe for branching, convergent and cyclic graphs.

Fresh child per engine/topology/repetition; 30-second process timeout. Only graph
queries measured here, not imports, FTS build or fixture load. Independent BFS oracle.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
from bench import SQL, Graph, sample


def fixture(kind):
    if kind=='cyclic':
        ids=[f'n{i:04d}' for i in range(500)]
        edges=[(ids[i],ids[(i+j)%500],'p') for i in range(500) for j in (1,3,7,13,29,61)]
    else:
        ids=['root']+[f'b{i:03d}' for i in range(64)]+[f'c{i:03d}' for i in range(64)]+['sink']
        edges=[('root',f'b{i:03d}','p') for i in range(64)]
        edges += [(f'b{i:03d}',f'c{j:03d}','p') for i in range(64) for j in range(64)]
        edges += [(f'c{i:03d}','sink','p') for i in range(64)]
        edges += [('sink','root','p')]
    return [(id,'p','synthetic concept','fixture-v2') for id in ids],edges,ids[0]


def oracle(edges,start):
    adjacency=defaultdict(set)
    for a,b,_ in edges:adjacency[a].add(b)
    frontier={start};found=set()
    for _ in range(3):
        frontier={n for v in frontier for n in adjacency[v]}
        found.update(frontier)
    return sorted(found)[:100],len(found)


def worker(engine,kind):
    nodes,edges,start=fixture(kind);expected,total=oracle(edges,start)
    with tempfile.TemporaryDirectory() as tmp:
        ctor=Graph if engine=='ladybug' else SQL
        # Synthetic storage only; direct SQLite is encrypted in the main baseline,
        # but this probe explicitly uses plaintext SQLite for all-engine parity.
        db=ctor(Path(tmp),engine);db.load(nodes,edges)
        actual=[r[0] for r in db.graph(start)]
        assert actual==expected,(actual,expected)
        if engine != 'ladybug':
            # Endpoint reachability does not require enumerating duplicate paths.
            # UNION deduplicates (node,depth) before the next expansion.
            def deduplicated():
                return db.db.execute("""WITH RECURSIVE walk(id,depth) AS (
                    SELECT dst,1 FROM edges WHERE src=? AND project='p'
                    UNION SELECT e.dst,w.depth+1 FROM edges e JOIN walk w ON e.src=w.id
                    WHERE e.project='p' AND w.depth<3)
                    SELECT n.id FROM nodes n WHERE n.id IN (SELECT id FROM walk)
                    AND n.project='p' ORDER BY n.id LIMIT 100""",[start]).fetchall()
            assert [r[0] for r in deduplicated()]==expected
            dedup=sample(lambda _:deduplicated(),30)
        else: dedup=None
        result={'engine':engine,'version':db.version,'topology':kind,'nodes':len(nodes),
                'edges':len(edges),'reachable_nodes':total,'returned_nodes':len(actual),
                'oracle_equal':True,'deduplicated_sql_three_hop':dedup,'three_hop':sample(lambda _:db.graph(start),30)}
        db.close()
        result['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        print(json.dumps(result))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--worker',nargs=2);ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if args.worker:worker(*args.worker)
    else:
        results=[]
        for kind in ('cyclic','convergent'):
            for engine in ('sqlite','duckdb','ladybug'):
                for rep in (1,2,3):
                    try:
                        r=subprocess.run([sys.executable,__file__,'--worker',engine,kind],capture_output=True,text=True,timeout=30)
                        if r.returncode:
                            result={'engine':engine,'topology':kind,'exit_code':r.returncode,'error':r.stderr[-500:]}
                        else:result=json.loads(r.stdout)
                    except subprocess.TimeoutExpired:
                        result={'engine':engine,'topology':kind,'timeout_seconds':30}
                    result['repetition']=rep;results.append(result)
                    print(json.dumps(result),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(results,indent=2)+'\n')
