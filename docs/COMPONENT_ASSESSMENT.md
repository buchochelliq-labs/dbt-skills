# Reuse and component assessment

**Status:** M0 preliminary assessment, checked 2026-10-22. This is not a complete SBOM or final runtime selection. Revisions below are evidence snapshots, not approved production pins; the MCP SDK is pinned only for the ODS adapter prototype. Verify transitive licenses, security advisories, and compatibility before production adoption.

## Reuse candidates and boundaries

| Component | Observed license/activity | Proposed use | Decision / caveat |
|---|---|---|---|
| [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) | Apache-2.0; evidence revision `b8facde20b7a92c40ce3e6b86b71c4b92aa44040` | General dbt skill coverage; consume as an upstream package/repository and reference it from additive integration skills | Reuse; do not mirror common skills. Re-check pinned content, notices, package mechanics, and names before distribution. |
| [`dbt-labs/dbt-mcp`](https://github.com/dbt-labs/dbt-mcp) | Apache-2.0; evidence revision `c25baf52c1a201780f7d3e65023382d653b2d46f` | Existing dbt-specific local/platform MCP operations | Integrate through MCP and discover actual tools. Do not duplicate its command or metadata service. Re-check feature/permission/transport matrix per server release. |
| [`dbt-labs/dbt`](https://github.com/dbt-labs/dbt) source | Apache-2.0; v2.0.8 tag resolves to `43918198c2f02366ceb33f60006812872b0bab40` | dbt v2 OSS source and project-context behavior | The PyPI `dbt-oss` subset at 2.0.8 does not include the static-analysis engine, even though the source repository contains it. Do not infer that a feature in the repository is included in every distribution. |
| [`dbt` full distribution](https://pypi.org/project/dbt/2.0.8/) | PyPI `dbt` 2.0.8 source archive SHA-256: `b6c002bc792df98c0408785e3b4b25f51ffce9849651c54505cc95bc511b1bb9`; project docs identify a dbt product license | Reference only for the tested `dbt-oss` distribution boundary | Excluded as a dbt-skills runtime dependency/lineage provider per the ODS reuse decision. Do not require or distribute it without a separate user request and terms review. |
| [Agent Skills specification](https://agentskills.io/specification) | Specification snapshot evidence revision `69ef37e9424c0a7ea9dd2293b559e43ec8176379`; validator/library not selected | Canonical portable skill directory/frontmatter convention | Use the format; evaluate and pin any validator separately. Do not assume every client implements optional fields identically. |
| [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT; v2.3.0 release evidence; upstream evidence revision `2af9e3089ac66b35c1550c500aae86a82efb1e17` | Python stdio MCP client for the optional ODS adapter prototype | `mcp==2.3.0` is pinned in `requirements.txt`; the SDK connected to ODS v0.0.2 and passed the four-model dbt-oss 2.0.8 contract check through both artifact modes. `pip-audit` found no known vulnerabilities in the tested resolved dependency set. This is not a full transitive license audit or an automated update gate. GHSA-rwrf-2pqf-9j8j is fixed in SDK 2.2.0; HTTP/OAuth advisories reviewed do not apply to this stdio-only client. Re-check exact artifacts and all dependencies before release. |
| [Official MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) | GitHub API reports `NOASSERTION` for repository license metadata | Candidate only if TypeScript is selected | Do not adopt until the exact release license is independently established. |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | MIT; evidence revision `7e0d7b32e0ba0d3b8bebc50cfcf6bf756402c5b9` | Candidate agent/runtime/provider abstraction if Python is selected | Candidate only; prototype tool lifecycle, approval hooks, provider coverage, and memory/runtime fit before adoption. |
| [Typer](https://github.com/fastapi/typer) | MIT; evidence revision `a5882dedf0bc7a46cd861fdfca020f88519e0f21` | Candidate Python CLI framework | Candidate only; evaluate help/completion, packaging, cross-platform behavior, and compatibility with selected runtime. |
| [OpenDataSuite](https://github.com/buchochelliq-labs/open-data-suite) | Apache-2.0; reviewed main revision `965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a`; ODS v0.0.2 release commit `f18ed9aad5e5121509fd4b649d336990ff605000` | Optional external provider via ODS's read-only stdio MCP for local SQL column-lineage, impact, and opaque-node diagnostics | User-directed reuse. CLI, raw stdio MCP, and official Python SDK adapter checks passed on the four-model dbt-oss 2.0.8 fixture in both artifact modes. The prototype is optional, not bundled, and pins the expected server contract at ODS 0.0.2; ODS labels lineage/MCP preview and warns 0.0.x interfaces may break. Broader source/catalog coverage and release-time license/provenance/security gates remain open. |

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

The dbt and MCP integration ecosystem is Python-oriented: the public dbt MCP server and official MCP Python SDK provide possible building blocks, while a typed CLI/runtime such as Typer and Pydantic AI are candidates. The user selected a Python adapter prototype using the official SDK; `src/dbt_skills/ods_mcp.py` now connects to optional ODS stdio MCP and explicitly preserves unavailable/partial lineage status. Its contract check passed against ODS v0.0.2 and dbt-oss 2.0.8 in both artifact modes, including an opaque focus and absent-provider fallback. This does not select the eventual CLI/agent runtime or validate source-heavy/catalog-dependent projects. Continue the broader runtime/component comparison before scaffolding the CLI.

For the first interactive CLI, the working product decision is a provider-neutral adapter interface with multiple BYOK provider options from the outset; select exact providers only after verifying their SDKs, licensing, and local/self-hosted support. This preserves the roadmap's provider-flexibility requirement without prematurely locking the runtime.

## Verified dbt v2 lineage boundary

The official dbt Information Schema docs describe local Parquet generation, but an installable distribution check is important: `dbt-oss` 2.0.8 accepts `--generate-info-schema --static-analysis strict`, warns that its distribution does not include the static-analysis engine, and returns zero rows for `dbt.column_lineage`. The open-source product will use ODS's separate Apache-2.0 static SQL analyzer through its optional read-only MCP rather than require or redistribute dbt's full product-licensed distribution. ODS documents local analysis of compiled dbt SQL and outputs lineage, impact, confidence/diagnostics, and opaque-node reasons; the capability is marked preview and exact artifact, tool-schema, and version compatibility must be validated before adoption.

See [the reproduction record](research/dbt-v2-column-lineage.md) and [ODS's lineage design](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0008-column-level-lineage.md). The reproduction establishes the `dbt-oss` boundary, not a lack of available open-source lineage: ODS provides an independent static-analysis path. Keep it optional and report column-level impact unavailable (with ODS's diagnostic reason where present) when the server is absent or the model is opaque/unsupported.

For large artifacts, benchmark realistic project sizes and use bounded/selective Parquet/JSON reads; do not load redundant full snapshots without need. User-visible responsiveness and reliable project-scale memory use matter more than language alone. Establish baseline measurements before setting budgets.

## Backout procedure

1. Freeze upgrades and identify the exact last approved release and its license/notice obligations.
2. Do not adopt or distribute newly relicensed versions until reviewed; continued use of an older version is only permissible where its terms allow it.
3. Prefer a maintained compatible open implementation; otherwise consider a lawful fork or clean replacement behind the adapter.
4. If replacement is not lawful or maintainable, disable the optional capability and document the impact rather than creating a proprietary service dependency.
