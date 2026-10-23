import unittest

from dbt_skills.modelling_naming import NamingError, NamingRule, resolve_name


class NamingTests(unittest.TestCase):
    def test_unicode_controls_are_rejected(self):
        for character in ("\u0085", "\u009b", "\u202e", "\u200b"):
            with self.subTest(character=repr(character)), self.assertRaises(NamingError):
                resolve_name(self.rule(), {"source": "x" + character, "concept": "customer"})

    def rule(self, template="stg_{source}_{concept}.sql", **kwargs):
        return NamingRule(
            rule_id="staging-file", template=template,
            tokens={"source": "Which source system?", "concept": "Which business concept?"},
            provenance={"document": "modelling.yml", "revision": "abc", "locator": "naming.staging"},
            **kwargs,
        )

    def test_renders_source_concept_and_preserves_provenance(self):
        result = resolve_name(self.rule(), {"source": "xyz", "concept": "customer"})
        self.assertEqual(result["value"], "stg_xyz_customer.sql")
        self.assertEqual(result["provenance"]["revision"], "abc")

    def test_arbitrary_tokens_order_and_directory(self):
        rule = NamingRule("custom", "models/{domain}/{object}__{system}.sql",
                          {"domain": "Domain?", "object": "Object?", "system": "System?"},
                          {"document": "team.yml"})
        self.assertEqual(resolve_name(rule, {"domain": "sales", "object": "order", "system": "erp"})["value"],
                         "models/sales/order__erp.sql")

    def test_missing_inputs_are_questions_without_partial_output(self):
        result = resolve_name(self.rule(), {"source": "xyz"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("value", result)
        self.assertEqual(result["questions"], [{"token": "concept", "question": "Which business concept?"}])

    def test_fixed_binding_cannot_be_overridden(self):
        rule = self.rule(bindings={"source": "xyz"})
        self.assertEqual(resolve_name(rule, {"concept": "customer"})["value"], "stg_xyz_customer.sql")
        with self.assertRaises(NamingError):
            resolve_name(rule, {"source": "other", "concept": "customer"})

    def test_rejects_expressions_undeclared_and_malformed_tokens(self):
        for template in ("{source.upper}", "{source[0]}", "{source!r}", "{source:>2}",
                         "{{source}}", "{missing}", "{source", "source}"):
            with self.subTest(template=template), self.assertRaises(NamingError):
                resolve_name(self.rule(template), {})

    def test_rejects_unsafe_paths_and_input_segments(self):
        for value in ("../secrets", "a/b", "a\\b", "..", "", "x\n", "c:", "{concept}"):
            with self.subTest(value=value), self.assertRaises(NamingError):
                resolve_name(self.rule(), {"source": value, "concept": "customer"})
        for template in ("/tmp/{source}", "../{source}", "a/../{source}", "C:/{source}", "a\\{source}"):
            with self.subTest(template=template), self.assertRaises(NamingError):
                resolve_name(self.rule(template), {"source": "xyz"})

    def test_unknown_input_is_not_silently_ignored(self):
        with self.assertRaises(NamingError):
            resolve_name(self.rule(), {"soruce": "xyz"})

    def test_requires_provenance(self):
        with self.assertRaises(NamingError):
            resolve_name(NamingRule("id", "constant", {}, {}), {})
