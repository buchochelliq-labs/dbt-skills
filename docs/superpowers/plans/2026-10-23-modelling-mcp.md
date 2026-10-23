# Modelling MCP and VS Code adapter plan

Goal: Thin stdio tools expose existing local modelling context, inference, naming,
comparison and pending proposals to Copilot in VS Code without a new agent runtime.
Spec: docs/ARCHITECTURE.md; #25. Execute inline; independent review before publishing.

1. Tests first: real MCP subprocess/tool discovery and calls across context -> rule
   selection -> clarification/render -> comparison -> proposal. Assert read-only
   annotations, no raw SQL sentinel, no writes or UOL dependency, pinned source hash,
   explicit refresh, stale context IDs and policy changes fail closed.
2. modelling_mcp.py captures one shared inspect_artifacts result plus selected policy
   at startup/refresh. Tools take context IDs, not file paths. Startup pins human-selected
   project/policy/proposals paths. Reuse all core functions. Check live policy/proposal
   hashes returned by core calls against pinned context; serialize capture/tool calls.
   Add bounded policy-rule paging. No SQL query, edit, apply, approval or arbitrary-file tool.
3. Add separate portable mcpServers and VS Code Local servers configuration examples,
   no interactive substitutions; paths explicitly configured. Add thin custom agent
   profile guiding incremental questions and review only. Use current official docs.
4. Run stdio tests/full suite, verify config/profile assets, independent review and CI.
   Record live VS Code/Copilot smoke as not performed: code executable is only a shim
   reporting that VS Code is not installed. Do not claim host approval/UI verification.
