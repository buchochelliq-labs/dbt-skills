"""Independent user-flow acceptance through the public MCP stdio protocol only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/data-model-workflow'

def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}

async def main():
    before = hashes(FIXTURE)
    events = []
    with tempfile.TemporaryDirectory(prefix='agent-metadata-') as tmp:
        project = Path(tmp) / 'context'
        shutil.copytree(FIXTURE, project)
        params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(project), '--target-path', 'artifacts', '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                events.append({'method': 'initialize', 'result': (await session.initialize()).model_dump(mode='json')})
                discovered = (await session.list_tools()).model_dump(mode='json')
                events.append({'method': 'tools/list', 'result': discovered})
                async def call(name, args):
                    try:
                        result = await session.call_tool(name, args)
                        payload = result.model_dump(mode='json')
                    except MCPError as exc:
                        payload = {'protocol_error': {'code': exc.code, 'message': exc.message}}
                        events.append({'method': 'tools/call', 'name': name, 'arguments': args, 'result': payload})
                        return payload
                    events.append({'method': 'tools/call', 'name': name, 'arguments': args, 'result': payload})
                    return payload.get('structured_content') or json.loads(payload['content'][0]['text'])
                ctx = await call('modelling_context', {})
                cid = ctx['context_id']
                common = {'context_id': cid}
                naming = await call('modelling_rules', {**common, 'section': 'naming'})
                await call('modelling_rules', {**common, 'section': 'modelling'})
                status = await call('catalog_status', common)
                for provider in status['providers']:
                    await call('catalog_search', {**common, 'provider_id': provider['id'], 'query': '', 'limit': 20})
                request = json.loads((FIXTURE / 'design-request.json').read_text())
                for asset in request['assets']:
                    await call('catalog_resolve', {**common, 'asset_id': asset['asset_id'], 'fields': ['relation', 'columns', 'primary_key', 'foreign_keys']})
                plan = await call('model_plan', {**common, 'request': request})
                assert len(plan['entities']) == 2
                assert plan['relationships'][0]['status'] == 'declared_endpoints_valid'
                assert all(e['normal_form_status'] == 'unverified' and not e['grain']['verified'] for e in plan['entities'])
                rule = next(r for r in naming['rules'] if r['target'] == 'model_file')
                await call('modelling_render', {**common, 'rule_id': rule['id'], 'values': {}})
                for concept in ['customer', 'order']:
                    await call('modelling_render', {**common, 'rule_id': rule['id'], 'values': {'system': 'xyz', 'concept': concept}})
                model = plan['entities'][0]['existing_models'][0]
                await call('modelling_compare', {**common, 'model_id': model, 'context': {'system': 'xyz', 'concept': 'customer'}})
                preproposal = hashes(project)
                proposal = await call('modelling_propose', {**common, 'rule_id': rule['id'], 'model_id': model, 'rationale': 'Draft compatibility exception for the existing customer filename while downstream consumers are reviewed; human approval remains required.'})
                assert proposal['status'] == 'pending_review'
                assert proposal['policy_patch'] == []
                assert proposal['proposal_document']['records'][0]['models'] == [model]
                assert hashes(project) == preproposal, 'proposal mutated context files'
                orders_only = {**request, 'assets': [request['assets'][1]]}
                missing = await call('model_plan', {**common, 'request': orders_only})
                assert len(missing['entities']) == 1
                assert missing['relationships'][0]['status'] == 'unresolved'
                assert request['assets'][0]['asset_id'] not in missing['evidence']
                curated_path = project / 'curated.json'
                curated = json.loads(curated_path.read_text())
                curated['assets'][1]['facts']['foreign_keys'][0]['target_columns'] = ['missing_customer_id']
                curated_path.write_text(json.dumps(curated, indent=2) + '\n')
                refreshed = await call('modelling_refresh', {})
                assert refreshed['context_id'] != cid
                stale = await call('model_plan', {**common, 'request': request})
                assert stale['protocol_error']['message'] == 'Context changed; call modelling_context and review the refreshed evidence'
                broken = await call('model_plan', {'context_id': refreshed['context_id'], 'request': request})
                assert broken['relationships'][0]['status'] != 'declared_endpoints_valid'
                assert broken['status'] == 'needs_clarification'
                print('Proposal:', proposal.get('status'), 'Missing:', missing['relationships'][0]['status'], 'Stale:', stale, 'Broken:', broken['relationships'][0]['status'])
        assert hashes(FIXTURE) == before, 'original fixture mutated'
    print(f'Passed {len(events)} MCP protocol events without writing a transcript.')

if __name__ == '__main__':
    asyncio.run(main())
