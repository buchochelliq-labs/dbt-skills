"""Disposable model-free Cognee adapter experiment; not a permission integration."""
import asyncio
import importlib.metadata as md
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
from uuid import UUID

# Deliberately minimal local configuration. No credential is read or printed.
ROOT=tempfile.TemporaryDirectory(prefix='cognee-spike-root-')
os.environ['DATA_ROOT_DIRECTORY']=ROOT.name+'/data'
os.environ['SYSTEM_ROOT_DIRECTORY']=ROOT.name+'/system'
os.environ['LLM_MODEL']='llama3.1:8b'
os.environ['LLM_ENDPOINT']='http://127.0.0.1:11434/v1'
os.environ['LLM_API_KEY']='offline-spike-placeholder'
os.environ['EMBEDDING_ENDPOINT']='http://127.0.0.1:11434/api/embeddings'
os.environ['EMBEDDING_API_KEY']='offline-spike-placeholder'
os.environ['EMBEDDING_MODEL']='nomic-embed-text'
os.environ['TELEMETRY_DISABLED']='true'
os.environ['LLM_PROVIDER']='ollama'
os.environ['EMBEDDING_PROVIDER']='ollama'
os.environ['COGNEE_SKIP_PREFLIGHT']='true'
os.environ['COGNEE_SKIP_CONNECTION_TEST']='true'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='true'
attempts=[]
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):
        attempts.append(event)
        raise RuntimeError('Network forbidden by spike Python audit hook')
sys.addaudithook(audit)
started=time.perf_counter()
from cognee.infrastructure.databases.graph.ladybug.adapter import LadybugAdapter
from cognee.infrastructure.engine.models.DataPoint import DataPoint
from cognee.infrastructure.databases.provenance.source_refs import make_source_ref_key
import_ms=(time.perf_counter()-started)*1000

class Claim(DataPoint):
    asset_id: str
    field: str
    value: str
    provider: str
    observed_at: str
    project: str
    metadata: dict = {'index_fields': []}

async def main():
    result={'cognee':md.version('cognee'),'ladybug':md.version('ladybug'),
            'import_ms':import_ms, 'scope':'low-level graph adapter only; not high-level dataset ACL integration',
            'network_guard':'Python audit hook; native networking not OS-isolated'}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['DATA_ROOT_DIRECTORY']=tmp+'/data'
        os.environ['SYSTEM_ROOT_DIRECTORY']=tmp+'/system'
        path=tmp+'/graph'
        a=LadybugAdapter(path,kuzu_num_threads=1,kuzu_buffer_pool_size=268435456)
        uid=lambda i:UUID(int=i)
        source=make_source_ref_key(uid(100),uid(101))
        claims=[Claim(id=uid(i),asset_id='customers',field='grain',value=value,provider=provider,
                      observed_at='2026-10-23T00:00:00Z',project='p')
                for i,value,provider in [(1,'customer','catalog'),(2,'customer-account','human')]]
        start=time.perf_counter()
        await a.add_nodes(claims,source_ref_key=source)
        await a.add_edges([(str(uid(1)),str(uid(2)),'contradicts',{'evidence':'synthetic'})],source_ref_key=source)
        result['two_claims_one_edge_write_ms']=(time.perf_counter()-start)*1000
        before=await a.get_nodes([str(uid(1)),str(uid(2))])
        # Preserve both claims and original observation, independently of adapter timestamps.
        assert len(before)==2
        assert {n['value'] for n in before}=={'customer','customer-account'}
        assert all(n['observed_at']=='2026-10-23T00:00:00Z' for n in before)
        result['source_ref_in_get_nodes']=source in json.dumps(before,default=str)
        ownership=await a.get_node_delete_data([str(uid(1)),str(uid(2))])
        result['source_ref_in_ownership_api']=all(source in n.source_ref_keys for n in ownership.values())
        assert len(ownership)==2 and result['source_ref_in_ownership_api']
        neighborhood=await a.get_neighborhood([str(uid(1))],depth=1)
        result['neighborhood_nodes']=len(neighborhood[0]);result['neighborhood_edges']=len(neighborhood[1])
        assert result['neighborhood_nodes']==2 and result['neighborhood_edges']==1
        # A low-level graph getter does not enforce our project selection.
        foreign=Claim(id=uid(3),asset_id='customers',field='grain',value='foreign',provider='catalog',observed_at='2026-10-23T00:00:00Z',project='q')
        await a.add_nodes([foreign])
        result['low_level_getter_returns_other_project']=(await a.get_node(str(uid(3))))['project']=='q'
        await a.close()
        a=LadybugAdapter(path,kuzu_num_threads=1,kuzu_buffer_pool_size=268435456)
        reopened=await a.get_nodes([str(uid(1)),str(uid(2))])
        result['restart_retains_values']=len(reopened)==2 and {n['value'] for n in reopened}=={'customer','customer-account'}
        assert result['restart_retains_values']
        await a.delete_nodes([str(uid(1))])
        assert await a.get_node(str(uid(1))) is None
        assert await a.get_edges(str(uid(2)))==[]
        assert (await a.get_node(str(uid(2))))['value']=='customer-account'
        await a.close()
        result['delete_retains_other_claim']=True
        result['disk_bytes']=sum(p.stat().st_size for p in Path(tmp).rglob('*') if p.is_file())
    result['network_attempts']=attempts
    result['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

try:
    asyncio.run(main())
finally:
    ROOT.cleanup()
