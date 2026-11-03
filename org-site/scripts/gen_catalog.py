#!/usr/bin/env python3
"""Generate docs/catalog.md from the organisation's public GitHub repositories.

Runs before `mkdocs build` in CI so the catalog never goes stale. Uses only the
standard library. Set GITHUB_TOKEN to avoid the unauthenticated rate limit.

    python scripts/gen_catalog.py            # fetch from the GitHub API
    python scripts/gen_catalog.py repos.json # or read a saved API response
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ORG = "buchochelliq-labs"
OUT = Path(__file__).resolve().parent.parent / "docs" / "catalog.md"

# Order matters: first matching group wins.
GROUPS: list[tuple[str, str, callable]] = [
    ("IntentumDiff: engine, bindings and tools", "intentumdiff",
     lambda n: n.startswith("intentumdiff-") and not n.endswith("-parser")),
    ("IntentumDiff: language parsers", "intentumdiff-parsers",
     lambda n: n.startswith("intentumdiff-") and n.endswith("-parser")),
    ("OpenDataSuite and analytics engineering", "data",
     lambda n: n.startswith("open-data-suite") or n in {"dbt-skills", "homebrew-tap"}),
    ("rs-rich", "rs-rich", lambda n: n.startswith("rs-rich")),
    ("Tooling and organisation", "other", lambda n: True),
]

HIDDEN = {".github"}

# Used when a repository has no description set on GitHub.
FALLBACK_DESCRIPTIONS = {
    "dbt-skills": "Local-first dbt skills, project context and catalog grounding for coding agents.",
    "homebrew-tap": "Homebrew formulae: `brew install buchochelliq-labs/tap/ods`.",
    "open-data-suite": "Rust-first, provider-neutral control plane for analytics engineering (dbt, Databricks).",
    "open-data-suite-ontology": "Layered, provenance-preserving ontology served to agents over MCP.",
    "rs-rich-cli": "Python's rich, ported to Rust byte for byte, plus the intuiTUIve TUI framework.",
    "rs-rich-doom": "Doom in the terminal, drawn and driven by rs-rich.",
    "rs-rich-marketplace": "The signed plugin marketplace index for rs-rich.",
    "release-kit": "The org's release standard: one file, one command, every registry.",
}


def fetch() -> list[dict]:
    repos: list[dict] = []
    page = 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"{ORG}-docs"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    while True:
        url = f"https://api.github.com/orgs/{ORG}/repos?type=public&per_page=100&page={page}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as resp:
            batch = json.load(resp)
        if not batch:
            return repos
        repos.extend(batch)
        page += 1


def cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def parser_language(name: str) -> str:
    return name.removeprefix("intentumdiff-").removesuffix("-parser")


def render(repos: list[dict]) -> str:
    repos = [r for r in repos
             if not r.get("private") and not r.get("archived") and r["name"] not in HIDDEN]
    grouped: dict[str, list[dict]] = {title: [] for title, _, _ in GROUPS}
    for repo in sorted(repos, key=lambda r: r["name"]):
        for title, _, match in GROUPS:
            if match(repo["name"]):
                grouped[title].append(repo)
                break

    out = [
        "# All repositories",
        "",
        f"Every public repository in [{ORG}](https://github.com/{ORG}), "
        f"grouped by project ({len(repos)} in total).",
        "",
        "!!! note \"Generated page\"",
        "    This page is rebuilt from the GitHub API on every deploy by "
        "`scripts/gen_catalog.py`. Don't edit it by hand.",
        "",
    ]
    for title, anchor, _ in GROUPS:
        items = grouped[title]
        if not items:
            continue
        out += [f"## {title} {{ #{anchor} }}", ""]
        if anchor == "intentumdiff-parsers":
            out += [
                f"{len(items)} tree-sitter-based Wasm parser plugins, one per language "
                "or format, built on the "
                f"[plugin SDK](https://github.com/{ORG}/intentumdiff-plugin-sdk).",
                "",
                " · ".join(f"[`{parser_language(r['name'])}`]({r['html_url']})" for r in items),
                "",
            ]
            continue
        out += ["| Repository | Description | Language | Docs |", "|---|---|---|---|"]
        for r in items:
            docs = ""
            if r.get("has_pages"):
                docs = f"[Site](https://{ORG}.github.io/{r['name']}/)"
            elif r.get("homepage"):
                docs = f"[Site]({r['homepage']})"
            out.append(
                f"| [{r['name']}]({r['html_url']}) | {cell(r.get('description') or FALLBACK_DESCRIPTIONS.get(r['name']))} "
                f"| {cell(r.get('language'))} | {docs} |"
            )
        out.append("")
    return "\n".join(out)


def main() -> None:
    repos = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else fetch()
    OUT.write_text(render(repos))
    print(f"wrote {OUT} ({len(repos)} repositories from the API)")


if __name__ == "__main__":
    main()
