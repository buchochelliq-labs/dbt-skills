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
