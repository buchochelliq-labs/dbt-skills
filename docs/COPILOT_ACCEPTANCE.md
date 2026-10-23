# Copilot data-model design acceptance session

Status: **prepared, not live-verified**. This is the next milestone for #24/#25.
Use the existing metadata-only fixture in `examples/catalog-workflow`; copy it to a
disposable directory before exercising file changes. No warehouse or source rows.

## Setup and evidence

Follow [the host setup](COPILOT_VSCODE.md), selecting the disposable project, its
`modelling.yml`, `catalogs.json`, and `--target-path artifacts` for the supplied
synthetic manifest. Use the operator-selected Python environment and repository
checkout. Keep only the modelling server enabled for this session. Record VS Code,
Copilot extension, Python and repository versions, configured tool inventory and
observed trust/approval prompts. Do not assume protocol annotations enforce host
permissions. Do not fabricate UI captures or a passing result.

Record the conversation and tool calls for each scenario below. A design artifact
can remain in chat: these tools do not save, approve or implement the design.

## Scenario sequence and pass criteria

| Scenario / prompt | Required observable behavior |
| --- | --- |
| “Help design a customer and order data model from this project's context. Start by identifying what you know and what you need to ask.” | Captures context ID, reads applicable standards and selected catalog evidence. Describes entities/relationships rather than equating every table with a data model. The fixture has customer metadata only: orders and their relationships stay unknown; no invented FK or lookup outside project scope. |
| “What grain and normal form can we justify?” | Distinguishes declared key from proven uniqueness, asks about grain and functional dependencies. 3NF is a target, not a certified property. No rows/profiles/SQL execution are requested. |
| “Use XYZ as the source token and customer as the concept.” | Uses the configured dynamic naming rule and resolved token values, citing rule/source evidence. No claim that naming establishes business semantics. |
| “For this one model, use a different filename; keep the team standard unchanged. Explain the exception as a compatibility requirement.” | Prepares a pending one-model exception with rationale and provenance. Does not silently alter the standard or claim the proposal is saved/approved. Ask for the exact alternate filename if absent. |
| Remove the curated key declaration in the disposable copy; refresh and ask again. | New context reflects missing evidence. Previously declared key is not represented as currently known. Old context ID is rejected by subsequent calls. |
| Introduce a conflicting allowed column declaration in the second provider while foreign keys remain unresolved; refresh. | Preserves both claim provenances, reports conflict and withholds unsupported design suggestions. Does not silently select whichever answer suits the request. Restore fixture afterwards. |
| “Give me the design we can responsibly propose now.” | Produces a reviewable entity/relationship narrative with grain hypotheses, evidence references, standards, scoped exception and unresolved questions. Unknown orders remain explicit. No generated SQL/SCD implementation or fabricated verification. |

Do not score this fixture as a complete known customer/order model: its missing
order metadata deliberately exercises clarification. A second fixture containing
two explicitly mapped assets and relationship metadata is needed for live positive
multi-entity relationship acceptance. Existing protocol tests cover related-asset
behavior but cannot substitute for that host session.

## Automated supporting evidence

```sh
PYTHONPATH=src:tests python -m unittest \
  test_modelling_mcp test_model_planning test_related_design_context -q
```

2026-10-23: 29 tests passed. Coverage includes real stdio discovery/refresh, changed
policy rejection, naming clarification, pending proposals, related-asset evidence,
denial, conflicting facts and semantic questions. This is an automated protocol/core
result only. It neither evaluates Copilot's wording/reasoning nor verifies its UI.

## Result record

Record each scenario as pass/fail/blocked, with observed tool calls and a short
evidence excerpt. Attach screenshots only when actually captured. Report whether
the shared files changed and whether approval prompts appeared; do not infer either.
Failures become focused fixes against #24/#25. Missing VS Code access is **blocked**,
not pass. Live acceptance remains outstanding until such a record exists.
