const FINANCE_DOMAINS = new Set(['finance', 'revenue', 'receivables', 'collections']);
const SERVICE_DOMAINS = new Set(['customer', 'lifecycle', 'onboarding', 'retention', 'operations', 'service']);
const ACTIVE_CUSTOMER_IDS = new Set(['active-customer', 'billing-active']);
const SOURCE_PROVIDERS = {
  'Unity Catalog': 'unity',
  OpenMetadata: 'openmetadata',
  'Authored definitions': 'authored',
};
const ORIGIN_TYPES = {
  'Business term': 'term', Concept: 'concept', Metric: 'metric', Rule: 'rule', Page: 'page',
};

// These are deliberately declared demo replicas, not a claim that every provider
// contains every fixture. Each fact keeps the identity of the original meaning.
const DEMO_REPLICAS = {
  'active-customer': [{
    providerId: 'authored',
    sourcePath: 'terms/active-customer.yaml',
    facts: ['definition', 'grain', 'mapping', 'exclusions', 'logic'],
  }],
};

function normalise(value) {
  return String(value ?? '').normalize('NFKC').toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function requestedTerm(question) {
  const text = normalise(question);
  const forms = [
    /^how (?:is|are) (?:a |an |the )?(.+) defined$/,
    /^what (?:is|are) the definitions? of (.+)$/,
    /^what does (.+) mean$/,
    /^(?:what (?:is|are)|what counts as|define|describe|explain|tell me about|how do you define) (?:a |an |the )?(.+)$/,
  ];
  for (const form of forms) {
    const match = text.match(form);
    if (match) return match[1];
  }
  return text;
}

function itemIdentity(item) {
  // No definition or source values can leak through the item on a denied,
  // withheld, mismatched, or incomplete result; those belong in resolved facts.
  const {id, name, type, domain, scope, status, origin, version, effective} = item;
  return {id, name, type, domain, scope, status, origin, version, effective};
}

function financeItem(item) {
  return FINANCE_DOMAINS.has(item.domain)
    || ['billing', 'finance', 'collections'].includes(normalise(item.scope));
}

function expectedScope(item) {
  if (financeItem(item)) return 'billing';
  if (['enterprise', 'commercial'].includes(normalise(item.scope))) return null;
  if (SERVICE_DOMAINS.has(item.domain)
    || ['service', 'retention', 'operations'].includes(normalise(item.scope))) return 'service';
  return null;
}

function supplied(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function factDefinitions(item) {
  const grainDefined = supplied(item.grain)
    && !['not defined', 'not yet defined'].includes(normalise(item.grain));
  const facts = [
    {id: 'definition', label: 'Business definition', value: supplied(item.definition) ? item.definition : null},
    {id: 'grain', label: 'Grain & scope', value: grainDefined && supplied(item.scope)
      ? item.grain + ' · ' + item.scope : null},
    {id: 'mapping', label: 'Source reference', value: supplied(item.sourcePath) ? item.sourcePath : null},
  ];
  if (item.type === 'Metric') {
    for (const [id, label] of [['formula', 'Formula'], ['unit', 'Unit'], ['aggregation', 'Aggregation']]) {
      facts.push({id, label, value: supplied(item[id]) ? item[id] : null});
    }
    if (Array.isArray(item.dimensions) && item.dimensions.length) {
      const dimensions = item.dimensions.filter(supplied);
      if (dimensions.length) facts.push({id: 'dimensions', label: 'Dimensions', value: dimensions.join(' · ')});
    }
  }
  if (supplied(item.logic)) {
    facts.push({id: 'logic', label: 'Business logic', value: item.logic});
  }
  if (supplied(item.exclusions)) {
    facts.push({id: 'exclusions', label: 'Rules & exclusions', value: item.exclusions});
  }
  return facts;
}

function evidenceByFact(item, facts) {
  const originId = item.originId || 'uol:' + (ORIGIN_TYPES[item.type] || 'knowledge') + ':' + item.id;
  const nativeProvider = SOURCE_PROVIDERS[item.source];
  return new Map(facts.map(fact => {
    const evidence = [];
    if (nativeProvider && supplied(item.sourcePath)) {
      evidence.push({
        providerId: nativeProvider, sourcePath: item.sourcePath, originId,
        value: fact.value, demoReplica: false,
      });
    }
    for (const replica of DEMO_REPLICAS[item.id] || []) {
      if (!replica.facts.includes(fact.id)) continue;
      evidence.push({
        providerId: replica.providerId, sourcePath: replica.sourcePath, originId,
        value: fact.id === 'mapping' ? replica.sourcePath : fact.value,
        demoReplica: true,
      });
    }
    return [fact.id, evidence];
  }));
}

function resolveFact(fact, evidence, providers) {
  const attempts = [];
  for (const provider of providers) {
    const candidate = evidence.find(entry => entry.providerId === provider.id);
    if (!candidate) {
      attempts.push(provider.name + ': unsupported for this fact.');
      continue;
    }
    if (normalise(provider.state) === 'denied') {
      return {
        id: fact.id, label: fact.label, value: null, state: 'Denied', source: null,
        providerId: provider.id,
        reason: provider.name + ' denied this fact; no fallback attempted.',
      };
    }
    if (provider.state && normalise(provider.state) !== 'available') {
      attempts.push(provider.name + ': ' + provider.state.toLowerCase() + '.');
      continue;
    }
    if (!supplied(candidate.value)) {
      attempts.push(provider.name + ': insufficient metadata for this fact.');
      continue;
    }
    return {
      id: fact.id, label: fact.label, value: candidate.value, state: 'Resolved',
      source: provider.name, providerId: provider.id, sourcePath: candidate.sourcePath,
      originId: candidate.originId,
      reason: 'First sufficient permitted source in the configured order. '
        + (candidate.demoReplica ? 'Explicit demo replica; original identity retained. ' : 'Declared fixture evidence. ')
        + attempts.join(' '),
    };
  }
  return {
    id: fact.id, label: fact.label, value: null, state: 'Insufficient', source: null,
    reason: providers.length
      ? attempts.join(' ') + ' No enabled provider supplies sufficient evidence for this fact.'
      : 'No metadata providers are enabled.',
  };
}

/** Resolve only the simulated workspace's named definitions and evidence. */
export function resolveContext({
  question = '', scope = 'unspecified', reader = 'standard', initialItemId,
  seedQuestion, knowledge = [], providers = [],
}) {
  const request = {question, scope, reader};
  let item;
  let family = false;
  if (initialItemId && typeof seedQuestion === 'string' && question === seedQuestion) {
    item = knowledge.find(entry => entry.id === initialItemId);
    family = Boolean(item && ACTIVE_CUSTOMER_IDS.has(item.id));
  } else {
    const term = requestedTerm(question);
    const matches = term ? knowledge.filter(entry => [entry.name, ...(entry.synonyms || [])]
      .some(alias => normalise(alias) === term)) : [];
    family = matches.length > 1 && matches.every(entry => ACTIVE_CUSTOMER_IDS.has(entry.id));
    if (matches.length > 1 && !family) {
      return {...request, state: 'ambiguous', message: 'Several definitions match this term. Open the intended definition to preview its context.'};
    }
    item = matches[0];
  }

  if (family) {
    if (!['service', 'billing'].includes(scope)) {
      return {...request, state: 'ambiguous', message: 'Active customer has Service and Billing meanings. Choose a business context.'};
    }
    item = knowledge.find(entry => entry.id === (scope === 'billing' ? 'billing-active' : 'active-customer'));
  }
  if (!item) {
    return {...request, state: 'missing', message: 'No named definition or synonym matches this question in the sample workspace.'};
  }

  const identity = itemIdentity(item);
  const definitions = factDefinitions(item);
  // Authorisation is checked against resolved metadata, never the caller's
  // selected scope, and precedes all provider selection or fallback.
  if (reader === 'restricted' && financeItem(item)) {
    const reason = 'Sample policy denies this financial metadata; no fallback attempted.';
    return {
      ...request, state: 'denied', item: identity, providerOrder: [], message: reason,
      facts: definitions.map(fact => ({
        id: fact.id, label: fact.label, value: null, state: 'Denied', source: null, reason,
      })),
    };
  }
  if (item.status !== 'Approved') {
    return {...request, state: 'withheld', item: identity,
      message: 'This definition is ' + (item.status || 'unapproved') + ' and is withheld from agent context until explicitly approved.'};
  }
  const expected = expectedScope(item);
  if (expected && scope !== expected) {
    return {...request, state: 'scopeMismatch', item: identity, expectedScope: expected,
      message: 'This definition belongs to ' + (expected === 'billing' ? 'Finance · Billing' : 'Customer · Service') + '. Select that business context to continue.'};
  }

  const enabled = providers.filter(provider => provider.enabled);
  const registry = evidenceByFact(item, definitions);
  const facts = definitions.map(fact => resolveFact(fact, registry.get(fact.id), enabled));
  const state = facts.some(fact => fact.state === 'Denied') ? 'denied'
    : facts.every(fact => fact.state === 'Resolved') ? 'ready' : 'incomplete';
  return {...request, state, item: identity, facts, providerOrder: enabled.map(provider => provider.name)};
}
