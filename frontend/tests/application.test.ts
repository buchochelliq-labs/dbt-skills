import test from "node:test";
import assert from "node:assert/strict";
import { seed } from "../src/fixtures.ts";
import {
  path,
  createDomain,
  updateDomain,
  inherited,
  ttl,
  resolve,
  approve,
  revise,
  reorder,
  updateProvider,
  HOUR,
  recommendation,
  saveMapping,
  propose,
  review,
  deliver,
  rebase,
  projection,
  workspaceExport,
  knowledgeView,
  assetView,
} from "../src/services.ts";
import { validateMetric } from "../src/nativeValidation.ts";
import { stringify } from "yaml";
const req = (
  objectId = "active-customer",
  scope = "Service",
  reader: "steward" | "restricted" = "steward",
) => ({ question: "", objectId, scope, reader });
test("create fourth-level domain, inherit, override and reset", () => {
  const s = seed();
  const d = createDomain(s, "Advocacy", "lifecycle", "Customer advocacy");
  assert.equal(path(s, d.id).length, 4);
  assert.equal(inherited(s, d.id, "owner").value, "Customer Analytics");
  updateDomain(s, d.id, { owner: "Advocacy team" });
  assert.equal(inherited(s, d.id, "owner").value, "Advocacy team");
  updateDomain(s, d.id, { owner: null });
  assert.equal(inherited(s, d.id, "owner").value, "Customer Analytics");
});
test("rename/move preserves identity and references; cycles and invalid parents rejected", () => {
  const s = seed();
  updateDomain(s, "retention", { name: "Loyalty", parent: "service" });
  assert.equal(
    s.knowledge.find((k) => k.id === "churn-rate")!.domain,
    "retention",
  );
  assert.equal(path(s, "retention").at(-2)?.id, "service");
  assert.throws(
    () => updateDomain(s, "operations", { parent: "retention" }),
    /descendants/,
  );
  assert.throws(
    () => updateDomain(s, "retention", { parent: "missing" }),
    /existing/,
  );
});
test("TTL provider default not masked by enterprise fallback", () => {
  const s = seed(),
    p = s.providers[2];
  assert.equal(ttl(s, s.knowledge[0], p).hours, 12);
  assert.equal(
    ttl(
      s,
      s.knowledge.find((k) => k.id === "churn-rate")!,
      p,
    ).hours,
    6,
  );
  s.knowledge[0].ttl = 1;
  assert.equal(ttl(s, s.knowledge[0], p).hours, 1);
});
test("unscoped same label is ambiguous; scoped meanings are distinct", () => {
  const s = seed();
  assert.equal(
    resolve(s, {
      question: "Active customer",
      scope: "Unspecified",
      reader: "steward",
    }).state,
    "ambiguous",
  );
  const a = resolve(s, {
      question: "Active customer",
      scope: "Service",
      reader: "steward",
    }),
    b = resolve(s, {
      question: "Active customer",
      scope: "Billing",
      reader: "steward",
    });
  assert.equal(a.state, "sufficient");
  assert.equal(b.state, "sufficient");
  assert.notEqual(a.facts[0].value, b.facts[0].value);
});
test("draft has no exported definition values", () => {
  const s = seed(),
    r = resolve(s, req("overdue", "Billing"));
  assert.equal(r.state, "withheld");
  assert.deepEqual(r.facts, []);
  assert.ok(!JSON.stringify(r).includes("contractually"));
});
test("approving inferred rule preserves inferred origin", () => {
  const s = seed();
  approve(s, "suspended-rule");
  updateProvider(s, "openmetadata", { health: "healthy" });
  const r = resolve(s, req("suspended-rule"));
  assert.equal(r.state, "sufficient");
  assert.equal(r.facts[0].evidence.origin, "Inferred");
});
test("required metric formula missing produces incomplete context", () => {
  const s = seed();
  s.knowledge.find((k) => k.id === "active-customers")!.formula = "";
  assert.equal(resolve(s, req("active-customers")).state, "incomplete");
});
test("authored replica order preserves actual provenance and original identity", () => {
  const s = seed();
  reorder(s, "authored", -1);
  reorder(s, "authored", -1);
  reorder(s, "authored", -1);
  const r = resolve(s, req());
  assert.equal(r.facts[0].evidence.providerId, "authored");
  assert.equal(r.facts[0].evidence.replica, true);
  assert.equal(r.facts[0].evidence.originId, "uol:term:active-customer");
});
test("paused only provider cannot manufacture evidence", () => {
  const s = seed();
  updateProvider(s, "uc-customer", { enabled: false });
  assert.equal(resolve(s, req("active-customers")).state, "incomplete");
});
test("restricted reader cannot bypass denial through cache, scope or replica", () => {
  const s = seed();
  assert.equal(resolve(s, req("mrr", "Billing")).state, "sufficient");
  for (const scope of ["Billing", "Service", "Unspecified"]) {
    const r = resolve(s, req("mrr", scope, "restricted"));
    assert.equal(r.state, "denied");
    assert.deepEqual(r.facts, []);
  }
});
test("origin authorization denial blocks earlier authored replica", () => {
  const s = seed();
  resolve(s, req());
  reorder(s, "authored", -1);
  reorder(s, "authored", -1);
  reorder(s, "authored", -1);
  updateProvider(s, "uc-customer", { health: "denied" });
  assert.equal(resolve(s, req()).state, "denied");
});
test("cache hit retains observation time; expiry forces retrieval", () => {
  const s = seed();
  const a = resolve(s, req());
  s.clock += HOUR;
  const b = resolve(s, req());
  assert.equal(a.facts[0].evidence.observedAt, b.facts[0].evidence.observedAt);
  assert.ok(b.trace.some((t) => t.includes("eligible cache")));
  s.clock += 25 * HOUR;
  const c = resolve(s, req());
  assert.notEqual(
    c.facts[0].evidence.observedAt,
    a.facts[0].evidence.observedAt,
  );
});
test("TTL recommendation observes repeated retrieval but does not apply itself", () => {
  const s = seed();
  for (let i = 0; i < 3; i++) {
    s.cache = [];
    resolve(s, req());
  }
  const rec = recommendation(s);
  assert.equal(rec?.count, 3);
  assert.equal(s.knowledge[0].ttl, undefined);
});
test("provider malformed evidence blocks; recoverable outage falls through explicit replica", () => {
  const s = seed();
  updateProvider(s, "uc-customer", { health: "malformed" });
  assert.equal(resolve(s, req()).state, "error");
  updateProvider(s, "uc-customer", { health: "outage" });
  const r = resolve(s, req());
  assert.equal(r.state, "sufficient");
  assert.equal(r.facts[0].evidence.providerId, "authored");
});
test("hidden and nonexistent are indistinguishable; all export graphs omit hidden identity", () => {
  const s = seed();
  assert.deepEqual(
    resolve(s, req("private-concept")),
    resolve(s, req("nonexistent")),
  );
  const out = JSON.stringify(workspaceExport(s, "restricted", true));
  for (const value of [
    "Confidential acquisition",
    "finance.private",
    "Hidden synthetic",
    "Monthly recurring revenue",
  ])
    assert.ok(!out.includes(value));
  assert.ok(!knowledgeView(s, "restricted").some((k) => k.hidden));
  assert.ok(!assetView(s, "restricted").some((a) => a.hidden));
});
test("mapping validates separate containing asset and field identity", () => {
  const s = seed();
  const m = saveMapping(
    s,
    {
      knowledgeId: "customer-entity",
      assetId: "customers",
      fieldPath: "customer_id",
      attribute: "identity",
      type: "concept attribute",
      scope: "Enterprise",
      validFrom: "2026-10-01",
      evidence: "Contract",
    },
    "steward",
  );
  assert.equal(m.assetId, "customers");
  assert.equal(m.fieldPath, "customer_id");
  assert.equal(m.status, "Draft");
  assert.throws(
    () => saveMapping(s, { ...m, fieldPath: "missing" }, "steward"),
    /Field/,
  );
});
test("typed edges distinguish subtype composition lineage and semantic dependency", () => {
  const s = seed();
  for (const type of ["is_a", "part_of", "lineage", "dependency", "join"])
    assert.ok(s.relationships.some((e) => e.type === type));
});
test("deep projection retains canonical identity and Page domain", () => {
  const s = seed();
  const p = projection(s, "retention", "flatten");
  assert.equal(p.uolId, "retention");
  assert.equal(p.nativeSubdomain, "Lifecycle-Retention");
  assert.equal(s.pages[0].domain, "lifecycle");
  assert.equal(projection(s, "retention", "uol-only").nativeDomain, null);
});
function proposal(
  s: ReturnType<typeof seed>,
  targetId = "customers",
  field = "description",
  after: any = "Reviewed customer description",
) {
  return propose(s, {
    originId: "customer-entity",
    targetId,
    field,
    after,
    reason: "Align definition",
  });
}
test("session edits pin exact field before/after and UOL revision", () => {
  const s = seed();
  const p = proposal(s);
  assert.equal(
    p.before,
    s.targets.find((t) => t.id === "customers")!.content.description,
  );
  assert.equal(p.originRevision, 4);
  assert.equal(p.state, "Draft");
});
test("one of three selected changes leaves others pending", () => {
  const s = seed();
  const ps = [proposal(s), proposal(s, "accounts"), proposal(s, "services")];
  ps.forEach((p) => review(s, p.id));
  deliver(s, [ps[0].id], "steward");
  assert.deepEqual(
    ps.map((p) => p.state),
    ["Verified", "Reviewed", "Reviewed"],
  );
  assert.equal(s.deliveries.length, 1);
  assert.equal(s.deliveries[0].indexing, "unknown");
});
test("target drift conflicts and preserves unrelated content", () => {
  const s = seed(),
    p = proposal(s),
    t = s.targets.find((t) => t.id === "customers")!;
  review(s, p.id);
  t.revision++;
  t.content.note = "Other steward";
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Conflict");
  assert.equal(t.content.note, "Other steward");
  assert.equal(t.content.description, p.before);
  rebase(s, p.id);
  assert.equal(p.state, "Draft");
});
test("readback compares actual mock store; retry does not republish successes", () => {
  const s = seed(),
    p = proposal(s),
    t = s.targets.find((t) => t.id === "customers")!;
  review(s, p.id);
  t.failNext = true;
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Failed");
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Verified");
  const revision = t.revision;
  deliver(s, [p.id], "steward");
  assert.equal(t.revision, revision);
  assert.deepEqual(t.origins.description, {
    originId: "uol:concept:customer",
    revision: 4,
  });
});
test("divergent readback never becomes Verified", () => {
  const s = seed(),
    p = proposal(s);
  review(s, p.id);
  s.targets.find((t) => t.id === "customers")!.mismatchNext = true;
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Mismatch");
  assert.equal(s.deliveries[0].acknowledged, true);
});
test("unsupported destination produces no native write", () => {
  const s = seed(),
    p = propose(s, {
      originId: "lifecycle-page",
      targetId: "page-lifecycle",
      field: "summary",
      after: "New summary",
      reason: "Review Page",
    });
  review(s, p.id);
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Unsupported");
  assert.equal(s.targets.find((t) => t.id === "page-lifecycle")!.revision, 1);
});
test("editing approved knowledge preserves history, makes draft, invalidates cache", () => {
  const s = seed();
  resolve(s, req());
  const before = s.knowledge[0].definition;
  revise(s, "active-customer", { definition: "Changed meaning" });
  assert.equal(s.knowledge[0].history[0].definition, before);
  assert.equal(s.knowledge[0].status, "Draft");
  assert.equal(s.cache.length, 0);
});
test("Genie full replacement preserves unrelated sections and external setting", () => {
  const s = seed(),
    t = s.targets.find((t) => t.kind === "genie")!;
  const after = structuredClone(t.content.serialized_space);
  after.instructions.text_instructions[0].content = ["Changed instruction"];
  const p = propose(s, {
    originId: "active-customer",
    targetId: t.id,
    field: "serialized_space",
    after,
    reason: "Change instruction",
  });
  review(s, p.id);
  deliver(s, [p.id], "steward");
  assert.equal(p.state, "Verified");
  assert.equal(t.content.unrelated_setting, "Preserve this existing setting");
  assert.deepEqual(t.content.serialized_space.benchmarks, after.benchmarks);
});
test("metric YAML rejects invented native keys and old runtime", () => {
  const s = seed(),
    text = stringify(
      s.targets.find((t) => t.id === "active-view")!.content.yaml,
    );
  assert.deepEqual(validateMetric(text, "17.3").errors, []);
  assert.ok(validateMetric(text, "16.4").errors.length);
  assert.ok(
    validateMetric(text + "\nuol_concept: x\n", "17.3").errors.some((e) =>
      e.includes("uol_concept"),
    ),
  );
  assert.ok(validateMetric("version: [", "17.3").errors.length);
});
