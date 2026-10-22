# Reuse and component assessment

**Status:** M0 preliminary assessment, checked 2026-10-22. This is not a lockfile or final implementation selection. Revisions below are evidence snapshots, not approved dependency pins. Verify transitive licenses, security advisories, and compatibility again before adding dependencies.

## Reuse candidates and boundaries

| Component | Observed license/activity | Proposed use | Decision / caveat |
|---|---|---|---|
| [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) | Apache-2.0; evidence revision `b8facde20b7a92c40ce3e6b86b71c4b92aa44040` | General dbt skill coverage; consume as an upstream package/repository and reference it from additive integration skills | Reuse; do not mirror common skills. Re-check pinned content, notices, package mechanics, and names before distribution. |
| [`dbt-labs/dbt-mcp`](https://github.com/dbt-labs/dbt-mcp) | Apache-2.0; evidence revision `c25baf52c1a201780f7d3e65023382d653b2d46f` | Existing dbt-specific local/platform MCP operations | Integrate through MCP and discover actual tools. Do not duplicate its command or metadata service. Re-check feature/permission/transport matrix per server release. |
| [`dbt-labs/dbt`](https://github.com/dbt-labs/dbt) source | Apache-2.0; v2.0.8 tag resolves to `43918198c2f02366ceb33f60006812872b0bab40` | dbt v2 OSS source and project-context behavior | The PyPI `dbt-oss` subset at 2.0.8 does not include the static-analysis engine, even though the source repository contains it. Do not infer that a feature in the repository is included in every distribution. |
| [`dbt` full distribution](https://pypi.org/project/dbt/2.0.8/) | PyPI `dbt` 2.0.8 source archive SHA-256: `b6c002bc792df98c0408785e3b4b25f51ffce9849651c54505cc95bc511b1bb9`; project docs identify a dbt product license | Possible local strict static-analysis/lineage provider | Do not require or distribute it without separately reviewing its terms. Local lineage under these terms and any plan requirement remain unresolved. |
| [Agent Skills specification](https://agentskills.io/specification) | Specification snapshot evidence revision `69ef37e9424c0a7ea9dd2293b559e43ec8176379`; validator/library not selected | Canonical portable skill directory/frontmatter convention | Use the format; evaluate and pin any validator separately. Do not assume every client implements optional fields identically. |
| [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT; evidence revision `2af9e3089ac66b35c1550c500aae86a82efb1e17` | Candidate client/server protocol implementation if Python is selected | Candidate only. Verify supported MCP protocol versions, transport coverage, dependency security, and release license before pinning. |
| [Official MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) | GitHub API reports `NOASSERTION` for repository license metadata | Candidate only if TypeScript is selected | Do not adopt until the exact release license is independently established. |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | MIT; evidence revision `7e0d7b32e0ba0d3b8bebc50cfcf6bf756402c5b9` | Candidate agent/runtime/provider abstraction if Python is selected | Candidate only; prototype tool lifecycle, approval hooks, provider coverage, and memory/runtime fit before adoption. |
| [Typer](https://github.com/fastapi/typer) | MIT; evidence revision `a5882dedf0bc7a46cd861fdfca020f88519e0f21` | Candidate Python CLI framework | Candidate only; evaluate help/completion, packaging, cross-platform behavior, and compatibility with selected runtime. |
| [OpenDataSuite](https://github.com/buchochelliq-labs/open-data-suite) | Apache-2.0; evidence revision `965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a`; sibling project states pre-alpha | Context for adjacent analytics-engineering work and possible future convergence | Not a dependency or scope change now. Share concrete reusable findings with ODS; re-evaluate if a future integration is requested. |

## Selection criteria

Before choosing a CLI/runtime or library, record:

- Exact release/commit, SPDX license, notices, source provenance, and relevant transitive licenses.
- Maintenance signals, vulnerability/advisory posture, security model, and support policy.
- Required OS/Python/runtime versions and packaging/install experience on Windows, macOS, and Linux.
- MCP client/server transport support and interoperability with dbt MCP and compatible clients.
- Provider extensibility, BYOK/local-provider support, approval hooks, policy boundaries, and workspace-safe editing.
- Artifact scale/read strategy, memory/latency profile, and how performance can be measured reproducibly.
- Adapter seam and specific exit path if the project changes license, becomes unmaintained, or no longer fits.

No dependency is approved merely because it appears in this table. Do not silently follow a moving branch. Pin reviewed versions, scan and review updates, and fail CI on newly unapproved license identifiers. Where a component is optional, keep the core usable without it.

This M0 inventory is not yet an SBOM or a complete security audit: transitive dependency licenses, CVEs/advisories, threat models, and exact pinned package artifacts must be checked in the implementation milestone before dependencies are adopted.

## Preliminary runtime direction

The dbt and MCP integration ecosystem is Python-oriented: the public dbt MCP server and official MCP Python SDK provide possible building blocks, while a typed CLI/runtime such as Typer and Pydantic AI are candidates. This is not a final language/framework choice. Prototype a representative local-project discovery and one MCP interaction, compare alternatives on the selection criteria above, then record the decision before scaffolding the CLI.

For the first interactive CLI, the working product decision is a provider-neutral adapter interface with multiple BYOK provider options from the outset; select exact providers only after verifying their SDKs, licensing, and local/self-hosted support. This preserves the roadmap's provider-flexibility requirement without prematurely locking the runtime.

## Verified dbt v2 lineage boundary

The official dbt Information Schema docs describe local Parquet generation, but an installable distribution check is important: `dbt-oss` 2.0.8 accepts `--generate-info-schema --static-analysis strict`, warns that its distribution does not include the static-analysis engine, and returns zero rows for `dbt.column_lineage`. The sibling full `dbt` distribution advertises the full feature set and is identified in dbt's packaging text as released under a dbt product license, while `dbt-oss` is the Apache-2.0 subset. Therefore, the open-source subset cannot be treated as a source of generated column lineage based on its interface or the presence of an empty Parquet table.

See [the reproduction record](research/dbt-v2-column-lineage.md). Whether the full distribution's local lineage feature is available under free/self-hosted terms is not resolved by this test; it is also distinct from the hosted dbt Catalog Enterprise feature. The project must detect actual non-empty lineage evidence and remain useful without it.

For large artifacts, benchmark realistic project sizes and use bounded/selective Parquet/JSON reads; do not load redundant full snapshots without need. User-visible responsiveness and reliable project-scale memory use matter more than language alone. Establish baseline measurements before setting budgets.

## Backout procedure

1. Freeze upgrades and identify the exact last approved release and its license/notice obligations.
2. Do not adopt or distribute newly relicensed versions until reviewed; continued use of an older version is only permissible where its terms allow it.
3. Prefer a maintained compatible open implementation; otherwise consider a lawful fork or clean replacement behind the adapter.
4. If replacement is not lawful or maintainable, disable the optional capability and document the impact rather than creating a proprietary service dependency.
