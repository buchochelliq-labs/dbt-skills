import type {
  State,
  Domain,
  Knowledge,
  Reader,
  Provider,
  Fact,
  MetadataAdapter,
  ResolutionRequest,
  ResolutionOutcome,
  Proposal,
  Mapping,
  PublicationAdapter,
} from "./contracts";
export const HOUR = 3600000;
export function path(state: State, id: string): Domain[] {
  const out: Domain[] = [];
  const seen = new Set<string>();
  let d = state.domains.find((d) => d.id === id);
  while (d && !seen.has(d.id)) {
    seen.add(d.id);
    out.unshift(d);
    d = state.domains.find((x) => x.id === d!.parent);
  }
  return out;
}
export function inDomain(s: State, id: string, parent: string) {
  return path(s, id).some((d) => d.id === parent);
}
export function visible<T extends { hidden?: boolean }>(items: T[]) {
  return items.filter((x) => !x.hidden);
}
export function mayInspect(
  x: { hidden?: boolean; restricted?: boolean },
  r: Reader,
) {
  return !x.hidden && !(r === "restricted" && x.restricted);
}
export function knowledgeView(s: State, r: Reader) {
  return visible(s.knowledge).filter((k) => mayInspect(k, r));
}
export function domainKnowledge(
  state: State,
  reader: Reader,
  domainId: string,
  includeDescendants: boolean,
) {
  return knowledgeView(state, reader).filter((knowledge) =>
    [knowledge.domain, ...knowledge.memberships].some((membership) =>
      includeDescendants
        ? inDomain(state, membership, domainId)
        : membership === domainId,
    ),
  );
}
export function assetView(s: State, r: Reader) {
  return visible(s.assets).filter((a) => mayInspect(a, r));
}
export function invalidate(s: State) {
  s.configVersion++;
  s.cache = [];
}
export function updateDomain(s: State, id: string, patch: Partial<Domain>) {
  const d = s.domains.find((x) => x.id === id);
  if (!d) throw Error("Domain unavailable");
  const parent = patch.parent === undefined ? d.parent : patch.parent;
  const name = (patch.name ?? d.name).trim();
  if (!name) throw Error("A name is required");
  if (id === "enterprise" && parent !== null)
    throw Error("Enterprise must remain the root");
  if (
    id !== "enterprise" &&
    (!parent || !s.domains.some((x) => x.id === parent))
  )
    throw Error("Choose an existing parent");
  if (parent && path(s, parent).some((x) => x.id === id))
    throw Error("A domain cannot move into itself or its descendants");
  if (
    s.domains.some(
      (x) =>
        x.id !== id &&
        x.parent === parent &&
        x.name.toLowerCase() === name.toLowerCase(),
    )
  )
    throw Error("A sibling already uses that name");
  if (patch.ttl != null && (!Number.isFinite(patch.ttl) || patch.ttl <= 0))
    throw Error("TTL must be positive");
  Object.assign(d, patch, { id, name, parent });
  invalidate(s);
  return d;
}
export function createDomain(
  s: State,
  name: string,
  parent: string,
  description: string,
) {
  if (!s.domains.some((d) => d.id === parent) || !name.trim())
    throw Error("Name and parent are required");
  if (
    s.domains.some(
      (d) =>
        d.parent === parent &&
        d.name.toLowerCase() === name.trim().toLowerCase(),
    )
  )
    throw Error("A sibling already uses that name");
  const d: Domain = {
    id: `domain-${s.sequence++}`,
    name: name.trim(),
    parent,
    description,
    owner: null,
    technicalOwner: null,
    steward: null,
    providerPolicy: null,
    ttl: null,
  };
  s.domains.push(d);
  return d;
}
export function inherited(s: State, id: string, key: keyof Domain) {
  for (const d of path(s, id).reverse()) {
    if (d[key] != null) return { value: d[key], origin: d.name, id: d.id };
  }
  return {
    value: key === "ttl" ? 24 : "Not set",
    origin: "Workspace default",
    id: "workspace",
  };
}
export function ttl(s: State, k: Knowledge, p: Provider) {
  if (k.ttl != null) return { hours: k.ttl, origin: "Object override" };
  for (const d of path(s, k.domain).reverse())
    if (d.ttl != null) return { hours: d.ttl, origin: `Domain: ${d.name}` };
  return {
    hours: p.ttl ?? 24,
    origin: p.ttl != null ? `Provider: ${p.name}` : "Workspace default",
  };
}
function validDate(value: string) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
function validateValidity(from: string, to?: string) {
  if (!validDate(from)) throw Error("Business-valid from must be a real date in YYYY-MM-DD format");
  if (to && !validDate(to)) throw Error("Business-valid to must be a real date in YYYY-MM-DD format");
  if (to && to < from) throw Error("Validity ends before it begins");
}
export function revise(s: State, id: string, patch: Partial<Knowledge>) {
  const k = s.knowledge.find((x) => x.id === id);
  if (!k) throw Error("Knowledge unavailable");
  if (!String(patch.definition ?? k.definition).trim())
    throw Error("Definition is required");
  const next = { ...k, ...patch };
  if (!s.domains.some((d) => d.id === next.domain))
    throw Error("Choose an existing ownership domain");
  if (!Array.isArray(next.memberships) ||
      next.memberships.some((id) => id === next.domain || !s.domains.some((d) => d.id === id)) ||
      new Set(next.memberships).size !== next.memberships.length)
    throw Error("Additional memberships must be unique existing domains, excluding the ownership domain");
  validateValidity(next.validFrom, next.validTo);
  k.history.push({
    revision: k.version,
    definition: k.definition,
    status: k.status,
    origin: k.origin,
    changedAt: s.clock,
  });
  Object.assign(k, patch, {
    id: k.id,
    originId: k.originId,
    origin: k.origin,
    version: k.version + 1,
    status: "Draft",
  });
  invalidate(s);
  return k;
}
export function approve(s: State, id: string) {
  const k = s.knowledge.find((x) => x.id === id);
  if (!k) throw Error("Knowledge unavailable");
  k.status = "Approved";
  invalidate(s);
}
export function providerFor(k: Knowledge) {
  return k.source === "Unity Catalog"
    ? k.domain === "revenue"
      ? "uc-finance"
      : "uc-customer"
    : k.source === "OpenMetadata"
      ? "openmetadata"
      : "authored";
}
function norm(v: string) {
  return v
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
function expectedScope(k: Knowledge) {
  if (["Enterprise", "Commercial"].includes(k.scope)) return null;
  return ["Billing", "Collections"].includes(k.scope) ? "Billing" : "Service";
}
function valueOf(k: Knowledge, key: string) {
  return key === "scope"
    ? `${k.scope} · ${k.grain}`
    : key === "source"
      ? k.sourcePath
      : Array.isArray((k as any)[key])
        ? (k as any)[key].join(", ")
        : (k as any)[key];
}
export const mockAdapter: MetadataAdapter = {
  read(s, p, k, key, reader) {
    if (!p.scope.includes("*") && !p.scope.includes(k.domain))
      return { status: "unsupported" };
    const replica = k.id === "active-customer" && p.id === "authored";
    if (providerFor(k) !== p.id && !replica) return { status: "unsupported" };
    if (p.health === "denied") return { status: "denied" };
    if (p.health === "malformed") return { status: "error" };
    if (p.health === "outage") return { status: "unavailable" };
    const value = valueOf(k, key);
    if (typeof value !== "string" || !value.trim())
      return { status: "missing" };
    const asset = s.assets.find(
      (a) => a.name === k.sourcePath && a.providerId === providerFor(k),
    );
    return {
      status: "sufficient",
      fact: {
        id: key,
        value,
        evidence: {
          originId: k.originId,
          originRevision: k.version,
          providerId: p.id,
          assetId: asset?.id ?? `authored:${k.id}`,
          sourcePath: replica ? "terms/active-customer.yaml" : k.sourcePath,
          observedAt: s.clock,
          sourceRevision: `${k.originId}@${k.version}`,
          validFrom: k.validFrom,
          validTo: k.validTo,
          approval: k.status,
          origin: k.origin,
          reader,
          policyVersion: s.policyVersion,
          replica,
          confidence: "declared",
          authority: "not assessed",
        },
      },
    };
  },
};
export function resolve(s: State, req: ResolutionRequest): ResolutionOutcome {
  const base: ResolutionOutcome = {
    schema_version: 1,
    simulation: true,
    state: "missing",
    message: "No available meaning matches this request.",
    facts: [],
    trace: [],
  };
  const term = norm(req.question)
    .replace(/^(what is|define|explain|what does) (the |an? )?/, "")
    .replace(/ mean$/, "");
  const candidates = visible(s.knowledge).filter((k) =>
    req.objectId
      ? k.id === req.objectId
      : [k.name, ...k.synonyms].some((n) => norm(n) === term),
  );
  // Nonexistent and undiscoverable identifiers produce exactly the same payload.
  if (!candidates.length) return base;
  if (candidates.length > 1 && !["Service", "Billing"].includes(req.scope))
    return {
      ...base,
      state: "ambiguous",
      message: "Choose Service or Billing: these are different meanings.",
      choices: candidates
        .filter((k) => mayInspect(k, req.reader))
        .map((k) => ({ id: k.id, name: k.name, scope: k.scope })),
    };
  const k =
    candidates.length > 1
      ? candidates.find((k) => expectedScope(k) === req.scope)
      : candidates[0];
  if (!k) return base;
  if (!mayInspect(k, req.reader))
    return {
      ...base,
      state: "denied",
      message:
        "This reader cannot inspect the requested metadata. No replica or cache fallback.",
      trace: [
        "Identity disclosure permitted; fact access denied before scope and cache.",
      ],
    };
  // A known authorization denial on the origin is binding even when a replica is first.
  const origin = s.providers.find((p) => p.id === providerFor(k));
  if (origin?.health === "denied")
    return {
      ...base,
      state: "denied",
      message: "Origin policy denied access. No replica or cache fallback.",
    };
  if (k.status !== "Approved")
    return {
      ...base,
      state: "withheld",
      message: "Unapproved definition values are withheld by UOL policy.",
    };
  if (expectedScope(k) && expectedScope(k) !== req.scope)
    return {
      ...base,
      state: "scopeMismatch",
      message: `Choose the ${expectedScope(k)} business scope.`,
    };
  const day = new Date(s.clock).toISOString().slice(0, 10);
  if (k.validFrom > day || (k.validTo && k.validTo < day))
    return {
      ...base,
      state: "withheld",
      message:
        "The approved definition is outside its business-valid interval.",
    };
  const required = [
    "definition",
    "grain",
    "scope",
    "source",
    ...(k.type === "Metric" ? ["formula", "unit", "aggregation"] : []),
  ];
  const keys = [
    ...required,
    ...["dimensions", "logic", "exclusions"].filter((key) => valueOf(k, key)),
  ];
  let missing = false;
  for (const key of keys) {
    let selected: Fact | undefined;
    for (const p of s.providers.filter((x) => x.enabled)) {
      const cacheKey = [
        k.id,
        k.version,
        key,
        req.scope,
        p.id,
        req.reader,
        s.policyVersion,
        s.configVersion,
      ].join("|");
      const cached = s.cache.find(
        (e) => e.key === cacheKey && e.expiresAt > s.clock,
      );
      // Current policy and origin status were checked before cache. Provider enablement/order remains effective.
      if (cached && p.health !== "denied" && p.health !== "malformed") {
        selected = structuredClone(cached.fact);
        s.observations.push({
          knowledgeId: k.id,
          factId: key,
          providerId: p.id,
          at: s.clock,
          hit: true,
        });
        base.trace.push(
          `${key}: eligible cache from ${p.name}; original observation retained.`,
        );
        break;
      }
      const result = mockAdapter.read(s, p, k, key, req.reader);
      base.trace.push(`${key}: ${p.name} → ${result.status}`);
      if (result.status === "denied" || result.status === "error")
        return {
          ...base,
          facts: [],
          state: result.status === "denied" ? "denied" : "error",
          message: "Resolution blocked; no context values exported.",
        };
      if (result.status === "sufficient") {
        selected = result.fact;
        s.observations.push({
          knowledgeId: k.id,
          factId: key,
          providerId: p.id,
          at: s.clock,
          hit: false,
        });
        s.cache = s.cache.filter((e) => e.key !== cacheKey);
        s.cache.push({
          key: cacheKey,
          knowledgeId: k.id,
          fact: structuredClone(selected),
          retrievedAt: s.clock,
          expiresAt: s.clock + ttl(s, k, p).hours * HOUR,
          configVersion: s.configVersion,
          reader: req.reader,
          scope: req.scope,
        });
        break;
      }
    }
    if (selected) base.facts.push(selected);
    else if (required.includes(key)) missing = true;
  }
  return {
    ...base,
    state: missing ? "incomplete" : "sufficient",
    message: missing
      ? "Required evidence is missing. No complete definition packet is available."
      : "Required facts resolved with their original provenance. Declared semantics remain unverified.",
  };
}
export function updateProvider(s: State, id: string, patch: Partial<Provider>) {
  const p = s.providers.find((p) => p.id === id);
  if (!p) throw Error("Provider unavailable");
  if (
    patch.ttl !== undefined &&
    (!Number.isFinite(patch.ttl) || patch.ttl <= 0 || patch.ttl > 8760)
  )
    throw Error("TTL must be between 0 and 8760 hours");
  Object.assign(p, patch, { id: p.id });
  invalidate(s);
}
export function reorder(s: State, id: string, delta: number) {
  const i = s.providers.findIndex((p) => p.id === id),
    j = i + delta;
  if (i < 0 || j < 0 || j >= s.providers.length) return;
  [s.providers[i], s.providers[j]] = [s.providers[j], s.providers[i]];
  invalidate(s);
}
export function recommendation(s: State) {
  const recent = s.observations.filter((o) => !o.hit && s.clock - o.at <= HOUR);
  const groups = new Map<string, number>();
  for (const o of recent) {
    const key = `${o.knowledgeId}|${o.factId}|${o.providerId}`;
    groups.set(key, (groups.get(key) || 0) + 1);
  }
  const entry = [...groups].find(([, n]) => n >= 3);
  if (!entry || s.ttlDismissed) return null;
  const [knowledgeId, factId, providerId] = entry[0].split("|");
  const k = s.knowledge.find((x) => x.id === knowledgeId)!,
    p = s.providers.find((x) => x.id === providerId)!;
  return {
    knowledgeId,
    factId,
    providerId,
    count: entry[1],
    hours: Math.min(24, Math.max(1, ttl(s, k, p).hours * 2)),
  };
}
export function saveMapping(
  s: State,
  m: Omit<Mapping, "id" | "status">,
  reader: Reader,
) {
  const k = s.knowledge.find((k) => k.id === m.knowledgeId),
    a = s.assets.find((a) => a.id === m.assetId);
  if (!k || !a || !mayInspect(k, reader) || !mayInspect(a, reader))
    throw Error("Mapping endpoints unavailable");
  if (!m.evidence.trim() || !m.scope.trim() || !m.attribute.trim())
    throw Error("Attribute, scope and evidence are required");
  if (
    m.fieldPath &&
    !a.fields.some((f) => f.path === m.fieldPath) &&
    a.type !== "metric_view"
  )
    throw Error("Field is not declared on this asset");
  validateValidity(m.validFrom, m.validTo);
  const mapping = {
    ...m,
    id: `mapping-${s.sequence++}`,
    status: "Draft" as const,
  };
  s.mappings.push(mapping);
  return mapping;
}
export function propose(
  s: State,
  args: {
    originId: string;
    targetId: string;
    field: string;
    after: unknown;
    reason: string;
    audience?: string;
    dependencies?: string[];
  },
  reader: Reader = "steward",
) {
  const k = s.knowledge.find((k) => k.id === args.originId),
    t = s.targets.find((t) => t.id === args.targetId);
  const a = s.assets.find((a) => a.id === args.targetId);
  if (!k || !t || !mayInspect(k, reader) || (a && !mayInspect(a, reader)))
    throw Error("Proposal endpoints unavailable");
  if (!args.reason.trim()) throw Error("A reason is required");
  if (
    ![
      "description",
      "tags",
      "yaml",
      "serialized_space",
      "summary",
      "page",
      "projection",
    ].includes(args.field)
  )
    throw Error("Unsupported target field");
  if (JSON.stringify(t.content[args.field]) === JSON.stringify(args.after))
    throw Error("Make a change before proposing");
  const p: Proposal = {
    id: `proposal-${s.sequence++}`,
    originId: k.id,
    originRevision: k.version,
    targetId: t.id,
    field: args.field,
    before: structuredClone(t.content[args.field] ?? null),
    after: structuredClone(args.after),
    expectedRevision: t.revision,
    reason: args.reason,
    audience: args.audience || t.audience,
    state: "Draft",
    dependencies: args.dependencies || [],
    evidence: `${k.originId}@${k.version}`,
  };
  s.proposals.push(p);
  return p;
}
export function review(s: State, id: string) {
  const p = s.proposals.find((p) => p.id === id);
  if (!p || !["Draft", "Conflict"].includes(p.state))
    throw Error("Only a pending proposal can be reviewed");
  const k = s.knowledge.find((k) => k.id === p.originId);
  if (!k || k.version !== p.originRevision)
    throw Error("UOL revision changed. Create a new proposal.");
  p.state = "Reviewed";
  p.reviewedAt = s.clock;
  p.reviewDecision = "Approved for simulated delivery by demo steward";
}
export function deliver(s: State, ids: string[], reader: Reader) {
  for (const id of ids) {
    const p = s.proposals.find((p) => p.id === id);
    if (!p || !["Reviewed", "Failed"].includes(p.state)) continue;
    const t = s.targets.find((t) => t.id === p.targetId)!,
      k = s.knowledge.find((k) => k.id === p.originId)!;
    const a = s.assets.find((a) => a.id === p.targetId);
    let message = "";
    let acknowledged = false;
    let readback: "matches" | "mismatch" | "unknown" = "unknown";
    if (
      reader !== "steward" ||
      !mayInspect(k, reader) ||
      (a && !mayInspect(a, reader)) ||
      t.permission === "denied"
    ) {
      p.state = "Failed";
      message = "Permission denied; target unchanged.";
    } else if (k.version !== p.originRevision || k.status !== "Approved") {
      p.state = "Conflict";
      message = "Pinned UOL revision or approval changed.";
    } else if (
      p.audience !== t.audience ||
      (k.restricted && t.audience !== "Finance stewards")
    ) {
      p.state = "Failed";
      message = "Destination audience is unsuitable.";
    } else if (
      p.dependencies.some(
        (id) => s.proposals.find((x) => x.id === id)?.state !== "Verified",
      )
    ) {
      p.state = "Failed";
      message = "Required dependency has not been verified.";
    } else if (t.capability === "unsupported") {
      p.state = "Unsupported";
      message = "Create a reviewed handoff; no direct native adapter.";
    } else if (t.capability !== "permitted" || t.permission !== "permitted") {
      p.state = "Failed";
      message = "Capability or modification permission is unknown.";
    } else if (t.revision !== p.expectedRevision) {
      p.state = "Conflict";
      message = "Target changed after review. Reconcile before delivery.";
    } else if (t.failNext) {
      t.failNext = false;
      p.state = "Failed";
      message = "Simulated write failed. Retry this item only.";
    } else {
      new MockPublicationAdapter(s).conditionalSave(
        t.id,
        p.expectedRevision,
        p.field,
        p.after,
      );
      t.origins[p.field] = { originId: k.originId, revision: k.version };
      acknowledged = true;
      p.state = "Saved";
      if (t.mismatchNext) {
        t.mismatchNext = false;
        t.content[p.field] = "Divergent simulated read-back";
      }
      readback =
        JSON.stringify(t.content[p.field]) === JSON.stringify(p.after)
          ? "matches"
          : "mismatch";
      p.state = readback === "matches" ? "Verified" : "Mismatch";
      message =
        readback === "matches"
          ? "Target acknowledged and actual mock-store read-back matches."
          : "Save acknowledged; read-back differs.";
    }
    s.deliveries.push({
      id: `delivery-${s.sequence++}`,
      proposalId: id,
      at: s.clock,
      state: p.state,
      acknowledged,
      readback,
      indexing: "unknown",
      answerUse: "unknown",
      message,
    });
  }
}
export function rebase(s: State, id: string) {
  const p = s.proposals.find((p) => p.id === id)!;
  const t = s.targets.find((t) => t.id === p.targetId)!;
  if (p.field === "serialized_space") {
    throw Error(
      "Full replacement conflict: reopen Genie editor to preserve the latest complete configuration.",
    );
  }
  p.before = structuredClone(t.content[p.field] ?? null);
  p.expectedRevision = t.revision;
  p.state = "Draft";
  p.reviewDecision = undefined;
}
export function projection(s: State, id: string, choice: string, simulation = true) {
  const full = path(s, id);
  const names = full.slice(1).map((d) => d.name);
  const sub =
    choice === "flatten" ? names.slice(1).join("-") || null : names[1] || null;
  return {
    uolId: id,
    fullPath: full.map((d) => d.name).join(" / "),
    choice,
    nativeDomain: choice === "uol-only" ? null : names[0] || null,
    nativeSubdomain: choice === "uol-only" ? null : sub,
    tags:
      choice === "uol-only" || !names.length
        ? {}
        : { [names[0]]: "", ...(sub ? { [`${names[0]}/${sub}`]: "" } : {}) },
    lostDepth: Math.max(0, names.length - 2),
    collision: simulation ? s.domains.some((d) => d.id !== id && d.name === sub) : null,
    pageDomain: s.pages.find((p) => p.domain === id)?.domain ?? null,
  };
}
export function exportEnvelope(value: unknown, simulation: boolean) {
  return { schema_version: 1, simulation, payload: value };
}
export function workspaceExport(s: State, reader: Reader, simulation: boolean) {
  const visibleKnowledge = knowledgeView(s, reader),
    visibleAssets = assetView(s, reader);
  const knowledgeIds = new Set(visibleKnowledge.map((k) => k.id));
  const assetIds = new Set(visibleAssets.map((a) => a.id));
  const knowledge = visibleKnowledge.map((k) => ({
    ...k, related: k.related.filter((id) => knowledgeIds.has(id)),
  }));
  const assets = visibleAssets.map((a) => ({
    ...a,
    knowledgeIds: a.knowledgeIds.filter((id) => knowledgeIds.has(id)),
    parent: a.parent && assetIds.has(a.parent) ? a.parent : null,
  }));
  const ids = new Set([...knowledgeIds, ...assetIds]);
  return exportEnvelope({
    domains: s.domains,
    knowledge,
    assets,
    mappings: s.mappings.filter(
      (m) => ids.has(m.assetId) && ids.has(m.knowledgeId),
    ),
    relationships: s.relationships.filter(
      (r) => ids.has(r.source) && ids.has(r.target),
    ),
    providers: s.providers,
  }, simulation);
}
export function createKnowledge(
  s: State,
  domain: string,
  name: string,
  type: string,
  definition: string,
) {
  if (
    !name.trim() ||
    !definition.trim() ||
    !s.domains.some((d) => d.id === domain)
  )
    throw Error("Name, definition and domain are required");
  const id = `knowledge-${s.sequence++}`;
  const k: Knowledge = {
    id,
    name: name.trim(),
    type,
    domain,
    memberships: [],
    summary: definition,
    definition,
    scope: "Enterprise",
    grain: "Not yet defined",
    status: "Draft",
    origin: "Curated",
    version: 1,
    owner: String(inherited(s, domain, "owner").value),
    source: "Authored definitions",
    sourcePath: `local/${id}.yaml`,
    effective: "Pending approval",
    validFrom: new Date(s.clock).toISOString().slice(0, 10),
    synonyms: [],
    related: [],
    originId: `uol:${id}`,
    history: [],
  };
  s.knowledge.push(k);
  return k;
}
export function updateRelationship(
  s: State,
  id: string,
  patch: { label: string; scope: string; cardinality: string },
) {
  const r = s.relationships.find((r) => r.id === id);
  if (!r) throw Error("Edit this mapping through the mapping workbench");
  if (!patch.label.trim() || !patch.scope.trim())
    throw Error("Label and scope are required");
  Object.assign(r, patch, {
    approval: "Draft",
    provenance: "UOL session relationship edit",
  });
}

/** Native boundary: the only target write adapter in this build is in-memory. */
export class MockPublicationAdapter implements PublicationAdapter {
  constructor(private state: State) {}
  readTarget(id: string) {
    return this.state.targets.find((t) => t.id === id);
  }
  conditionalSave(id: string, revision: number, field: string, value: unknown) {
    const target = this.readTarget(id);
    if (!target || target.revision !== revision)
      throw Error("Target precondition failed");
    target.content[field] = structuredClone(value);
    target.revision++;
    return target;
  }
}

export function domainEditError(state: State, domain: Domain | undefined, name: string, parent: string | null) {
  if (!name.trim()) return "Domain name is required.";
  if (domain && parent && path(state, parent).some(d => d.id === domain.id)) return "A domain cannot move into itself or its descendants.";
  if (state.domains.some(d => d.id !== domain?.id && d.parent === parent && d.name.toLowerCase() === name.trim().toLowerCase())) return "A sibling domain already uses this name.";
  return "";
}
export function comparableMeanings(state: State, reader: Reader) {
  const visible = knowledgeView(state, reader);
  const name = visible.find(k => visible.filter(other => other.name === k.name).length > 1)?.name;
  return name ? visible.filter(k => k.name === name) : [];
}
export function mappingDefaults(state: State, reader: Reader, assetId?: string, fieldPath?: string) {
  const assets = assetView(state, reader).filter(a => !["catalog", "schema"].includes(a.type));
  const asset = assets.find(a => a.id === assetId) || assets[0];
  const objects = knowledgeView(state, reader);
  const knowledge = objects.find(k => asset?.knowledgeIds.includes(k.id)) || objects[0];
  return { asset: asset?.id || "", field: fieldPath || "", knowledge: knowledge?.id || "", scope: knowledge?.scope || "", from: new Date(state.clock).toISOString().slice(0, 10) };
}
export function mappingFields(state: State, asset: State["assets"][number] | undefined) {
  const measures = asset?.type === "metric_view" ? state.targets.find(t => t.id === asset.id)?.content.yaml?.measures : [];
  return [...new Set([...(asset?.fields || []).map(f => f.path), ...(Array.isArray(measures) ? measures.flatMap(m => typeof m?.name === "string" ? [m.name] : []) : [])])];
}
export function projectionPresentation(state: State, id: string, choice: string, simulation: boolean) {
  const plan = projection(state, id, choice);
  return { inventory: simulation ? ["Customer", "Finance", "Operations"] : [], collisionLabel: simulation ? (plan.collision ? "Review required" : "No collision in fixtures") : "Not verified against native inventory" };
}
