import copy
import json
import unittest
from unittest.mock import patch

import test_model_drafts
from dbt_skills.catalog import load_catalog
from dbt_skills.model_drafts import apply_draft, DraftError
from dbt_skills.model_validation import validate_applied
from dbt_skills.model_revisions import prepare_revision, apply_revision


class ModelRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.project = self.fixture.root, self.fixture.project
        self.base = self.fixture.draft()
        apply_draft(self.project, self.base, self.base['draft_id'])
        self.request = copy.deepcopy(self.fixture.request)
        self.request['columns'].append('updated_at')

    def prepare(self, base=None):
        return prepare_revision(self.project, self.root/'modelling.yml', load_catalog(self.root/'catalogs.json'), base or self.base, self.request)

    def test_proposal_is_read_only_and_apply_validates(self):
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        revision = self.prepare()
        self.assertEqual(revision['status'],'pending_review')
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertTrue(all(f['operation']=='replace' for f in revision['files']))
        self.assertIn('+',revision['files'][0]['diff'])
        with self.assertRaises(DraftError):
            apply_revision(self.project,revision,'wrong')
        self.assertEqual(apply_revision(self.project,revision,revision['revision_id'])['status'],'replaced')
        self.assertEqual(validate_applied(self.project,revision['proposed'])['status'],'passed')
        self.assertEqual(validate_applied(self.project,self.base)['status'],'failed')
        with self.assertRaises(DraftError):
            apply_revision(self.project,revision,revision['revision_id'])
        self.request['columns'].remove('customer_name')
        second = self.prepare(revision['proposed'])
        self.assertEqual(second['status'],'pending_review')
        apply_revision(self.project,second,second['revision_id'])
        self.assertEqual(validate_applied(self.project,second['proposed'])['status'],'passed')

    def test_changed_files_and_inputs_block_without_overwrite(self):
        revision = self.prepare()
        path = self.root/self.base['files'][0]['path']
        path.write_text(path.read_text()+'\n-- manual edit\n')
        with self.assertRaises(DraftError):
            self.prepare()
        with self.assertRaises(DraftError):
            apply_revision(self.project,revision,revision['revision_id'])
        self.assertIn('manual edit',path.read_text())

    def test_renames_and_noop_do_not_propose_replacement(self):
        self.request = copy.deepcopy(self.fixture.request)
        self.assertEqual(self.prepare()['status'],'needs_clarification')
        self.request['values']['concept'] = 'other'
        self.assertEqual(self.prepare()['status'],'needs_clarification')

    def test_second_replace_failure_restores_first(self):
        import os
        revision = self.prepare()
        before = [(self.root/f['path']).read_bytes() for f in self.base['files']]
        replace = os.replace
        calls = 0
        def fail_second(source,target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('PRIVATE_SENTINEL')
            return replace(source,target)
        with patch('dbt_skills.model_revisions.os.replace',side_effect=fail_second):
            with self.assertRaises(DraftError) as caught:
                apply_revision(self.project,revision,revision['revision_id'])
        self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
        self.assertEqual(before,[(self.root/f['path']).read_bytes() for f in self.base['files']])
        self.assertEqual(validate_applied(self.project,self.base)['status'],'passed')

    def test_postvalidation_failure_restores_both_files_and_modes(self):
        import stat
        revision = self.prepare()
        paths = [self.root / f['path'] for f in self.base['files']]
        paths[0].chmod(0o640)
        modes = [stat.S_IMODE(p.stat().st_mode) for p in paths]
        before = [p.read_bytes() for p in paths]
        def fail_after_replace(project, draft):
            if draft is revision['proposed'] and paths[0].read_text() == draft['files'][0]['content']:
                return {'status': 'failed', 'checks': []}
            return validate_applied(project, draft)
        with patch('dbt_skills.model_revisions.validate_applied', side_effect=fail_after_replace):
            with self.assertRaisesRegex(DraftError, 'replaced files restored'):
                apply_revision(self.project, revision, revision['revision_id'])
        self.assertEqual([p.read_bytes() for p in paths], before)
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in paths], modes)
        apply_revision(self.project, revision, revision['revision_id'])
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in paths], modes)

    def test_tampered_revision_cannot_write(self):
        revision = self.prepare()
        revision['proposed']['files'][0]['content'] += '\n-- changed\n'
        with self.assertRaises(DraftError):
            apply_revision(self.project, revision, revision['revision_id'])
        self.assertEqual(validate_applied(self.project, self.base)['status'], 'passed')

    def test_rollback_preserves_independently_changed_output(self):
        import os
        revision = self.prepare()
        first = self.root / self.base['files'][0]['path']
        replace = os.replace
        calls = 0
        def change_after_first(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                first.write_text('independent edit')
                raise OSError('PRIVATE_SENTINEL')
            return replace(source, target)
        with patch('dbt_skills.model_revisions.os.replace', side_effect=change_after_first):
            with self.assertRaisesRegex(DraftError, 'rollback incomplete'):
                apply_revision(self.project, revision, revision['revision_id'])
        self.assertEqual(first.read_text(), 'independent edit')
        second = self.base['files'][1]
        self.assertEqual((self.root / second['path']).read_text(), second['content'])

    def test_changed_evidence_blocks_revision(self):
        revision = self.prepare()
        path=self.root/'physical.json'
        path.write_text(path.read_text()+'\n')
        with self.assertRaises(DraftError):
            apply_revision(self.project,revision,revision['revision_id'])
        self.assertEqual((self.root/self.base['files'][0]['path']).read_text(),self.base['files'][0]['content'])

    def test_symlink_target_is_rejected(self):
        revision = self.prepare()
        path=self.root/self.base['files'][0]['path']
        other=self.root/'other.sql'; other.write_text(path.read_text())
        path.unlink()
        try:
            path.symlink_to(other)
        except OSError:
            self.skipTest('symlink creation unavailable')
        with self.assertRaises(DraftError):
            apply_revision(self.project,revision,revision['revision_id'])
        self.assertEqual(other.read_text(),self.base['files'][0]['content'])

    def test_cli_prepare_and_apply_revision(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        (self.root/'base.json').write_text(json.dumps(self.base))
        (self.root/'request.json').write_text(json.dumps(self.request))
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        prefix=[sys.executable,'-m','dbt_skills.model_revisions']
        result=subprocess.run(prefix+['prepare','--project-dir',str(self.root),'--base-draft','base.json','--request','request.json','--policy','modelling.yml','--catalog-config','catalogs.json'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(result.stdout)
        revision=json.loads(result.stdout)
        (self.root/'revision.json').write_text(json.dumps(revision))
        result=subprocess.run(prefix+['apply','--project-dir',str(self.root),'--revision','revision.json','--approve',revision['revision_id']],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'replaced')

    def test_stdio_revises_only_retained_drafts_and_validates_proposed(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        # Start from an empty output pair so the server can retain the original draft.
        for file in self.base['files']:
            (self.root/file['path']).unlink()
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--policy','modelling.yml','--catalog-config','catalogs.json'],env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
            async with Client(params,read_timeout_seconds=20) as client:
                key=(await client.call_tool('modelling_context',{})).structured_content['context_id']
                base=(await client.call_tool('model_draft',{'context_id':key,'request':self.fixture.request})).structured_content
                apply_draft(self.project,base,base['draft_id'])
                tools={t.name:t for t in (await client.list_tools()).tools}
                self.assertIn('model_revise',tools)
                self.assertTrue(tools['model_revise'].annotations.read_only_hint)
                with self.assertRaises(MCPError):
                    await client.call_tool('model_revise',{'context_id':key,'draft_id':'unknown','request':self.request})
                revision=(await client.call_tool('model_revise',{'context_id':key,'draft_id':base['draft_id'],'request':self.request})).structured_content
                self.assertEqual(revision['status'],'pending_review')
                self.assertEqual(validate_applied(self.project,base)['status'],'passed')
                apply_revision(self.project,revision,revision['revision_id'])
                result=(await client.call_tool('model_validate',{'context_id':key,'draft_id':revision['proposed']['draft_id']})).structured_content
                self.assertEqual(result['status'],'passed')
        asyncio.run(exercise())
