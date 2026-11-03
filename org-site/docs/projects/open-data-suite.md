# OpenDataSuite

**A Rust-first, provider-neutral control plane for analytics engineering.** It starts
with dbt and Databricks, and it explains every decision it makes.

!!! warning "Pre-alpha"
    OpenDataSuite is very experimental. Commands and formats may change between releases.

[Read the documentation](https://buchochelliq-labs.github.io/open-data-suite/){ .md-button .md-button--primary }
[open-data-suite on GitHub](https://github.com/buchochelliq-labs/open-data-suite){ .md-button }

## Highlights

- `ods state build` runs `dbt build` only on what changed (code or upstream data) and explains why each node ran.
- `ods serve` is a read-only dashboard showing the plan, the runs, column-level lineage and the catalog.
- An MCP server exposes project context to coding agents.

## Install

```sh
pip install opendatasuite
# or
brew install buchochelliq-labs/tap/ods
```

## Related repositories

| Repository | Role |
|---|---|
| [open-data-suite-ontology](https://github.com/buchochelliq-labs/open-data-suite-ontology) | A layered ontology that merges central, repository and local facts and serves them to agents over MCP, keeping the provenance of every value |
| [homebrew-tap](https://github.com/buchochelliq-labs/homebrew-tap) | Homebrew formula for the `ods` binary |
| [dbt-skills](dbt-skills.md) | The agent skills and modelling context that the ontology was originally ported from |
