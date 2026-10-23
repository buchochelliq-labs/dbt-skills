# Design decision proposals Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare complete reviewable grain/history records without manually copying hashes.
**Architecture:** A shared read-only operation derives context through the existing planner, then returns a proposed decisions document and guarded JSON patch. CLI and MCP remain thin adapters. Humans review and save through their existing file workflow.
**Tech Stack:** Python 3.11+, existing bounded JSON loader and unittest/MCP harness.
**Spec:** docs/ARCHITECTURE.md learning/authority boundaries and docs/MODEL_PLANNING.md saved decisions workflow; issues #16/#37.

## Global Constraints

No file writes, source rows, automatic approval or standards promotion. Exact one-asset intent/scope; explicit grain/history and human-supplied attribution/time/rationale. Pending proposals never prove normal form. Existing records are preserved unless an exact matching record is explicitly selected for replacement. Base digest and test patch protect review against intervening file edits; saving remains external.

## Review Focus

- Denial/conflicting catalog evidence must not produce a reusable record.
- Existing matching records require explicit replacement, not accidental duplicates.
- A replacement cannot overwrite an unrelated intent/asset/scope or another ID.
- MCP rejects changed selected policy/decisions until refresh; paths remain startup-only.
- Proposed output must be accepted by the bounded saved-decisions loader.

## Task 1: Shared proposal operation and adapters

Files: new src/dbt_skills/design_decision_proposals.py and tests/test_design_decision_proposals.py; modify src/dbt_skills/modelling_mcp.py and docs/MODEL_PLANNING.md, COPILOT_VSCODE.md, HANDOVER.md.
Interface: prepare_design_decision(project, policy, catalog, request, *, decisions=None, snapshot=None) -> report. Request contains plan (one explicit asset with grain/history), record (id/rationale/recorded_by/recorded_at), optional replace_record_id. Return status, planning report, proposed_document, decisions_base and decisions_patch. CLI mirrors planning context flags. MCP model_propose_decision takes context_id/request only.

- [x] Add failing core tests for new document roundtrip/no writes, replacement/duplicates/ID collisions, missing columns/denied evidence, invalid attribution, output bounds.
- [x] Implement core and run focused tests.
- [x] Add failing CLI and real stdio tests, including changed-file refresh; implement adapters.
- [x] Update workflow docs and handover; run full suite with real dbt, compileall and diff check.
- [ ] Independent review, fix findings, commit and publish focused PR; verify CI. No merge/release.

Progress: core and adapters complete; independent review found no critical/important issues. Added explicit catalog-conflict and policy-change stdio coverage. Synthetic example returns pending_review with dependency questions retained.
