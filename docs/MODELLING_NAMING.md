# Dynamic naming primitive

This is the first implementation slice of #37. It is a Python API, not yet a
YAML policy loader or Copilot tool. It does not automatically select rules,
infer standards, approve deviations or write models.

```python
from dbt_skills.modelling_naming import NamingRule, resolve_name

rule = NamingRule(
    rule_id="staging-file",
    template="models/{layer}/{source}/{layer}_{source}_{concept}.sql",
    tokens={
        "layer": "Which modelling layer?",
        "source": "Which source system?",
        "concept": "Which business concept?",
    },
    bindings={"layer": "stg"},
    provenance={
        "document": "modelling.yml",
        "revision": "<content hash or immutable revision>",
        "locator": "naming.staging-file",
    },
)
result = resolve_name(rule, {"source": "xyz", "concept": "customer"})
# result["value"] == "models/stg/xyz/stg_xyz_customer.sql"
```

Tokens have no built-in business meaning. Teams choose their names, order,
separators and literal directory structure. Token names use letters, digits and
underscores and cannot start with a digit. Values are single literal path
segments; directory separators belong in the template. Values retain their case.
Fixed bindings cannot be overridden by supplied values. Invalid inputs raise
`NamingError` without echoing their values. Templates do not evaluate expressions.

If `concept` is omitted, the result has `status: needs_clarification` and a
`questions` list containing its token and configured question. No partially
rendered value is returned. Hosts decide how to ask the question and call again.
Every successful resolution or clarification carries the rule ID and supplied
provenance. Callers must supply trustworthy source metadata; the primitive does
not verify that a policy was approved or that a revision exists.

Path validation is lexical and rejects absolute paths, traversal segments,
backslashes, control characters and executable placeholders. It does not enforce
OS-specific reserved names, SQL identifier restrictions, extension conventions,
case-sensitive collisions, symlink containment or existing-file protection.
Future file-writing tools must enforce those independently. Templates and outputs
are bounded to 4096 characters; token values to 1024; mappings to 256 entries.

Remaining #37 work includes versioned YAML/JSON Schema, scoped modelling styles
and 3NF/4NF targets, observations and decisions, provenance validation, and rule
selection/conflict handling. #38 adds project scanning and guided onboarding.
See [the architecture](ARCHITECTURE.md) for the agreed delivery order.
