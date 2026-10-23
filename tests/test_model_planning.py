import copy
import json
from pathlib import Path
import unittest
import yaml

import metadata_fixture
from dbt_skills.catalog import load_catalog
from dbt_skills.modelling_policy import load_document
from dbt_skills.project_artifacts import inspect_artifacts
from dbt_skills.model_planning import plan_model, PlanningError


class ModelPlanningTests(unittest.TestCase):
    def setUp(self):
        self.fixture = metadata_fixture.MetadataFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.request = {'intent': 'Model customers and their orders', 'assets': [{'asset_id': 'urn:demo:xyz:customers'}]}

    def plan(self, request=None):
        return plan_model(self.fixture.project, load_document(self.root / 'modelling.yml'),
                          load_catalog(self.root / 'catalogs.json'), request or self.request,
                          snapshot=inspect_artifacts(self.fixture.project))

    def codes(self, plan):
        return {q['code'] for q in plan['questions']}

    def test_candidates_keep_provenance_and_ask_for_unproven_design(self):
        before = set(self.root.rglob('*'))
        result = self.plan()
        self.assertEqual(result['status'], 'needs_clarification')
        candidate = result['entities'][0]
        self.assertEqual(candidate['grain']['suggested'], ['customer_id'])
        self.assertEqual(candidate['grain']['basis'], 'catalog_declaration')
        self.assertEqual(candidate['grain']['provenance']['provider'], 'curated')
        self.assertEqual(candidate['normal_form_status'], 'unverified')
        self.assertTrue({'confirm_grain', 'choose_history', 'functional_dependencies', 'relationships_unknown'} <= self.codes(result))
        self.assertEqual(candidate['source_candidates'], ['source.catalog_workflow.xyz.customers'])
        self.assertEqual(set(self.root.rglob('*')), before)
        self.assertNotIn('files', result)

    def test_asserted_grain_is_checked_but_never_proven(self):
        self.request['assets'][0].update(grain=['customer_id'], history='current')
        result = self.plan()
        grain = result['entities'][0]['grain']
        self.assertEqual(grain['basis'], 'caller_assertion')
        self.assertFalse(grain['verified'])
        self.assertNotIn('confirm_grain', self.codes(result))
        self.assertIn('current_row_rule', self.codes(result))
        self.request['assets'][0]['grain'] = ['missing']
        self.assertIn('grain_columns_missing', self.codes(self.plan()))

    def test_scope_unknown_conflicting_rules_and_4nf(self):
        path = self.root / 'modelling.yml'
        doc = yaml.safe_load(path.read_text())
        doc['modelling'] = [{'id': 'core', 'scope': {'layer': 'core'}, 'style': 'relational', 'normal_form': '4NF'},
                            {'id': 'other', 'scope': {'layer': 'core'}, 'style': 'relational', 'normal_form': '3NF'}]
        path.write_text(yaml.safe_dump(doc))
        result = self.plan()
        self.assertIn('modelling_scope', self.codes(result))
        self.assertEqual(result['entities'][0]['standards'], [])
        self.request['assets'][0]['scope'] = {'layer': 'core'}
        result = self.plan()
        self.assertTrue({'standards_conflict', 'multivalued_dependencies'} <= self.codes(result))
        self.assertEqual(len(result['entities'][0]['standards']), 2)

    def add_orders(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        order = {'id': 'urn:demo:xyz:orders', 'native_id': 'demo.xyz.orders', 'facts': {
            'relation': {'catalog': 'demo', 'schema': 'xyz', 'name': 'orders'},
            'columns': [{'name': 'order_id', 'type': 'int64', 'nullable': False}, {'name': 'customer_id', 'type': 'int64', 'nullable': False}],
            'primary_key': {'columns': ['order_id'], 'enforcement': 'not_enforced', 'rely': False},
            'foreign_keys': [{'columns': ['customer_id'], 'target_asset': 'urn:demo:xyz:customers', 'target_columns': ['customer_id'], 'enforcement': 'not_enforced', 'rely': False}]}}
        manifest = json.loads(self.fixture.manifest.read_text())
        manifest['sources']['source.catalog_workflow.xyz.orders'] = {'resource_type': 'source',
            'package_name': 'catalog_workflow', 'database': 'demo', 'schema': 'xyz', 'identifier': 'orders'}
        self.fixture.manifest.write_text(json.dumps(manifest))
        doc['assets'].append(order)
        path.write_text(json.dumps(doc))
        return path, doc

    def test_relationships_suggest_entities_without_claiming_join_safety(self):
        self.add_orders()
        self.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        result = self.plan()
        relation = result['relationships'][0]
        self.assertEqual(relation['status'], 'declared_endpoints_valid')
        self.assertEqual(relation['target_key'], 'matches_declared_primary_key')
        self.assertEqual(relation['cardinality'], 'unverified')
        self.assertIn('review_separate_entities', {s['code'] for s in result['suggestions']})
        self.assertIn('confirm_relationship', self.codes(result))

    def test_unselected_targets_are_not_fetched_and_bad_endpoints_are_questions(self):
        path, doc = self.add_orders()
        self.request['assets'] = [{'asset_id': 'urn:demo:xyz:orders'}]
        result = self.plan()
        self.assertEqual(len(result['evidence']), 1)
        self.assertIn('select_relationship_target', self.codes(result))
        self.request['assets'].append({'asset_id': 'urn:demo:xyz:customers'})
        doc['assets'][1]['facts']['foreign_keys'][0]['target_columns'] = ['missing']
        path.write_text(json.dumps(doc))
        result = self.plan()
        self.assertIn('relationship_columns_missing', self.codes(result))
        self.assertNotIn('review_separate_entities', {s['code'] for s in result['suggestions']})

    def test_existing_downstream_models_are_review_candidates_not_zero_impact_claim(self):
        doc = json.loads(self.fixture.manifest.read_text())
        doc['nodes']['model.catalog_workflow.customers'] = {'resource_type': 'model', 'name': 'customers', 'package_name': 'catalog_workflow', 'depends_on': {'nodes': ['source.catalog_workflow.xyz.customers']}}
        self.fixture.manifest.write_text(json.dumps(doc))
        result = self.plan()
        self.assertEqual(result['entities'][0]['existing_models'], ['model.catalog_workflow.customers'])
        self.assertIn('review_existing_models', {s['code'] for s in result['suggestions']})
        self.assertFalse(result['impact_complete'])

    def test_invalid_requests_fail_with_static_errors(self):
        for request in [{'intent': 'x', 'assets': []}, {'intent': 'x', 'assets': self.request['assets'] * 9},
                        {'intent': 'x', 'assets': [{'asset_id': 'PRIVATE_SENTINEL\n'}]},
                        {'intent': 'x', 'assets': [{'asset_id': 'urn:demo:xyz:customers', 'extra': 'PRIVATE_SENTINEL'}]}]:
            with self.assertRaises(PlanningError) as caught:
                self.plan(request)
            self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))

    def test_denial_withholds_prior_asset_evidence(self):
        from dbt_skills.catalog import CatalogResolver, FileCatalogProvider, ProviderResult
        self.add_orders()
        file_provider = FileCatalogProvider('physical', self.root / 'physical.json', 'local')
        # First provider resolves customers fully; second asset is denied after
        # successful collection of the first asset's metadata.
        class GuardedProvider:
            id = 'physical'
            def project_bindings(self):
                return file_provider.project_bindings()
            def fetch(self, asset_id, fields):
                return ProviderResult('denied') if asset_id.endswith('orders') else file_provider.fetch(asset_id, fields)
        self.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        result = plan_model(self.fixture.project, load_document(self.root / 'modelling.yml'), CatalogResolver([GuardedProvider()]), self.request)
        self.assertEqual(result['status'], 'blocked')
        for field in ('evidence', 'entities', 'relationships', 'suggestions'):
            self.assertFalse(result[field])
        self.assertNotIn('customer_name', json.dumps(result))

    def test_conflicting_catalog_claims_block_design_suggestions(self):
        path = self.root / 'curated.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['relation'] = {'catalog': 'other', 'schema': 'xyz', 'name': 'customers'}
        path.write_text(json.dumps(doc))
        result = self.plan()
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['entities'])
        self.assertFalse(result['suggestions'])
        self.assertEqual(result['evidence'], {})

    def test_mcp_plan_uses_context_and_rejects_policy_changes(self):
        import asyncio
        import os
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                result = (await client.call_tool('model_plan', {'context_id': key, 'request': self.request})).structured_content
                self.assertEqual(result['context_id'], key)
                self.assertEqual(result['entities'][0]['grain']['suggested'], ['customer_id'])
                path = self.root / 'modelling.yml'
                path.write_text(path.read_text() + '\n# change\n')
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', {'context_id': key, 'request': self.request})
                await client.call_tool('modelling_refresh', {})
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', {'context_id': key, 'request': self.request})
        asyncio.run(exercise())

    def test_cli_returns_clarification_report(self):
        import os
        import subprocess
        import sys
        (self.root / 'plan.json').write_text(json.dumps(self.request))
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.model_planning', '--project-dir', str(self.root), '--request', 'plan.json', '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'],
                                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)['entities'][0]['normal_form_status'], 'unverified')

    def test_provider_errors_never_release_raw_details(self):
        from dbt_skills.catalog import CatalogResolver
        class BrokenProvider:
            id = 'broken'
            def project_bindings(self):
                return {'urn:demo:xyz:customers': {'relation': {'catalog': 'demo', 'schema': 'xyz', 'name': 'customers'}}}
            def fetch(self, asset_id, fields):
                raise RuntimeError('PRIVATE_SENTINEL')
        result = plan_model(self.fixture.project, load_document(self.root / 'modelling.yml'), CatalogResolver([BrokenProvider()]), self.request)
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_missing_snapshot_and_invalid_key_metadata_remain_questions(self):
        original_manifest = self.fixture.manifest.read_text()
        self.fixture.manifest.write_text('{}')
        self.assertIn('project_snapshot', self.codes(self.plan()))
        # Restore a valid snapshot independently of the key declaration.
        self.fixture.manifest.write_text(original_manifest)
        path = self.root / 'curated.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['primary_key']['columns'] = ['missing']
        path.write_text(json.dumps(doc))
        result = self.plan()
        self.assertIn('key_columns_missing', self.codes(result))
        self.assertEqual(result['entities'][0]['grain']['suggested'], [])

    def test_large_policy_report_fails_explicitly(self):
        path = self.root / 'modelling.yml'
        doc = yaml.safe_load(path.read_text())
        doc['modelling'] = [{'id': 'large', 'style': 'relational', 'normal_form': '3NF', 'principles': ['x' * 4096] * 180}]
        path.write_text(yaml.safe_dump(doc))
        self.add_orders()
        self.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        with self.assertRaisesRegex(PlanningError, 'response limit'):
            self.plan()
