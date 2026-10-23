import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import test_model_drafts
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied, run_parse


class ModelValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.project = self.fixture.root, self.fixture.project
        self.draft = self.fixture.draft()

    def test_reports_missing_changed_and_exact_files_without_content(self):
        self.assertEqual(validate_applied(self.project, self.draft)['status'], 'failed')
        apply_draft(self.project, self.draft, self.draft['draft_id'])
        report = validate_applied(self.project, self.draft)
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['warehouse_validated'])
        (self.root / self.draft['files'][0]['path']).write_text('PRIVATE_SENTINEL')
        report = validate_applied(self.project, self.draft)
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
        self.assertNotIn('customer_id', json.dumps(report))

    def test_stale_catalog_and_tampered_envelope_are_not_valid(self):
        apply_draft(self.project, self.draft, self.draft['draft_id'])
        self.fixture.manifest.write_text('{}')
        report = validate_applied(self.project, self.draft)
        self.assertEqual(report['status'], 'failed')
        self.assertIn({'check': 'input_revisions', 'status': 'failed'}, report['checks'])
        tampered = copy.deepcopy(self.draft)
        tampered['files'][0]['content'] = 'select PRIVATE_SENTINEL'
        self.assertEqual(validate_applied(self.project, tampered)['status'], 'failed')

    def test_resealed_arbitrary_sql_fails_projection_contract(self):
        altered = copy.deepcopy(self.draft)
        altered['files'][0]['content'] = "{{ run_query('select PRIVATE_SENTINEL') }}"
        altered['draft_id'] = _digest({k: v for k, v in altered.items() if k != 'draft_id'})
        apply_draft(self.project, altered, altered['draft_id'])
        report = validate_applied(self.project, altered)
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))

    def fake_parse(self, exit_code=0, delay=0):
        # Python runs the file named 'parse' as its script, accepting the runner's
        # fixed remaining argv. This exercises real subprocess I/O on every OS.
        (self.root / 'parse').write_text("import sys,time\nprint('PRIVATE_SENTINEL')\nprint('PRIVATE_SENTINEL', file=sys.stderr)\ntime.sleep(" + str(delay) + ")\nsys.exit(" + str(exit_code) + ")\n")
        profiles = self.root / 'profiles'
        profiles.mkdir(exist_ok=True)
        return profiles

    def test_operator_parse_success_failure_and_timeout_are_output_safe(self):
        apply_draft(self.project, self.draft, self.draft['draft_id'])
        for code, delay, expected in [(0, 0, 'passed'), (2, 0, 'failed'), (0, 2, 'timeout')]:
            profiles = self.fake_parse(code, delay)
            report = run_parse(self.project, self.draft, self.draft['draft_id'], executable=sys.executable, profiles_dir=profiles, timeout=1)
            self.assertEqual(report['status'], expected)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
            self.assertFalse(report['warehouse_validated'])

    def test_no_execution_without_approval_and_local_checks(self):
        profiles = self.fake_parse()
        report = run_parse(self.project, self.draft, 'wrong', executable=sys.executable, profiles_dir=profiles)
        self.assertEqual(report['status'], 'blocked')
        report = run_parse(self.project, self.draft, self.draft['draft_id'], executable=sys.executable, profiles_dir=profiles)
        self.assertEqual(report['status'], 'blocked')

    def test_mcp_validates_only_retained_ids_and_refresh_invalidates(self):
        import asyncio
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id': key, 'request': self.fixture.request})).structured_content
                args = {'context_id': key, 'draft_id': draft['draft_id']}
                self.assertEqual((await client.call_tool('model_validate', args)).structured_content['status'], 'failed')
                apply_draft(self.project, draft, draft['draft_id'])
                self.assertEqual((await client.call_tool('model_validate', args)).structured_content['status'], 'passed')
                with self.assertRaises(MCPError):
                    await client.call_tool('model_validate', {**args, 'draft_id': 'unknown'})
                new = (await client.call_tool('modelling_refresh', {})).structured_content['context_id']
                for context in (key, new):
                    with self.assertRaises(MCPError):
                        await client.call_tool('model_validate', {**args, 'context_id': context})
        asyncio.run(exercise())

    @unittest.skipUnless(os.environ.get('DBT_SKILLS_REAL_DBT'), 'optional isolated dbt executable required')
    def test_real_dbt_parse_and_invalid_project(self):
        (self.root / 'models').mkdir()
        (self.root / 'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n')
        apply_draft(self.project, self.draft, self.draft['draft_id'])
        profiles = self.root / 'profiles'
        profiles.mkdir()
        (profiles / 'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        kwargs = dict(executable=os.environ['DBT_SKILLS_REAL_DBT'], profiles_dir=profiles)
        self.assertEqual(run_parse(self.project, self.draft, self.draft['draft_id'], **kwargs)['status'], 'passed')
        (self.root / 'models/sources.yml').write_text('version: [PRIVATE_SENTINEL')
        report = run_parse(self.project, self.draft, self.draft['draft_id'], **kwargs)
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))

    def test_cli_check_and_parse_return_fixed_reports(self):
        import subprocess
        apply_draft(self.project, self.draft, self.draft['draft_id'])
        path = self.root / 'draft.json'
        path.write_text(json.dumps(self.draft))
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        prefix = [sys.executable, '-m', 'dbt_skills.model_validation']
        common = ['--project-dir', str(self.root), '--draft', str(path)]
        profiles = self.fake_parse()
        for command in [['check'], ['parse', '--approve', self.draft['draft_id'], '--dbt-executable', sys.executable, '--profiles-dir', str(profiles)]]:
            result = subprocess.run(prefix + command + common, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'passed')
            self.assertNotIn('PRIVATE_SENTINEL', result.stdout + result.stderr)
