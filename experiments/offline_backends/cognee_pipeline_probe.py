"""Disposable #62 released graph-only pipeline + dataset lifecycle probe.

No patched engines, extraction or embedding calls; synthetic metadata only.
Python network audit hook is not a native/OS egress sandbox.
"""
import asyncio
import importlib.metadata as md
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import NAMESPACE_URL, uuid5

ROOT = tempfile.TemporaryDirectory(prefix='cognee-pipeline-')
os.environ.pop('HUGGINGFACE_TOKENIZER',None)
os.environ.update({
    'DATA_ROOT_DIRECTORY': ROOT.name+'/data', 'SYSTEM_ROOT_DIRECTORY': ROOT.name+'/system',
    'HF_HOME':ROOT.name+'/hf', 'TIKTOKEN_CACHE_DIR':ROOT.name+'/tiktoken',
    'TELEMETRY_DISABLED':'true', 'LLM_PROVIDER':'ollama', 'LLM_MODEL':'llama3.1:8b',
    'LLM_ENDPOINT':'http://127.0.0.1:11434/v1', 'LLM_API_KEY':'offline-spike-placeholder',
    'EMBEDDING_PROVIDER':'ollama', 'EMBEDDING_MODEL':'nomic-embed-text',
    'EMBEDDING_ENDPOINT':'http://127.0.0.1:11434/api/embeddings', 'EMBEDDING_API_KEY':'offline-spike-placeholder',
    'COGNEE_SKIP_PREFLIGHT':'true', 'COGNEE_SKIP_CONNECTION_TEST':'true',
    'LITELLM_LOCAL_MODEL_COST_MAP':'true', 'ENABLE_BACKEND_ACCESS_CONTROL':'true',
    'GRAPH_DATABASE_PROVIDER':'ladybug', 'GRAPH_DATABASE_SUBPROCESS_ENABLED':'false',
    'VECTOR_DB_SUBPROCESS_ENABLED':'false', 'KUZU_NUM_THREADS':'1', 'KUZU_BUFFER_POOL_SIZE':'268435456',
})
# Optional documented tokenizer override with pre-staged HF files.
if '--cached-tokenizer' in sys.argv:
    os.environ['HF_HOME']=os.environ.get('SPIKE_HF_CACHE','/tmp/dbt-spike-hf-cache')
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['HUGGINGFACE_TOKENIZER']='nomic-ai/nomic-embed-text-v1.5'
attempts=[]
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):
        attempts.append(event)
        raise RuntimeError('Network forbidden by spike Python audit hook')
sys.addaudithook(audit)
import cognee
from cognee.modules.engine.operations.setup import setup
from cognee.modules.users.methods.get_default_user import get_default_user
from cognee.modules.users.methods.create_user import create_user
from cognee.modules.pipelines.models.PipelineContext import PipelineContext
from cognee.infrastructure.engine.models.DataPoint import DataPoint
from cognee.infrastructure.databases.graph.get_graph_engine import get_graph_engine
from cognee.context_global_variables import set_database_global_context_variables
from cognee.tasks.storage.add_data_points import add_data_points
from cognee.infrastructure.databases.provenance.source_refs import make_source_ref_key

class Evidence(DataPoint):
    name: str
    project: str
    field: str
    value: str
    provider: str
    observed_at: str
    metadata: dict = {'index_fields': []}

def evidence(key,project,value):
    return Evidence(id=uuid5(NAMESPACE_URL,key),name='customer grain',project=project,
        field='grain',value=value,provider=key,observed_at='2026-10-23T00:00:00Z')

async def main(result):
    result['stage']='setup'
    await setup()
    owner=await get_default_user()
    outsider=await create_user('outsider@example.test',password=None)
    result['stage']='ingest synthetic metadata documents'
    await cognee.add('Synthetic catalog declaration: customer grain.',dataset_name='project_p',user=owner,skip_connection_test=True)
    await cognee.add('Synthetic human declaration: customer-account grain.',dataset_name='project_p',user=owner,skip_connection_test=True)
    await cognee.add('Synthetic other-project declaration.',dataset_name='project_q',user=owner,skip_connection_test=True)
    datasets=await cognee.datasets.list_datasets(user=owner)
    p=next(d for d in datasets if d.name=='project_p')
    q=next(d for d in datasets if d.name=='project_q')
    docs=await cognee.datasets.list_data(p.id,user=owner)
    qdocs=await cognee.datasets.list_data(q.id,user=owner)
    assert len(docs)==2 and len(qdocs)==1
    claims=[evidence('p/catalog','p','customer'),evidence('p/human','p','customer-account')]
    foreign=evidence('q/catalog','q','foreign')
    shared=evidence('p/shared','p','shared concept')
    result['stage']='graph-only pipeline with real dataset context'
    async with set_database_global_context_variables(p.id,owner.id,permission_type='write'):
        for claim,doc in zip(claims,docs):
            await add_data_points([claim,shared],custom_edges=[(str(claim.id),str(shared.id),'describes',{})],
                ctx=PipelineContext(user=owner,dataset=p,data_item=doc),graph_only=True)
        graph=await get_graph_engine()
        rows=await graph.get_nodes([str(c.id) for c in claims])
        assert {n['value'] for n in rows}=={'customer','customer-account'}
        assert all(n['observed_at']=='2026-10-23T00:00:00Z' for n in rows)
        ownership=await graph.get_node_delete_data([str(shared.id)])
        assert set(ownership[str(shared.id)].source_ref_keys)=={make_source_ref_key(p.id,d.id) for d in docs}
        result['shared_node_has_two_source_owners']=True
        result['conflicts_and_original_observation_preserved']=True
    async with set_database_global_context_variables(q.id,owner.id,permission_type='write'):
        await add_data_points([foreign],ctx=PipelineContext(user=owner,dataset=q,data_item=qdocs[0]),graph_only=True)
        graph=await get_graph_engine()
        assert await graph.get_node(str(claims[0].id)) is None
    async with set_database_global_context_variables(p.id,owner.id,permission_type='read'):
        graph=await get_graph_engine()
        assert await graph.get_node(str(foreign.id)) is None
    result['project_database_isolation']=True
    result['stage']='unauthorized dataset access'
    try:
        await cognee.datasets.list_data(p.id,user=outsider)
    except Exception as exc:
        result['outsider_list_exception']=type(exc).__name__
    else: raise AssertionError('outsider read allowed')
    try:
        async with set_database_global_context_variables(p.id,outsider.id,permission_type='read'):
            raise AssertionError('outsider context allowed')
    except AssertionError: raise
    except Exception as exc:
        result['outsider_context_exception']=type(exc).__name__
    try:
        await cognee.datasets.delete_data(p.id,docs[0].id,user=outsider)
    except Exception as exc:
        result['outsider_delete_exception']=type(exc).__name__
    else: raise AssertionError('outsider delete allowed')
    assert result['outsider_list_exception']=='PermissionDeniedError'
    assert result['outsider_context_exception']=='PermissionDeniedError'
    assert result['outsider_delete_exception']=='UnauthorizedDataAccessError'
    result['stage']='source deletion with shared ownership'
    try:
        await cognee.datasets.delete_data(p.id,docs[0].id,user=owner)
    except Exception:
        async with set_database_global_context_variables(p.id,owner.id,permission_type='read'):
            graph=await get_graph_engine()
            result['failed_delete_retains_both_claims']=len(await graph.get_nodes([str(c.id) for c in claims]))==2
            ownership=await graph.get_node_delete_data([str(shared.id)])
            result['failed_delete_retains_both_source_refs']=len(ownership[str(shared.id)].source_ref_keys)==2
        result['failed_delete_retains_both_documents']=len(await cognee.datasets.list_data(p.id,user=owner))==2
        raise
    async with set_database_global_context_variables(p.id,owner.id,permission_type='read'):
        graph=await get_graph_engine()
        assert await graph.get_node(str(claims[0].id)) is None
        assert (await graph.get_node(str(claims[1].id)))['value']=='customer-account'
        ownership=await graph.get_node_delete_data([str(shared.id)])
        assert ownership[str(shared.id)].source_ref_keys==[make_source_ref_key(p.id,docs[1].id)]
        assert len(await graph.get_edges(str(shared.id)))==1
    result['first_source_delete_preserves_shared_node_and_other_claim']=True
    await cognee.datasets.delete_data(p.id,docs[1].id,user=owner)
    async with set_database_global_context_variables(p.id,owner.id,permission_type='read'):
        graph=await get_graph_engine()
        assert await graph.get_node(str(shared.id)) is None
        assert await graph.get_node(str(claims[1].id)) is None
    async with set_database_global_context_variables(q.id,owner.id,permission_type='read'):
        graph=await get_graph_engine()
        assert (await graph.get_node(str(foreign.id)))['value']=='foreign'
    result['last_source_delete_removes_graph_without_affecting_other_project']=True
    result['stage']='complete'

result={'cognee':md.version('cognee'),'ladybug':md.version('ladybug'),
        'cached_tokenizer':'--cached-tokenizer' in sys.argv, 'graph_subprocess_enabled':False,'network_guard':'Python audit hook only',
        'scope':'real local datasets, graph_only storage task, explicit permission context, public dataset delete'}
try:
    asyncio.run(main(result))
except Exception as exc:
    result['error_type']=type(exc).__name__
    import traceback; traceback.print_exc()
finally:
    result['network_attempts']=attempts
    out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    ROOT.cleanup()
if 'error_type' in result: sys.exit(1)
