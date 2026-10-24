import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { seed } from "../src/fixtures.ts";
import { domainKnowledge, exportEnvelope } from "../src/services.ts";
import { MappingReviewActions } from "../src/MappingReviewActions.tsx";

// These payload labels must come from the authenticated server's mode. A real
// workspace is not a simulation merely because its export is prepared locally.
test("review exports retain explicit real-workspace mode", () => {
  assert.deepEqual(exportEnvelope({ reviewRequired: true }, false), {
    schema_version: 1,
    simulation: false,
    payload: { reviewRequired: true },
  });
});

test("review exports retain explicit simulation mode", () => {
  assert.deepEqual(exportEnvelope({ reviewRequired: true }, true), {
    schema_version: 1,
    simulation: true,
    payload: { reviewRequired: true },
  });
});

function membershipState() {
  const state = seed();
  const base = state.knowledge.find((k) => k.id === "customer-entity")!;
  state.knowledge = [
    { ...base, id: "owner", domain: "customer", memberships: [] },
    { ...base, id: "member", domain: "service", memberships: ["customer", "lifecycle"] },
    { ...base, id: "child", domain: "lifecycle", memberships: [] },
    { ...base, id: "member-child", domain: "service", memberships: ["lifecycle"] },
    { ...base, id: "overlap", domain: "lifecycle", memberships: ["customer"] },
    { ...base, id: "unrelated", domain: "service", memberships: [] },
  ];
  return state;
}

test("direct domain lists include primary ownership and additional membership", () => {
  const state = membershipState();
  assert.deepEqual(domainKnowledge(state, "steward", "customer", false).map(k => k.id), ["owner", "member", "overlap"]);
});

test("descendant inclusion applies to both ownership and membership without duplicates", () => {
  const state = membershipState();
  assert.deepEqual(domainKnowledge(state, "steward", "customer", true).map(k => k.id), ["owner", "member", "child", "member-child", "overlap"]);
});

test("direct browsing excludes records attached only to descendants or unrelated domains", () => {
  const state = membershipState();
  assert.deepEqual(domainKnowledge(state, "steward", "enterprise", false), []);
  assert.deepEqual(domainKnowledge(state, "steward", "lifecycle", false).map(k => k.id), ["member", "child", "member-child", "overlap"]);
});

test("domain membership browsing preserves ownership and respects visibility", () => {
  const state = membershipState();
  state.knowledge[1].restricted = true;
  state.knowledge[4].hidden = true;
  const before = structuredClone(state);
  assert.deepEqual(domainKnowledge(state, "restricted", "customer", false).map(k => k.id), ["owner"]);
  assert.deepEqual(state, before);
});

test("mapping review is available after restored source evidence requires a new review", () => {
  const markup = renderToStaticMarkup(React.createElement(MappingReviewActions, {
    status: "Needs review", onReview: () => {}, onRemove: () => {},
  }));
  assert.match(markup, /<button[^>]*>Review mapping<\/button>/);
  assert.doesNotMatch(markup, /Remove draft/);
});

test("approved mappings have no duplicate review or draft-removal action", () => {
  const markup = renderToStaticMarkup(React.createElement(MappingReviewActions, {
    status: "Approved", onReview: () => {}, onRemove: () => {},
  }));
  assert.equal(markup, "");
});

test("retired provider cannot expose an enable action", async () => {
  const { ProviderToggle } = await import("../src/ProviderToggle.tsx");
  const markup = renderToStaticMarkup(React.createElement(ProviderToggle, {
    provider: { ...seed().providers[0], enabled: false, retired: true },
    onToggle: () => {},
  }));
  assert.doesNotMatch(markup, /<button/);
  assert.match(markup, /Removed from server configuration/);
});

test("root domain edits retain a null parent and do not report a self-cycle", async () => {
  const { domainEditError } = await import("../src/services.ts");
  const state = seed();
  assert.equal(domainEditError(state, state.domains[0], "Renamed enterprise", null), "");
  assert.match(domainEditError(state, state.domains[0], "Renamed enterprise", "customer"), /descendant|root/i);
});

test("live mapping defaults and measure choices come only from visible workspace metadata", async () => {
  const { mappingDefaults, mappingFields } = await import("../src/services.ts");
  const state = seed();
  state.knowledge = [{...state.knowledge[0], id: "real-term", scope: "Orders"}];
  state.assets = [{...state.assets[0], id: "real-metric", type: "metric_view", fields: []}];
  state.targets = [{...state.targets[0], id: "real-metric", content: {yaml: {measures: [{name: "order_total"}]}}}];
  const defaults = mappingDefaults(state, "steward");
  assert.equal(defaults.knowledge, "real-term");
  assert.equal(defaults.asset, "real-metric");
  assert.equal(defaults.scope, "Orders");
  assert.deepEqual(mappingFields(state, state.assets[0]), ["order_total"]);
  state.targets = [];
  assert.deepEqual(mappingFields(state, state.assets[0]), []);
});

test("comparison affordance requires actual visible definitions sharing a name", async () => {
  const { comparableMeanings } = await import("../src/services.ts");
  const state = seed();
  assert.equal(comparableMeanings(state, "steward").length, 2);
  assert.equal(comparableMeanings(state, "restricted").length, 0);
  state.knowledge = [{...state.knowledge[0], id: "real-term", name: "Order"}];
  assert.deepEqual(comparableMeanings(state, "steward"), []);
});

test("empty or malformed native instruction blocks can be displayed without crashing", async () => {
  const { genieInstructionText } = await import("../src/nativeValidation.ts");
  for (const value of [undefined, {}, {instructions:{}}, {instructions:{text_instructions:[]}}, {instructions:{text_instructions:[{content:null}]}}])
    assert.equal(genieInstructionText(value), "");
  assert.equal(genieInstructionText({instructions:{text_instructions:[{content:["One", "Two"]}]}}), "One\nTwo");
});

test("live domain projection makes no fictional inventory or native collision claim", async () => {
  const { projectionPresentation } = await import("../src/services.ts");
  const state = seed();
  const live = projectionPresentation(state, "retention", "ancestor", false);
  assert.deepEqual(live.inventory, []);
  assert.equal(live.collisionLabel, "Not verified against native inventory");
  assert.equal(projectionPresentation(state, "retention", "ancestor", true).inventory.length, 3);
});

test("live projection exports leave native collision verification unknown", async () => {
  const { projection } = await import("../src/services.ts");
  const state = seed();
  const live = exportEnvelope(projection(state, "retention", "ancestor", false), false);
  assert.equal((live.payload as { collision: unknown }).collision, null);
  assert.equal(live.simulation, false);
  assert.equal(typeof projection(state, "retention", "ancestor", true).collision, "boolean");
});

test("root domain projection has no native assignment or undefined tag", async () => {
  const { projection } = await import("../src/services.ts");
  for (const simulation of [false, true]) {
    for (const choice of ["ancestor", "flatten", "uol-only"]) {
      const plan = projection(seed(), "enterprise", choice, simulation);
      assert.equal(plan.nativeDomain, null);
      assert.equal(plan.nativeSubdomain, null);
      assert.deepEqual(plan.tags, {});
      assert.equal(plan.uolId, "enterprise");
    }
  }
});
