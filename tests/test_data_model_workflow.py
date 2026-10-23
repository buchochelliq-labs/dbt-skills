"""Acceptance support for the published metadata-only multi-entity fixture."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from mcp import Client, MCPError, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


class DataModelWorkflowTests(unittest.TestCase):
    def test_published_fixture_through_real_stdio(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            shutil.copytree(ROOT / 'examples/data-model-workflow', project)
            request = json.loads((project / 'design-request.json').read_text())
            before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
            params = StdioServerParameters(command=sys.executable,
                args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(project),
                      '--target-path', 'artifacts', '--policy', 'modelling.yml',
                      '--catalog-config', 'catalogs.json'],
                env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')))

            async def exercise():
                async with Client(params, read_timeout_seconds=20) as client:
                    async def call(name, args):
                        return (await client.call_tool(name, args)).structured_content
                    key = (await call('modelling_context', {}))['context_id']
                    result = await call('model_plan', {'context_id': key, 'request': request})
                    self.assertEqual(len(result['entities']), 2)
                    self.assertEqual(result['status'], 'needs_clarification')
                    self.assertEqual(len(result['relationships']), 1)
                    relation = result['relationships'][0]
                    self.assertEqual(relation['status'], 'declared_endpoints_valid')
                    self.assertEqual(relation['target_key'], 'matches_declared_primary_key')
                    self.assertEqual(relation['cardinality'], 'unverified')
                    for entity in result['entities']:
                        self.assertEqual(entity['normal_form_status'], 'unverified')
                        self.assertEqual(entity['grain']['provenance']['provider'], 'curated')
                    self.assertIn('confirm_relationship', {q['code'] for q in result['questions']})
                    self.assertIn('functional_dependencies', {q['code'] for q in result['questions']})
                    for concept in ('customer', 'order'):
                        rendered = await call('modelling_render', {'context_id': key,
                            'rule_id': 'staging_file', 'values': {'system': 'xyz', 'concept': concept}})
                        self.assertEqual(rendered['value'], f'models/staging/stg_xyz_{concept}.sql')
                    comparison = await call('modelling_compare', {'context_id': key,
                        'model_id': 'model.catalog_workflow.stg_xyz_customer',
                        'scope': {'directory': 'models/staging'}})
                    self.assertEqual(comparison['models'][0]['status'], 'mismatch')
                    proposal = await call('modelling_propose', {'context_id': key,
                        'rule_id': 'staging_file', 'model_id': 'model.catalog_workflow.stg_xyz_customer',
                        'rationale': 'Retain the customer filename for compatibility; one-model review only.'})
                    self.assertEqual(proposal['status'], 'pending_review')
                    self.assertEqual(proposal['proposal_document']['records'][0]['models'],
                                     ['model.catalog_workflow.stg_xyz_customer'])
                    self.assertEqual(before, {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()})
                    # An unselected target must remain a question, not a hidden fetch.
                    orders_only = dict(request, assets=[request['assets'][1]])
                    missing = await call('model_plan', {'context_id': key, 'request': orders_only})
                    self.assertEqual(len(missing['evidence']), 1)
                    self.assertIn('select_relationship_target', {q['code'] for q in missing['questions']})
                    # Human changes the selected metadata; refresh must invalidate the old context.
                    path = project / 'curated.json'
                    curated = json.loads(path.read_text())
                    curated['assets'][1]['facts']['foreign_keys'][0]['target_columns'] = ['missing_customer_key']
                    path.write_text(json.dumps(curated))
                    refreshed = await call('modelling_refresh', {})
                    new_key = refreshed['context_id']
                    self.assertNotEqual(new_key, key)
                    with self.assertRaises(MCPError):
                        await call('model_plan', {'context_id': key, 'request': request})
                    changed = await call('model_plan', {'context_id': new_key, 'request': request})
                    self.assertIn('relationship_columns_missing', {q['code'] for q in changed['questions']})
                    self.assertNotIn('review_separate_entities', {s['code'] for s in changed['suggestions']})
            asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
