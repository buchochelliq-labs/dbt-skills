import copy
import json
import unittest
from unittest.mock import patch

import metadata_fixture
import test_model_planning
from dbt_skills.catalog import CatalogError, CatalogResolver, Claim, FIELDS, ProviderResult, load_catalog
from dbt_skills.model_planning import plan_model
from dbt_skills.modelling_policy import load_document
from dbt_skills.project_artifacts import inspect_artifacts
from dbt_skills.project_catalog import scope_catalog
from dbt_skills.metadata_types import assess_types


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_planning.ModelPlanningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.asset = 'urn:demo:xyz:customers'

    def configure(self, options):
        path = self.root / 'catalogs.json'
        doc = json.loads(path.read_text())
        doc['resolution'] = options
        path.write_text(json.dumps(doc))
        return load_catalog(path)

    def conflict(self):
        path = self.root / 'curated.json'
        doc = json.loads(path.read_text())
        physical = json.loads((self.root / 'physical.json').read_text())
        columns = copy.deepcopy(physical['assets'][0]['facts']['columns'])
        columns[0]['type'] = 'string'
        doc['assets'][0]['facts']['columns'] = columns
        path.write_text(json.dumps(doc))

    def test_defaults_first_sufficient_and_disabled_order(self):
        self.conflict()
        catalog = self.configure({'provider_priority': {'enabled': False, 'order': ['curated', 'physical']}})
        result = catalog.resolve(self.asset, ['columns'])
        self.assertEqual(result['selected']['columns']['provenance']['provider'], 'physical')
        self.assertEqual(result['unqueried'], ['curated'])
        self.assertEqual(result['conflicts'], [])
        result = catalog.resolve(self.asset, list(FIELDS))
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['unresolved_conflicts'], ['columns'])
        self.assertEqual(result['resolved_conflicts'], [])

    def test_priority_reads_all_retains_claims_and_selects_first(self):
        self.conflict()
        catalog = self.configure({'provider_priority': {'enabled': True, 'order': ['curated', 'physical']}})
        result = catalog.resolve(self.asset, ['columns'])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['selected']['columns']['provenance']['provider'], 'curated')
        self.assertEqual(len(result['claims']['columns']), 2)
        self.assertEqual(result['resolved_conflicts'], ['columns'])
        self.assertEqual(result['unresolved_conflicts'], [])
        self.assertEqual(result['unqueried'], [])

    def test_invalid_options(self):
        for options in [None, {'planning_mode': 'unsafe'}, {'type_compatibility': 'cast'}, {'extra': True},
                        {'provider_priority': {'enabled': 1}},
                        {'provider_priority': {'enabled': True, 'order': ['physical']}},
                        {'provider_priority': {'enabled': True, 'order': ['physical', 'physical']}},
                        {'provider_priority': {'enabled': True, 'order': ['physical', 'unknown']}}]:
            with self.subTest(options=options), self.assertRaises(CatalogError):
                self.configure(options)

    def test_enabled_denial_and_error_clear_every_claim(self):
        catalog = self.configure({'provider_priority': {'enabled': True, 'order': ['physical', 'curated']}})
        for status in ['denied', 'error']:
            with patch.object(catalog.providers[1], 'fetch', return_value=ProviderResult(status)):
                result = catalog.resolve(self.asset, ['columns'])
            self.assertEqual(result['status'], status)
            for key in ['selected', 'claims', 'conflicts', 'resolved_conflicts', 'unresolved_conflicts']:
                self.assertFalse(result[key])

    def test_scope_mismatch_cannot_be_prioritized(self):
        catalog = self.configure({'provider_priority': {'enabled': True, 'order': ['physical', 'curated']}})
        provider = catalog.providers[1]
        original = provider.fetch
        def fetch(asset, fields):
            result = original(asset, fields)
            return ProviderResult('available', tuple(Claim(c.field, c.value, {**c.provenance, 'scope': 'another'}) for c in result.claims))
        with patch.object(provider, 'fetch', side_effect=fetch):
            result = catalog.resolve(self.asset, list(FIELDS))
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['selected'])

    def test_identity_quarantine_cannot_be_prioritized(self):
        path = self.root / 'curated.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['relation'] = {'catalog': 'other', 'schema': 'xyz', 'name': 'customers'}
        path.write_text(json.dumps(doc))
        catalog = self.configure({'provider_priority': {'enabled': True, 'order': ['physical', 'curated']}})
        scoped = scope_catalog(catalog, inspect_artifacts(self.fixture.fixture.project))
        result = scoped.resolve(self.asset, ['columns'])
        self.assertEqual(result['status'], 'denied')
        self.assertEqual(result['scope_reason'], 'conflicting_bindings')

    def test_scoped_same_manifest_retains_active_subset(self):
        catalog = self.configure({'provider_priority': {'enabled': True, 'order': ['curated', 'physical']}})
        snapshot = inspect_artifacts(self.fixture.fixture.project)
        scoped = scope_catalog(catalog, snapshot)
        scoped.providers = (scoped.providers[0],)
        self.assertIs(scope_catalog(scoped, snapshot), scoped)
        result = plan_model(self.fixture.fixture.project, load_document(self.root / 'modelling.yml'), scoped,
                            self.fixture.request, snapshot=snapshot)
        self.assertEqual(result['evidence'][self.asset]['attempts'], [{'provider': 'physical', 'status': 'available'}])

    def test_partial_withholds_only_conflicted_entity_and_target(self):
        self.fixture.add_orders()
        self.conflict()
        self.fixture.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        self.configure({'planning_mode': 'partial'})
        result = self.fixture.plan()
        self.assertEqual(result['withheld_assets'], [self.asset])
        self.assertEqual([e['asset_id'] for e in result['entities']], ['urn:demo:xyz:orders'])
        self.assertEqual(result['relationships'][0]['status'], 'blocked_conflict')
        self.configure({})
        self.assertEqual(self.fixture.plan()['entities'], [])

    def test_partial_permission_blocks_whole_response(self):
        self.conflict()
        self.configure({'planning_mode': 'partial'})
        self.fixture.request['assets'].append({'asset_id': 'outside'})
        result = self.fixture.plan()
        self.assertEqual(result['status'], 'blocked')
        for key in ['evidence', 'entities', 'relationships', 'withheld_assets']:
            self.assertFalse(result[key])

    def test_types_are_ordered_advisory_with_provenance(self):
        path, document = self.fixture.add_orders()
        document['assets'][1]['facts']['columns'][1]['type'] = 'float64'
        path.write_text(json.dumps(document))
        self.fixture.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        relation = self.fixture.plan()['relationships'][0]
        assessment = relation['type_assessments'][0]
        self.assertEqual(assessment['assessment'], 'potentially_compatible')
        self.assertEqual(assessment['source_column'], 'customer_id')
        self.assertEqual(assessment['source_provenance']['provider'], 'physical')
        self.assertFalse(relation['warnings'])
        self.configure({'type_compatibility': 'exact'})
        relation = self.fixture.plan()['relationships'][0]
        self.assertEqual(relation['status'], 'declared_endpoints_valid')
        self.assertEqual(relation['warnings'][0]['code'], 'relationship_type_mismatch')
        self.assertEqual(relation['warnings'][0]['severity'], 'warning')

    def test_composite_pairs_keep_declared_order_and_warning_subset(self):
        path, document = self.fixture.add_orders()
        customer = document['assets'][0]['facts']['columns']
        customer.append({'name': 'region_id', 'type': 'string', 'nullable': False})
        order = document['assets'][1]['facts']
        order['foreign_keys'][0].update(columns=['order_id', 'customer_id'], target_columns=['region_id', 'customer_id'])
        path.write_text(json.dumps(document))
        self.fixture.request['assets'].append({'asset_id': 'urn:demo:xyz:orders'})
        relation = self.fixture.plan()['relationships'][0]
        self.assertEqual([a['source_column'] for a in relation['type_assessments']], ['order_id', 'customer_id'])
        self.assertEqual([a['target_column'] for a in relation['type_assessments']], ['region_id', 'customer_id'])
        self.assertEqual(len(relation['warnings']), 1)
        self.assertEqual(relation['warnings'][0]['assessment'], 'requires_review')
        self.assertEqual(relation['status'], 'declared_endpoints_valid')

    def test_generic_type_families_and_unknowns(self):
        for value in ['array', 'map', 'struct', 'unknown', None, 'array<int64>']:
            self.assertEqual(assess_types(value, value)['assessment'], 'unknown')
        for value in ['int64', 'string', 'date', 'boolean']:
            result = assess_types(value, value)
            self.assertEqual((result['assessment'], result['severity'], result['verified']), ('exact', 'info', False))
        self.assertEqual(assess_types('int64', 'decimal')['assessment'], 'potentially_compatible')
        self.assertEqual(assess_types('int64', 'string')['assessment'], 'requires_review')
        self.assertEqual(assess_types('int64', 'string')['severity'], 'warning')
