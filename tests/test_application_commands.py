"""Independent acceptance tests through the persisted application contract."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.application_api import OntologyApplication
from dbt_skills.application_store import ApplicationStore, ApplicationConflict
from dbt_skills.workspace_service import Application
from dbt_skills.workspace_store import WorkspaceError
from tests.cache_test_support import MemoryKeyStore

FIXTURE = Path(__file__).parents[1] / 'examples/uol-workspace/fixture.json'


class ApplicationCommandsAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'application.db'
        self.keys = MemoryKeyStore()
        self.initial = json.loads(FIXTURE.read_text())
        self.store = ApplicationStore(self.path, key_store=self.keys, initial_state=self.initial, simulation=True)
        self.app = OntologyApplication(self.store)
        self.http = Application(None, None, self.app)

    def command(self, name, payload=None, reader=None):
        return self.http.dispatch('/api/application/command', dict(name=name, payload=payload or {}, reader=reader,
            expected_revision=self.store.read()['revision']))

    def find(self, collection, identifier):
        return next(x for x in self.store.read()['state'][collection] if x['id'] == identifier)

    def test_domain_identity_cycles_and_atomic_rollback(self):
        original = self.find('domains', 'customer')
        self.command('domain.update', {'id':'customer', 'patch':{'name':'Customer organisation'}})
        self.assertEqual(self.find('domains','customer')['id'], original['id'])
        before = self.store.read()
        with self.assertRaises(WorkspaceError):
            self.command('domain.update', {'id':'customer','patch':{'parent':'onboarding'}})
        self.assertEqual(self.store.read(), before)
        with self.assertRaises(WorkspaceError):
            self.command('domain.update', {'id':'enterprise','patch':{'parent':'customer'}})
        created = self.command('domain.create', {'name':'Research','parent':'customer'})['result']
        self.assertEqual(created['parent'], 'customer')
        with self.assertRaises(WorkspaceError):
            self.command('domain.create', {'name':'research','parent':'customer'})

    def test_memberships_revision_approval_and_immutable_origin(self):
        original = self.find('knowledge','active-customer')
        self.command('knowledge.revise', {'id':original['id'],'patch':{'definition':'Reviewed replacement','memberships':['finance']}})
        edited = self.find('knowledge', original['id'])
        self.assertEqual(edited['status'], 'Draft')
        self.assertEqual(edited['version'], original['version']+1)
        self.assertEqual(edited['originId'], original['originId'])
        self.assertEqual(edited['history'][-1]['definition'], original['definition'])
        before = self.store.read()
        for patch in ({'memberships':[edited['domain']]}, {'memberships':['finance','finance']}, {'originId':'forged'}):
            with self.assertRaises(WorkspaceError):
                self.command('knowledge.revise', {'id':original['id'],'patch':patch})
            self.assertEqual(self.store.read(), before)
        self.command('knowledge.approve', {'id':original['id']})
        self.assertEqual(self.find('knowledge',original['id'])['status'],'Approved')

    def test_context_privacy_scopes_and_authored_cache_durability(self):
        def query(identifier, scope='Service', reader='steward'):
            return self.command('context.resolve',{'request':{'objectId':identifier,'scope':scope}},reader)['result']
        self.assertEqual(query('private-concept'), query('nonexistent'))
        self.assertEqual(query('mrr','incorrect','restricted')['state'], 'denied')
        self.assertEqual(query('active-customer','incorrect')['state'], 'scopeMismatch')
        self.assertEqual(query('active-customer')['state'], 'sufficient')
        result = query('customer-entity','Enterprise')
        self.assertEqual(result['state'],'sufficient')
        self.assertEqual(result['facts'][0]['evidence']['assetId'],'')
        self.assertTrue(result['facts'][0]['evidence']['sourcePath'])
        reopened = OntologyApplication(ApplicationStore(self.path,key_store=self.keys))
        self.assertTrue(reopened.read()['simulation'])
        self.assertEqual(reopened.store.read(),self.store.read())

    def test_page_save_preserves_full_content(self):
        page = deepcopy(self.find('pages','lifecycle-page'))
        page.update(body='## Lifecycle\n\nIndependent authored body.',summary='Acceptance edit',synonyms=['Lifecycle reference'])
        result = self.command('page.save',{'page':page})['result']
        self.assertEqual(result,page)
        self.assertEqual(self.find('pages',page['id']),page)
        page['relatedAssets'] = ['hidden-asset']
        with self.assertRaises(WorkspaceError):self.command('page.save',{'page':page})

    def proposal(self, text, target='customers'):
        p = self.command('proposal.create',{'proposal':dict(originId='active-customer',targetId=target,field='description',after=text,reason='Independent acceptance review')})['result']
        self.command('proposal.review',{'id':p['id']})
        return p['id']

    def test_selected_publication_and_conflict_do_not_write_other_items(self):
        first = self.proposal('Selected description')
        second = self.proposal('Unselected description','accounts')
        before_second = deepcopy(self.find('targets','accounts'))
        result = self.command('proposal.deliver',{'ids':[first]})['result']
        self.assertEqual(result[0]['state'],'Verified')
        self.assertEqual(self.find('targets','customers')['content']['description'],'Selected description')
        self.assertEqual(self.find('targets','accounts'),before_second)
        self.assertEqual(self.find('proposals',second)['state'],'Reviewed')
        self.command('target.simulate',{'id':'accounts','scenario':'drift'})
        before = deepcopy(self.find('targets','accounts'))
        self.command('proposal.deliver',{'ids':[second]})
        self.assertEqual(self.find('proposals',second)['state'],'Conflict')
        self.assertEqual(self.find('targets','accounts'),before)
        self.assertFalse(self.store.read()['state']['deliveries'][-1]['acknowledged'])

    def test_export_import_preview_restart_and_staleness(self):
        self.command('domain.update',{'id':'customer','patch':{'description':'Durable independent edit'}})
        envelope = self.command('workspace.export')['result']
        preview = self.command('workspace.import.preview',{'envelope':envelope})['result']
        self.assertEqual(self.find('domains','customer')['description'],'Durable independent edit')
        self.assertTrue(preview['diff']['security_resets'])
        self.command('workspace.import.apply',{'previewId':preview['preview_id']})
        restarted = ApplicationStore(self.path,key_store=self.keys)
        self.assertEqual(restarted.read(),self.store.read())
        self.assertTrue(all(not p['enabled'] for p in restarted.read()['state']['providers']))
        self.assertTrue(all(a['hidden'] for a in restarted.read()['state']['assets']))
        next_preview = self.command('workspace.import.preview',{'envelope':envelope})['result']
        self.command('ttl.dismiss')
        with self.assertRaises(ApplicationConflict):
            self.command('workspace.import.apply',{'previewId':next_preview['preview_id']})

    def test_restricted_reader_cannot_mutate(self):
        before = self.store.read()
        with self.assertRaises(WorkspaceError):
            self.command('domain.update',{'id':'customer','patch':{'name':'forged'}},'restricted')
        self.assertEqual(self.store.read(),before)

    def test_live_reader_identity_cannot_be_overridden_by_payload(self):
        live = ApplicationStore(Path(self.tmp.name)/'live.db',key_store=self.keys,initial_state=self.initial,simulation=False)
        app = OntologyApplication(live,reader='restricted')
        self.assertEqual(app.read('steward')['reader'],'restricted')
        with self.assertRaises(WorkspaceError):
            app.command('domain.update',{'id':'customer','patch':{'name':'Escalated'}},expected_revision=0,reader='steward')
        result = app.command('context.resolve',{'request':{'objectId':'mrr','scope':'Billing','reader':'steward'}},expected_revision=0,reader='steward')
        self.assertEqual(result['result']['state'],'denied')
        self.assertFalse(result['simulation'])

    def test_live_source_requires_backend_and_simulation_controls_rejected(self):
        live = ApplicationStore(Path(self.tmp.name)/'live.db',key_store=self.keys,initial_state=self.initial,simulation=False)
        app = OntologyApplication(live)
        result = app.command('context.resolve',{'request':{'objectId':'active-customers','scope':'Service'}},expected_revision=0)
        self.assertEqual(result['result']['state'],'error')
        self.assertEqual(result['result']['facts'],[])
        for name,payload in [('clock.advance',{'hours':1}),('target.simulate',{'id':'customers','scenario':'drift'}),('workspace.reset',{})]:
            with self.assertRaises(WorkspaceError):app.command(name,payload,expected_revision=live.read()['revision'])

    def test_model_plan_context_uses_canonical_permission_and_validity_gate(self):
        class Bridge:
            status = 'complete'
            def preferences(self, providers): pass
            def call(self, name, args):
                if name == 'model_plan': return {'plan':'metadata only'}
                if name == 'modelling_context': return {'context_id':'test'}
                if name == 'catalog_resolve':
                    if self.status != 'complete': return {'status':self.status}
                    provenance = dict(provider='uc-customer',revision='a'*64,document='metadata.json',locator='/assets/0',retrieved_at='2026-10-24T00:00:00Z')
                    return {'status':'complete','selected':{'relation':{'value':{},'provenance':provenance},'columns':{'value':[{'name':'active_customers'}],'provenance':provenance}}}
                raise AssertionError(name)
        bridge = Bridge()
        store = ApplicationStore(Path(self.tmp.name)/'model.db',key_store=self.keys,initial_state=self.initial,simulation=False)
        app = OntologyApplication(store,bridge=bridge)
        args = {'request':{'assets':[{'asset_id':'active-view'}]}}
        result = app.agent_context('model_plan',args)
        self.assertEqual([k['id'] for k in result['ontology_context']],['active-customers'])
        self.assertEqual(result['ontology_context'][0]['facts'][0]['evidence']['providerId'],'uc-customer')
        bridge.status = 'denied'
        self.assertEqual(app.agent_context('model_plan',args)['ontology_context'],[])
        bridge.status = 'complete'
        def update(**patch):
            store.transact(store.read()['revision'],lambda s:next(k for k in s['knowledge'] if k['id']=='active-customers').update(patch))
        update(validTo='2020-01-01')
        self.assertEqual(app.agent_context('model_plan',args)['ontology_context'],[])
        update(validTo='2099-01-01',hidden=True)
        self.assertEqual(app.agent_context('model_plan',args)['ontology_context'],[])
        update(hidden=False,status='Draft')
        self.assertEqual(app.agent_context('model_plan',args)['ontology_context'],[])
