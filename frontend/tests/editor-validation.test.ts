import test from "node:test";
import assert from "node:assert/strict";
import { validateMetric } from "../src/nativeValidation";
const prefix = "version: 1.1\nsource: customer.core.customers\n";
test("malformed metric form inputs are rejected without throwing", () => {
  for (const suffix of [
    "measures: [null]",
    "measures: [{name: total, expr: COUNT(*), synonyms: nope}]",
    "comment: []\nmeasures: [{name: total, expr: COUNT(*)}]",
    "measures: [{name: total, expr: COUNT(*), display_name: []}]",
    "measures: [{name: total, expr: COUNT(*), format: false}]",
  ])
    assert.ok(validateMetric(prefix + suffix, "17.3").errors.length, suffix);
});
test("valid metric synonyms and formatting remain accepted", () => {
  assert.deepEqual(
    validateMetric(
      prefix +
        "measures:\n  - name: total\n    expr: COUNT(*)\n    synonyms: [count]\n    format: {type: number}",
      "17.3",
    ).errors,
    [],
  );
});
