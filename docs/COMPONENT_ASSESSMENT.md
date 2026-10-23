# Reuse and component assessment

**Status:** Initial local runtime decision recorded 2026-10-22. This is not a complete SBOM or production approval. Revisions below are evidence snapshots; verify transitive licenses, security advisories, and compatibility before production adoption.

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
| [PyYAML](https://pyyaml.org/) | MIT; pinned release 6.0.3 | Safe parsing of `dbt_project.yml` for project discovery | Adopted as the only new runtime dependency. Its transitive dependency set is empty in the tested installation; include its MIT notice in future packaged distributions. |
| `argparse`, `urllib`, `tomllib`, `sqlite3`, and other Python standard-library modules | Python Software Foundation License; bundled with the configured Python runtime | CLI, OpenAI-compatible HTTP adapter, project-local TOML config, and SQLite UOL | Adopt; no separate runtime package dependency. The project itself has no GitHub license metadata, so distributable packaging remains blocked on resolving repository licensing. |
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

This inventory is not yet an SBOM or a complete security audit. The initial runtime adopts PyYAML after recording its license and dependency footprint; production adoption still requires transitive dependency/license verification, CVE/advisory review, threat modeling, and exact pinned package artifact checks.

## Initial runtime decision

The initial local runtime uses Python 3.11+ and a small in-repository orchestration module, the Python standard library for CLI/HTTP/config/storage, and PyYAML 6.0.3 (MIT) with `safe_load` for `dbt_project.yml`. `argparse` is sufficient for the first CLI, so Typer is not added. A provider protocol keeps model access replaceable; the first adapter speaks the OpenAI Chat Completions-compatible HTTP contract, supporting local endpoints such as Ollama's OpenAI-compatible API and hosted BYOK endpoints without a provider SDK. Credentials are read by environment-variable name and are never written into project config. Plain HTTP is restricted to loopback hosts.

No general-purpose agent framework is selected: this runtime only sends a single scripted prompt and does not call tools. That keeps approvals and tool execution out of scope until policy controls are implemented in issue #11. dbt MCP remains the source for dbt operations; the local runtime does not duplicate dbt commands. The official MCP Python SDK remains pinned for the optional ODS adapter and is not a dependency of the CLI's model-provider adapter.

This decision favors a narrow seam and low dependency surface over Pydantic AI/Typer until tool lifecycle, streaming, interactive memory, approval hooks, and client compatibility are actually needed. Current evidence: Python 3.14 local test runtime; PyYAML 6.0.3 reports MIT and no package dependencies; model-protocol behavior is covered by local mocked HTTP tests, not by live provider calls. The repository has no declared license, so installable/distributable packaging and redistribution of this code remain blocked pending the repository licensing decision. Back out by replacing the `ModelProvider` adapter and `AgentRuntime` implementation while retaining project discovery and UOL storage interfaces; if dependency/license policy rejects PyYAML, remove project config parsing through this adapter seam rather than substituting an unreviewed parser.

## Verified dbt v2 lineage boundary

The official dbt Information Schema docs describe local Parquet generation, but an installable distribution check is important: `dbt-oss` 2.0.8 accepts `--generate-info-schema --static-analysis strict`, warns that its distribution does not include the static-analysis engine, and returns zero rows for `dbt.column_lineage`. The open-source product will use ODS's separate Apache-2.0 static SQL analyzer through its optional read-only MCP rather than require or redistribute dbt's full product-licensed distribution. ODS documents local analysis of compiled dbt SQL and outputs lineage, impact, confidence/diagnostics, and opaque-node reasons; the capability is marked preview and exact artifact, tool-schema, and version compatibility must be validated before adoption.

See [the reproduction record](research/dbt-v2-column-lineage.md) and [ODS's lineage design](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0008-column-level-lineage.md). The reproduction establishes the `dbt-oss` boundary, not a lack of available open-source lineage: ODS provides an independent static-analysis path. Keep it optional and report column-level impact unavailable (with ODS's diagnostic reason where present) when the server is absent or the model is opaque/unsupported.

For large artifacts, benchmark realistic project sizes and use bounded/selective Parquet/JSON reads; do not load redundant full snapshots without need. User-visible responsiveness and reliable project-scale memory use matter more than language alone. Establish baseline measurements before setting budgets.

## Backout procedure

1. Freeze upgrades and identify the exact last approved release and its license/notice obligations.
2. Do not adopt or distribute newly relicensed versions until reviewed; continued use of an older version is only permissible where its terms allow it.
3. Prefer a maintained compatible open implementation; otherwise consider a lawful fork or clean replacement behind the adapter.
4. If replacement is not lawful or maintainable, disable the optional capability and document the impact rather than creating a proprietary service dependency.
# Modelling policy validation dependency (2026-10-23)

Use `jsonschema==4.26.0` for the bundled Draft 2020-12 modelling document schema.
It was already installed transitively through the MCP stack; it is now an explicit
runtime dependency because the policy loader imports it directly. Exact installed
distribution metadata reports MIT; its COPYING notice is preserved in
THIRD_PARTY_NOTICES.md. No dynamic schema loading or remote references are used.
The schema remains portable if this validator must be replaced. Dependency updates
must re-run schema/negative-input tests and review the new distribution's license.
This does not resolve the repository's own distribution-license decision (#5).
