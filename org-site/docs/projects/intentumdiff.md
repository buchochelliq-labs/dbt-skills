# IntentumDiff

**Semantic code review that detects intent, moves, refactorings and style changes.**

IntentumDiff diffs code by *meaning* rather than by line. It parses both sides into
semantic trees, then matches and classifies every change as meaningful, refactoring,
moved, style-only or noise. It derives a risk level for each change and explains *why*,
across 69 languages and formats from Python and TypeScript to Terraform, SQL dialects
and Markdown.

[Read the documentation](https://buchochelliq-labs.github.io/intentumdiff-docs/){ .md-button .md-button--primary }
[intentumdiff-core on GitHub](https://github.com/buchochelliq-labs/intentumdiff-core){ .md-button }

## How the pieces fit

The engine does all of the work. Every product surface is a thin binding over its C ABI.

| Layer | Repository | Role |
|---|---|---|
| Engine | [intentumdiff-core](https://github.com/buchochelliq-labs/intentumdiff-core) | Rust backend: semantic tree diff, review, guardrails, and the native CLI |
| Shared model | [intentumdiff-ast](https://github.com/buchochelliq-labs/intentumdiff-ast) | Canonical cross-language AST (UAST) |
| Plugins | [intentumdiff-plugin-sdk](https://github.com/buchochelliq-labs/intentumdiff-plugin-sdk) | The WIT contract and build scaffolding for parser plugins |
| Trust | [intentumdiff-registry](https://github.com/buchochelliq-labs/intentumdiff-registry) | Plugin manifest, discovery catalog and vetting pipeline |
| Editors | [intentumdiff-vscode](https://github.com/buchochelliq-labs/intentumdiff-vscode), [intentumdiff-lsp](https://github.com/buchochelliq-labs/intentumdiff-lsp), [intentumdiff-live-server](https://github.com/buchochelliq-labs/intentumdiff-live-server) | VS Code extension, LSP server, and keystroke-level live diff server |
| Bindings | [Python](https://github.com/buchochelliq-labs/intentumdiff-python), [Go](https://github.com/buchochelliq-labs/intentumdiff-go), [Java](https://github.com/buchochelliq-labs/intentumdiff-java) | Thin C-ABI wrappers |
| Docs | [intentumdiff-docs](https://github.com/buchochelliq-labs/intentumdiff-docs) | The documentation site. Every example runs in CI. |

## Language parsers

Each supported language is a tree-sitter-based Wasm plugin in its own repository.
See the [full list of parsers](../catalog.md#intentumdiff-parsers).
