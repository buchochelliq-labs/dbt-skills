import copy
import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.catalog import load_catalog
from dbt_skills.project import discover_project
from dbt_skills.project_artifacts import inspect_artifacts
from dbt_skills.model_drafts import prepare_model, apply_draft, DraftError


class ModelDraftTests(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        example = Path(__file__).resolve().parents[1] / 'examples' / 'catalog-workflow'
        for name in ('dbt_project.yml', 'modelling.yml', 'catalogs.json', 'physical.json', 'curated.json'):
            shutil.copyfile(example / name, self.root / name)
        policy = self.root / 'modelling.yml'
        import yaml
        doc = yaml.safe_load(policy.read_text())
        doc['naming'] = [r for r in doc['naming'] if r['target'] != 'properties_file']
        doc['naming'].append({'id': 'properties', 'target': 'properties_file', 'template': 'models/staging/{concept}.yml'})
        policy.write_text(yaml.safe_dump(doc))
        (self.root / 'target').mkdir()
        self.manifest = self.root / 'target/manifest.json'
        self.manifest.write_text(json.dumps({'metadata': {'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json', 'project_name': 'catalog_workflow'}, 'nodes': {}, 'sources': {
            'source.catalog_workflow.xyz.customers': {'resource_type': 'source', 'package_name': 'catalog_workflow', 'name': 'customers', 'source_name': 'xyz', 'identifier': 'customers', 'database': 'demo', 'schema': 'xyz'}}}))
        self.project = discover_project(self.root)
        self.catalog = load_catalog(self.root / 'catalogs.json')
        self.request = {'intent': 'Stage current customer records from XYZ', 'asset_id': 'urn:demo:xyz:customers',
            'source_id': 'source.catalog_workflow.xyz.customers', 'model_rule': 'staging_file', 'properties_rule': 'properties',
            'values': {'system': 'xyz', 'concept': 'customer'}, 'columns': ['customer_id', 'customer_name'],
            'grain': ['customer_id'], 'history': 'source_rows', 'scope': {}}

    def draft(self, request=None):
        return prepare_model(self.project, self.root / 'modelling.yml', self.catalog, request or self.request,
                             snapshot=inspect_artifacts(self.project))

    def test_projection_draft_preserves_evidence_and_never_writes(self):
        before = set(self.root.rglob('*'))
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertEqual(set(self.root.rglob('*')), before)
        self.assertEqual([f['path'] for f in draft['files']], ['models/staging/stg_xyz_customer.sql', 'models/staging/customer.yml'])
        self.assertIn("adapter.quote('customer_id')", draft['files'][0]['content'])
        self.assertIn("source('xyz', 'customers')", draft['files'][0]['content'])
        self.assertIn('unique', draft['files'][1]['content'])
        self.assertEqual(draft['catalog']['selected']['columns']['provenance']['provider'], 'physical')
        self.assertEqual(draft['design']['normal_form_status'], 'unverified')
        self.assertEqual(draft['validation']['executed'], [])

    def test_missing_design_and_naming_produce_questions(self):
        for key in ('intent', 'source_id', 'grain', 'history', 'columns'):
            request = copy.deepcopy(self.request)
            request.pop(key)
            draft = self.draft(request)
            self.assertEqual(draft['status'], 'needs_clarification', key)
            self.assertNotIn('files', draft)
        request = copy.deepcopy(self.request)
        request['values'] = {}
        self.assertEqual(self.draft(request)['status'], 'needs_clarification')

    def test_unknown_columns_wrong_mapping_and_history_do_not_generate(self):
        for key, value in [('columns', ['unknown']), ('grain', ['unknown']), ('history', 'scd2'), ('source_id', 'source.other')]:
            request = copy.deepcopy(self.request)
            request[key] = value
            self.assertNotEqual(self.draft(request)['status'], 'pending_review')
        doc = json.loads(self.manifest.read_text())
        doc['sources'][self.request['source_id']]['schema'] = 'different'
        self.manifest.write_text(json.dumps(doc))
        self.assertNotEqual(self.draft()['status'], 'pending_review')

    def test_apply_requires_exact_review_digest_and_creates_only(self):
        draft = self.draft()
        with self.assertRaises(DraftError):
            apply_draft(self.project, draft, 'wrong')
        result = apply_draft(self.project, draft, draft['draft_id'])
        self.assertEqual(result['status'], 'created')
        self.assertEqual((self.root / draft['files'][0]['path']).read_text(), draft['files'][0]['content'])
        with self.assertRaises(DraftError):
            apply_draft(self.project, draft, draft['draft_id'])

    def test_changed_inputs_and_tampered_content_block_application(self):
        draft = self.draft()
        modified = copy.deepcopy(draft)
        modified['files'][0]['content'] += '\nselect 1'
        with self.assertRaises(DraftError):
            apply_draft(self.project, modified, draft['draft_id'])
        self.manifest.write_text('{}')
        with self.assertRaises(DraftError):
            apply_draft(self.project, draft, draft['draft_id'])
        self.assertFalse((self.root / 'models').exists())

    def test_existing_target_blocks_generation(self):
        target = self.root / 'models/staging/customer.yml'
        target.parent.mkdir(parents=True)
        target.write_text('preserve')
        self.assertNotEqual(self.draft()['status'], 'pending_review')
        self.assertEqual(target.read_text(), 'preserve')

    def test_scope_overlap_and_wrong_scope_block_drafts(self):
        import yaml
        path = self.root / 'modelling.yml'
        doc = yaml.safe_load(path.read_text())
        doc['naming'][0]['scope']['domain'] = 'customer'
        path.write_text(yaml.safe_dump(doc))
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        request = dict(self.request, scope={'domain': 'customer'})
        self.assertEqual(self.draft(request)['status'], 'pending_review')
        duplicate = dict(copy.deepcopy(doc['naming'][0]), id='other_rule')
        doc['naming'].append(duplicate)
        path.write_text(yaml.safe_dump(doc))
        self.assertEqual(self.draft(request)['status'], 'needs_clarification')

    def test_symlink_and_traversal_paths_are_rejected(self):
        import yaml
        path = self.root / 'modelling.yml'
        doc = yaml.safe_load(path.read_text())
        doc['naming'][0]['template'] = '../stg_{concept}.sql'
        path.write_text(yaml.safe_dump(doc))
        with self.assertRaises(ValueError):
            self.draft()
        doc['naming'][0]['template'] = 'models/staging/stg_{concept}.sql'
        path.write_text(yaml.safe_dump(doc))
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            (self.root / 'models').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable')
        self.assertNotEqual(self.draft()['status'], 'pending_review')
        self.assertEqual(list(outside.iterdir()), [])

    def test_second_file_failure_rolls_back_first_without_overwriting(self):
        from unittest.mock import patch
        draft = self.draft()
        original = Path.open
        def fail_second(path, *args, **kwargs):
            if str(path).endswith('customer.yml') and args and args[0] == 'x':
                raise PermissionError('PRIVATE_SENTINEL')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', fail_second):
            with self.assertRaises(DraftError) as raised:
                apply_draft(self.project, draft, draft['draft_id'])
        self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))
        self.assertFalse((self.root / draft['files'][0]['path']).exists())

    def test_cli_approval_creates_reviewed_files_without_execution(self):
        import os
        import subprocess
        import sys
        draft = self.draft()
        path = self.root / 'draft.json'
        path.write_text(json.dumps(draft))
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.model_drafts', 'apply', '--project-dir', str(self.root), '--draft', str(path), '--approve', draft['draft_id']], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['validation_executed'], [])

    def test_mcp_returns_sealed_draft_and_rejects_changed_policy(self):
        import asyncio
        import os
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id': key, 'request': self.request})).structured_content
                self.assertEqual(draft['status'], 'pending_review')
                self.assertEqual(draft['context_id'], key)
                self.assertFalse((self.root / 'models').exists())
                policy = self.root / 'modelling.yml'
                policy.write_text(policy.read_text() + '\n# changed\n')
                with self.assertRaises(MCPError):
                    await client.call_tool('model_draft', {'context_id': key, 'request': self.request})
        asyncio.run(exercise())

    def test_large_supported_manifest_can_be_revalidated_on_apply(self):
        doc = json.loads(self.manifest.read_text())
        doc['ignored_payload'] = 'x' * (2 * 1024 * 1024)
        self.manifest.write_text(json.dumps(doc))
        draft = self.draft()
        self.assertEqual(apply_draft(self.project, draft, draft['draft_id'])['status'], 'created')

    def test_explicit_directory_scope_is_not_silently_overridden(self):
        request = dict(self.request, scope={'directory': 'models/other'})
        self.assertEqual(self.draft(request)['status'], 'needs_clarification')

    def test_generated_envelope_fits_the_cli_loader(self):
        import yaml
        path = self.root / 'modelling.yml'
        doc = yaml.safe_load(path.read_text())
        doc['modelling'][0]['principles'] = ['x' * 3000] * 230
        path.write_text(yaml.safe_dump(doc))
        with self.assertRaises(DraftError):
            self.draft()

    def test_cli_prepare_then_apply_round_trip(self):
        import os
        import subprocess
        import sys
        request_path = self.root / 'request.json'
        request_path.write_text(json.dumps(self.request))
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        prefix = [sys.executable, '-m', 'dbt_skills.model_drafts']
        prepared = subprocess.run(prefix + ['prepare', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json', '--request', str(request_path)], env=env, capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        draft = json.loads(prepared.stdout)
        self.assertEqual(draft['status'], 'pending_review')
        self.assertFalse((self.root / 'models').exists())
        path = self.root / 'draft.json'
        path.write_text(prepared.stdout)
        applied = subprocess.run(prefix + ['apply', '--project-dir', str(self.root), '--draft', str(path), '--approve', draft['draft_id']], env=env, capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)['status'], 'created')

    def test_negative_catalog_evidence_is_revalidated_before_apply(self):
        path = self.root / 'curated.json'
        doc = json.loads(path.read_text())
        doc['assets'] = []
        path.write_text(json.dumps(doc))
        self.catalog = load_catalog(self.root / 'catalogs.json')
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        doc['assets'] = [{'id': self.request['asset_id'], 'native_id': 'other', 'facts': {'relation': {'catalog': 'different', 'schema': 'xyz', 'name': 'customers'}}}]
        path.write_text(json.dumps(doc))
        with self.assertRaises(DraftError):
            apply_draft(self.project, draft, draft['draft_id'])
        self.assertFalse((self.root / 'models').exists())

    def test_unparsed_model_name_collisions_block_prepare_and_apply(self):
        draft = self.draft()
        other = self.root / 'models/other/stg_xyz_customer.sql'
        other.parent.mkdir(parents=True)
        other.write_text('select 1')
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        with self.assertRaises(DraftError):
            apply_draft(self.project, draft, draft['draft_id'])
        self.assertEqual(other.read_text(), 'select 1')
        self.assertFalse((self.root / 'models/staging').exists())
