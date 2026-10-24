from copy import deepcopy
import unittest

from dbt_skills.application_resolver import resolve_context


def state():
    return dict(clock=1792800000000, policyVersion=1, configVersion=1, domains=[], assets=[], mappings=[],
        providers=[dict(id='authored', kind='authored', enabled=True, health='healthy', ttl=24, scope=['*'])],
        cache=[], observations=[], knowledge=[dict(id='term', name='Customer', synonyms=[], scope='Research',
        grain='person', domain='research', type='Concept', definition='A participant.', status='Approved',
        origin='Curated', originId='origin-1', version=3, source='Curated', sourcePath='terms/customer.yaml',
        validFrom='2020-01-01')])


def resolve(s, **kw):
    return resolve_context(s, dict(question='Customer', scope='Research'), **kw)


class ApplicationResolverTests(unittest.TestCase):
    def test_dynamic_scope_and_authored_provenance(self):
        s = state()
        result = resolve(s)
        self.assertEqual(result['state'], 'sufficient')
        self.assertFalse(result['simulation'])
        self.assertEqual(result['facts'][0]['evidence']['originRevision'], 3)
        self.assertEqual(result['facts'][0]['evidence']['sourcePath'], 'terms/customer.yaml')
        self.assertEqual(resolve_context(s, dict(question='Customer', scope='Other'))['state'], 'scopeMismatch')

    def test_hidden_unknown_and_denial_before_hints(self):
        s = state()
        s['knowledge'][0]['hidden'] = True
        self.assertEqual(resolve(s), resolve_context(s, dict(question='Unknown', scope='Other')))
        s['knowledge'][0].update(hidden=False, restricted=True)
        self.assertEqual(resolve_context(s, dict(question='Customer', scope='Other', reader='steward'), reader='restricted')['state'], 'denied')

    def test_ambiguous_and_draft(self):
        s = state()
        s['knowledge'].append({**s['knowledge'][0], 'id': 'second', 'scope': 'Operations'})
        result = resolve_context(s, dict(question='Customer', scope=''))
        self.assertEqual(result['state'], 'ambiguous')
        self.assertEqual(len(result['choices']), 2)
        s['knowledge'][0]['status'] = 'Draft'
        self.assertEqual(resolve(s)['state'], 'withheld')

    def test_metric_requires_formula(self):
        s = state()
        s['knowledge'][0].update(type='Metric', unit='count', aggregation='sum')
        self.assertEqual(resolve(s)['state'], 'incomplete')
        s['knowledge'][0]['formula'] = 'count(*)'
        self.assertEqual(resolve(s)['state'], 'sufficient')

    def test_cache_invalidation_and_ttl(self):
        s = state()
        s['knowledge'][0]['ttl'] = 2
        resolve(s, simulation=True)
        self.assertEqual(s['cache'][0]['expiresAt'] - s['cache'][0]['retrievedAt'], 7200000)
        resolve(s, simulation=True)
        self.assertTrue(s['observations'][-1]['hit'])
        s['knowledge'][0]['definition'] = 'Changed canonical text'
        result = resolve(s, simulation=True)
        self.assertEqual(result['facts'][0]['value'], 'Changed canonical text')
        self.assertFalse(s['observations'][-1]['hit'])

    def test_core_provenance_permission_before_cache(self):
        s = state()
        s['assets'] = [dict(id='source', providerId='uc', name='frontend label')]
        s['providers'].append(dict(id='uc', kind='uc', enabled=True, health='healthy', ttl=1))
        s['providers'].append(dict(id='actual-core-provider', kind='uc', enabled=True, health='healthy', ttl=2))
        s['mappings'] = [dict(knowledgeId='term', assetId='source', fieldPath='status', status='Approved', validFrom='2020-01-01')]
        provenance = dict(provider='actual-core-provider', revision='abc', document='catalog.json', locator='/assets/0/facts/columns', retrieved_at='2026-10-24T00:00:00Z')
        calls = []
        def core(asset, fields):
            calls.append((asset, fields))
            return dict(status='complete', selected={'relation': {'value': {}, 'provenance': provenance},
                'columns': {'value': [{'name': 'status'}], 'provenance': provenance}})
        result = resolve(s, catalog_resolve=core)
        self.assertEqual(result['state'], 'sufficient')
        e = result['facts'][0]['evidence']
        self.assertEqual((e['providerId'], e['assetId'], e['fieldPath']), ('actual-core-provider', 'source', 'status'))
        self.assertEqual(e['sourceRevision'], 'abc')
        self.assertEqual(e['originRevision'], 3)
        resolve(s, catalog_resolve=core)
        self.assertEqual(len(calls), 2)
        result = resolve(s, catalog_resolve=lambda *_: {'status': 'denied'})
        self.assertEqual(result['state'], 'denied')
        self.assertEqual(result['facts'], [])
        s['providers'][1]['enabled'] = False
        self.assertEqual(resolve(s, catalog_resolve=core)['state'], 'incomplete')

    def test_only_cache_and_observations_mutated(self):
        s = state()
        before = deepcopy(s)
        resolve(s)
        for key in before:
            if key not in ('cache', 'observations'):
                self.assertEqual(s[key], before[key])

    def test_explicit_simulation_retains_authored_replica(self):
        import json
        from pathlib import Path
        s = json.loads((Path(__file__).parents[1] / 'examples/uol-workspace/fixture.json').read_text())
        authored = next(p for p in s['providers'] if p['id'] == 'authored')
        s['providers'].remove(authored)
        s['providers'].insert(0, authored)
        result = resolve_context(s, {'objectId': 'active-customer', 'scope': 'Service'}, simulation=True)
        self.assertEqual(result['state'], 'sufficient')
        self.assertTrue(result['facts'][0]['evidence']['replica'])
        self.assertEqual(result['facts'][0]['evidence']['sourcePath'], 'terms/active-customer.yaml')
        result = resolve_context(s, {'objectId': 'active-customer', 'scope': 'Service'})
        self.assertEqual(result['state'], 'incomplete')

    def test_repeated_resolution_keeps_recent_observations_within_state_bounds(self):
        import json
        from pathlib import Path
        from dbt_skills.context_limits import check_bounds

        s = json.loads((Path(__file__).parents[1] / 'examples/uol-workspace/fixture.json').read_text())
        request = {'objectId': 'active-customer', 'scope': 'Service'}
        for _ in range(600):
            s['clock'] += 1
            result = resolve_context(s, request, simulation=True)
            self.assertEqual(result['state'], 'sufficient')
            check_bounds(s)
        self.assertLessEqual(len(s['observations']), 256)
        self.assertTrue(s['observations'][-1]['hit'])
        self.assertEqual(s['observations'][-1]['at'], s['clock'])
        self.assertEqual(len(s['cache']), len(result['facts']))

    def test_resolution_prunes_existing_observation_backlog(self):
        s = state()
        resolve(s, simulation=True)
        old = deepcopy(s['observations'][0])
        old['at'] = 1
        s['observations'] = [deepcopy(old) for _ in range(3000)]
        result = resolve(s, simulation=True)
        self.assertEqual(result['state'], 'sufficient')
        self.assertLessEqual(len(s['observations']), 256)
        self.assertEqual(s['observations'][-1]['at'], s['clock'])
