import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveContext} from '../src/contextResolver.js';
import {initialKnowledge, initialProviders} from '../src/data.js';

const activeQuestion = 'What counts as an active customer?';
const resolve = overrides => resolveContext({
  question: activeQuestion,
  scope: 'service',
  reader: 'standard',
  knowledge: initialKnowledge,
  providers: initialProviders,
  ...overrides,
});

test('native evidence resolves the selected meaning with its real source path', () => {
  const result = resolve();
  assert.equal(result.state, 'ready');
  assert.equal(result.item.id, 'active-customer');
  for (const id of ['definition', 'grain', 'mapping']) {
    const fact = result.facts.find(value => value.id === id);
    assert.equal(fact.state, 'Resolved');
    assert.equal(fact.providerId, 'unity');
    assert.equal(fact.sourcePath, 'customer.metrics.active_customers');
    assert.equal(fact.originId, 'uol:term:active-customer');
  }
});

test('finance denial uses the resolved item even when the request says service', () => {
  const result = resolve({
    question: 'How is monthly recurring revenue defined?',
    scope: 'service',
    reader: 'restricted',
  });
  assert.equal(result.state, 'denied');
  assert.equal(result.item.id, 'mrr');
  assert.ok(result.facts.every(fact => fact.state === 'Denied'));
  assert.ok(result.facts.every(fact => fact.value === null && fact.source === null));
  assert.deepEqual(result.providerOrder, []);
});

test('a permitted item in the wrong scope requests its actual business context', () => {
  const result = resolve({question: 'How is monthly recurring revenue defined?'});
  assert.equal(result.state, 'scopeMismatch');
  assert.equal(result.expectedScope, 'billing');
  assert.equal(result.facts, undefined);
});

test('previewing a new draft remains pinned and withholds its definition', () => {
  const draft = {
    id: 'new-draft', name: 'Engaged customer', domain: 'lifecycle',
    scope: 'Service', status: 'Draft', origin: 'Curated', version: 1,
    definition: 'An unapproved working definition.', grain: 'Customer',
    source: 'Authored definitions', sourcePath: 'Local draft · this session',
    synonyms: [], type: 'Business term',
  };
  const result = resolve({
    initialItemId: draft.id,
    seedQuestion: activeQuestion,
    knowledge: [...initialKnowledge, draft],
  });
  assert.equal(result.state, 'withheld');
  assert.equal(result.item.id, 'new-draft');
  assert.equal(result.facts, undefined);
  assert.equal(result.item.definition, undefined);
});

test('a selected inference stays withheld until explicitly approved', () => {
  const result = resolve({initialItemId: 'suspended-rule', seedQuestion: activeQuestion});
  assert.equal(result.state, 'withheld');
  assert.equal(result.item.id, 'suspended-rule');
  assert.equal(result.facts, undefined);
});

test('an approved selected inference resolves itself and retains its origin', () => {
  const knowledge = initialKnowledge.map(item => item.id === 'suspended-rule'
    ? {...item, status: 'Approved', version: 2}
    : item);
  const result = resolve({
    initialItemId: 'suspended-rule', seedQuestion: activeQuestion, knowledge,
  });
  assert.equal(result.state, 'ready');
  assert.equal(result.item.id, 'suspended-rule');
  assert.equal(result.item.origin, 'Inferred');
  const definition = result.facts.find(fact => fact.id === 'definition');
  assert.equal(definition.providerId, 'openmetadata');
  assert.equal(definition.sourcePath, 'retention_summary.sql · metadata annotation');
  assert.equal(definition.originId, 'uol:rule:suspended-rule');
});

test('an unknown question is not resolved merely because it mentions customer', () => {
  const result = resolve({question: 'Why did customer satisfaction fall?'});
  assert.equal(result.state, 'missing');
  assert.equal(result.item, undefined);
  assert.equal(result.facts, undefined);
});

test('the authored fallback has explicitly declared YAML evidence and keeps the original identity', () => {
  const result = resolve({providers: initialProviders.filter(provider => provider.id === 'authored')});
  assert.equal(result.state, 'ready');
  for (const fact of result.facts) {
    assert.equal(fact.source, 'Authored definitions');
    assert.equal(fact.providerId, 'authored');
    assert.equal(fact.sourcePath, 'terms/active-customer.yaml');
    assert.equal(fact.originId, 'uol:term:active-customer');
    assert.match(fact.reason, /demo replica/i);
  }
  assert.equal(result.facts.find(fact => fact.id === 'mapping').value, 'terms/active-customer.yaml');
});

test('with no enabled evidence providers the context is incomplete and contains no values', () => {
  const result = resolve({providers: initialProviders.map(provider => ({...provider, enabled: false}))});
  assert.equal(result.state, 'incomplete');
  assert.ok(result.facts.every(fact => fact.state === 'Insufficient'));
  assert.ok(result.facts.every(fact => fact.value === null && fact.source === null));
  assert.deepEqual(result.providerOrder, []);
});

test('active customer needs disambiguation when no context is selected', () => {
  const result = resolve({scope: 'unspecified'});
  assert.equal(result.state, 'ambiguous');
  assert.equal(result.facts, undefined);
});

test('the active-customer family changes meaning with the explicitly chosen scope', () => {
  const result = resolve({
    initialItemId: 'active-customer', seedQuestion: activeQuestion, scope: 'billing',
  });
  assert.equal(result.state, 'ready');
  assert.equal(result.item.id, 'billing-active');
  for (const fact of result.facts) {
    assert.equal(fact.providerId, 'authored');
    assert.equal(fact.sourcePath, 'finance/active-customer.yaml');
  }
});

test('named synonyms resolve without inventing unavailable exclusions', () => {
  const result = resolve({question: 'How is service churn defined?'});
  assert.equal(result.state, 'ready');
  assert.equal(result.item.id, 'churn-rate');
  assert.equal(result.facts.some(fact => fact.id === 'exclusions'), false);
});

test('metric previews include their declared formula and unit', () => {
  const scenarios = [
    {question: 'How is MRR defined?', scope: 'billing'},
    {question: 'How are active customers defined?', scope: 'service'},
  ];
  const actual = scenarios.map(scenario => {
    const result = resolve(scenario);
    return {id: result.item.id, state: result.state,
      facts: Object.fromEntries(result.facts.filter(fact => ['formula', 'unit'].includes(fact.id))
        .map(fact => [fact.id, fact.value]))};
  });
  assert.deepEqual(actual, [
    {id: 'mrr', state: 'ready', facts: {formula: 'SUM(normalised_monthly_recurring_charge)', unit: 'GBP'}},
    {id: 'active-customers', state: 'ready', facts: {formula: 'COUNT(DISTINCT customer_id)', unit: 'Customers'}},
  ]);
});

test('a metric without a formula has insufficient context', () => {
  const knowledge = initialKnowledge.map(item => item.id === 'mrr' ? {...item, formula: undefined} : item);
  const result = resolve({question: 'How is MRR defined?', scope: 'billing', knowledge});
  const formula = result.facts.find(fact => fact.id === 'formula');
  assert.deepEqual({state: result.state, formulaState: formula?.state, formulaValue: formula?.value},
    {state: 'incomplete', formulaState: 'Insufficient', formulaValue: null});
});

test('provider order selects between declared replicas rather than changing their provenance', () => {
  const authored = initialProviders.find(provider => provider.id === 'authored');
  const result = resolve({providers: [authored, ...initialProviders.filter(provider => provider.id !== 'authored')]});
  assert.equal(result.state, 'ready');
  assert.equal(result.facts[0].providerId, 'authored');
  assert.equal(result.facts[0].sourcePath, 'terms/active-customer.yaml');
});

test('editing the seed question releases the selected-item pin', () => {
  const result = resolve({
    initialItemId: 'active-customer', seedQuestion: activeQuestion,
    question: 'How is MRR defined?', scope: 'billing',
  });
  assert.equal(result.state, 'ready');
  assert.equal(result.item.id, 'mrr');
});

test('a provider denial stops fallback even when an authored replica is available', () => {
  const providers = initialProviders.map(provider => provider.id === 'unity'
    ? {...provider, state: 'Denied'}
    : provider);
  const result = resolve({providers});
  assert.equal(result.state, 'denied');
  assert.ok(result.facts.every(fact => fact.state === 'Denied' && fact.value === null));
  assert.ok(result.facts.every(fact => fact.providerId !== 'authored'));
});

test('an unavailable provider permits fallback to an explicitly declared replica', () => {
  const providers = initialProviders.map(provider => provider.id === 'unity'
    ? {...provider, state: 'Unavailable'}
    : provider);
  const result = resolve({providers});
  assert.equal(result.state, 'ready');
  assert.ok(result.facts.every(fact => fact.providerId === 'authored'));
});

test('a missing required grain cannot become sufficient through provider availability', () => {
  const knowledge = initialKnowledge.map(item => item.id === 'active-customer'
    ? {...item, grain: ''}
    : item);
  const result = resolve({knowledge});
  assert.equal(result.state, 'incomplete');
  assert.equal(result.facts.find(fact => fact.id === 'grain').state, 'Insufficient');
  assert.equal(result.facts.find(fact => fact.id === 'grain').value, null);
});
