# All repositories

Every public repository in [buchochelliq-labs](https://github.com/buchochelliq-labs), grouped by project (88 in total).

!!! note "Generated page"
    This page is rebuilt from the GitHub API on every deploy by `scripts/gen_catalog.py`. Don't edit it by hand.

## IntentumDiff: engine, bindings and tools { #intentumdiff }

| Repository | Description | Language | Docs |
|---|---|---|---|
| [intentumdiff-ast](https://github.com/buchochelliq-labs/intentumdiff-ast) | Canonical cross-language AST (UAST) — one normalised vocabulary for 200+ language-specific node types | Rust |  |
| [intentumdiff-core](https://github.com/buchochelliq-labs/intentumdiff-core) | IntentDiff — the complete Rust backend (semantic diff engine) + C ABI + shared CLI. The flagship. | Rust |  |
| [intentumdiff-docs](https://github.com/buchochelliq-labs/intentumdiff-docs) | Documentation for IntentumDiff — semantic code review. Examples are executed in CI. | Python | [Site](https://buchochelliq-labs.github.io/intentumdiff-docs/) |
| [intentumdiff-go](https://github.com/buchochelliq-labs/intentumdiff-go) | IntentDiff Go bindings — thin C-ABI wrapper (cgo). | Go |  |
| [intentumdiff-java](https://github.com/buchochelliq-labs/intentumdiff-java) | IntentDiff Java bindings — thin C-ABI wrapper (JNI/Panama). | Java |  |
| [intentumdiff-live-server](https://github.com/buchochelliq-labs/intentumdiff-live-server) | IntentDiff live-server — the native keystroke-level diff/review IPC server; an in-process C-ABI consumer of the core, spawned by editors. | Rust |  |
| [intentumdiff-lsp](https://github.com/buchochelliq-labs/intentumdiff-lsp) | IntentDiff LSP layer — the generic LSP client codec + the native intentdiff LSP server (links the engine in-process). | Rust |  |
| [intentumdiff-plugin-sdk](https://github.com/buchochelliq-labs/intentumdiff-plugin-sdk) | IntentDiff plugin SDK — the WIT contract and build scaffolding for parser plugins (root of the DAG). | Rust |  |
| [intentumdiff-python](https://github.com/buchochelliq-labs/intentumdiff-python) | IntentDiff Python bindings — thin C-ABI wrapper; ships the intentdiff package to PyPI. | Python |  |
| [intentumdiff-registry](https://github.com/buchochelliq-labs/intentumdiff-registry) | IntentDiff plugin registry — manifest, discovery catalog, and the trust/vetting pipeline (root of trust). | Python |  |
| [intentumdiff-vscode](https://github.com/buchochelliq-labs/intentumdiff-vscode) | IntentDiff VS Code extension — native-first diff surfaces over the core live-server. | TypeScript |  |

## IntentumDiff: language parsers { #intentumdiff-parsers }

69 tree-sitter-based Wasm parser plugins, one per language or format, built on the [plugin SDK](https://github.com/buchochelliq-labs/intentumdiff-plugin-sdk).

[`abap`](https://github.com/buchochelliq-labs/intentumdiff-abap-parser) · [`adf`](https://github.com/buchochelliq-labs/intentumdiff-adf-parser) · [`asciidoc`](https://github.com/buchochelliq-labs/intentumdiff-asciidoc-parser) · [`asm`](https://github.com/buchochelliq-labs/intentumdiff-asm-parser) · [`assemblyscript`](https://github.com/buchochelliq-labs/intentumdiff-assemblyscript-parser) · [`astro`](https://github.com/buchochelliq-labs/intentumdiff-astro-parser) · [`bash`](https://github.com/buchochelliq-labs/intentumdiff-bash-parser) · [`clojure`](https://github.com/buchochelliq-labs/intentumdiff-clojure-parser) · [`cmake`](https://github.com/buchochelliq-labs/intentumdiff-cmake-parser) · [`cpp`](https://github.com/buchochelliq-labs/intentumdiff-cpp-parser) · [`csharp`](https://github.com/buchochelliq-labs/intentumdiff-csharp-parser) · [`css`](https://github.com/buchochelliq-labs/intentumdiff-css-parser) · [`dart`](https://github.com/buchochelliq-labs/intentumdiff-dart-parser) · [`databricks`](https://github.com/buchochelliq-labs/intentumdiff-databricks-parser) · [`dax`](https://github.com/buchochelliq-labs/intentumdiff-dax-parser) · [`delphi`](https://github.com/buchochelliq-labs/intentumdiff-delphi-parser) · [`dockerfile`](https://github.com/buchochelliq-labs/intentumdiff-dockerfile-parser) · [`elixir`](https://github.com/buchochelliq-labs/intentumdiff-elixir-parser) · [`freebasic`](https://github.com/buchochelliq-labs/intentumdiff-freebasic-parser) · [`generic`](https://github.com/buchochelliq-labs/intentumdiff-generic-parser) · [`gitignore`](https://github.com/buchochelliq-labs/intentumdiff-gitignore-parser) · [`go`](https://github.com/buchochelliq-labs/intentumdiff-go-parser) · [`gomod`](https://github.com/buchochelliq-labs/intentumdiff-gomod-parser) · [`graphql`](https://github.com/buchochelliq-labs/intentumdiff-graphql-parser) · [`groovy`](https://github.com/buchochelliq-labs/intentumdiff-groovy-parser) · [`haskell`](https://github.com/buchochelliq-labs/intentumdiff-haskell-parser) · [`html`](https://github.com/buchochelliq-labs/intentumdiff-html-parser) · [`ini`](https://github.com/buchochelliq-labs/intentumdiff-ini-parser) · [`java`](https://github.com/buchochelliq-labs/intentumdiff-java-parser) · [`js-ts`](https://github.com/buchochelliq-labs/intentumdiff-js-ts-parser) · [`json`](https://github.com/buchochelliq-labs/intentumdiff-json-parser) · [`kotlin`](https://github.com/buchochelliq-labs/intentumdiff-kotlin-parser) · [`latex`](https://github.com/buchochelliq-labs/intentumdiff-latex-parser) · [`lua`](https://github.com/buchochelliq-labs/intentumdiff-lua-parser) · [`make`](https://github.com/buchochelliq-labs/intentumdiff-make-parser) · [`markdown`](https://github.com/buchochelliq-labs/intentumdiff-markdown-parser) · [`mdx`](https://github.com/buchochelliq-labs/intentumdiff-mdx-parser) · [`ocaml`](https://github.com/buchochelliq-labs/intentumdiff-ocaml-parser) · [`odin`](https://github.com/buchochelliq-labs/intentumdiff-odin-parser) · [`perl`](https://github.com/buchochelliq-labs/intentumdiff-perl-parser) · [`php`](https://github.com/buchochelliq-labs/intentumdiff-php-parser) · [`plsql`](https://github.com/buchochelliq-labs/intentumdiff-plsql-parser) · [`po`](https://github.com/buchochelliq-labs/intentumdiff-po-parser) · [`postscript`](https://github.com/buchochelliq-labs/intentumdiff-postscript-parser) · [`powershell`](https://github.com/buchochelliq-labs/intentumdiff-powershell-parser) · [`proto`](https://github.com/buchochelliq-labs/intentumdiff-proto-parser) · [`puppet`](https://github.com/buchochelliq-labs/intentumdiff-puppet-parser) · [`python`](https://github.com/buchochelliq-labs/intentumdiff-python-parser) · [`qsharp`](https://github.com/buchochelliq-labs/intentumdiff-qsharp-parser) · [`r`](https://github.com/buchochelliq-labs/intentumdiff-r-parser) · [`reasonml`](https://github.com/buchochelliq-labs/intentumdiff-reasonml-parser) · [`ruby`](https://github.com/buchochelliq-labs/intentumdiff-ruby-parser) · [`rust`](https://github.com/buchochelliq-labs/intentumdiff-rust-parser) · [`sas`](https://github.com/buchochelliq-labs/intentumdiff-sas-parser) · [`scala`](https://github.com/buchochelliq-labs/intentumdiff-scala-parser) · [`scss`](https://github.com/buchochelliq-labs/intentumdiff-scss-parser) · [`sql`](https://github.com/buchochelliq-labs/intentumdiff-sql-parser) · [`squirrel`](https://github.com/buchochelliq-labs/intentumdiff-squirrel-parser) · [`svelte`](https://github.com/buchochelliq-labs/intentumdiff-svelte-parser) · [`swift`](https://github.com/buchochelliq-labs/intentumdiff-swift-parser) · [`terraform`](https://github.com/buchochelliq-labs/intentumdiff-terraform-parser) · [`toml`](https://github.com/buchochelliq-labs/intentumdiff-toml-parser) · [`tsql`](https://github.com/buchochelliq-labs/intentumdiff-tsql-parser) · [`vbnet`](https://github.com/buchochelliq-labs/intentumdiff-vbnet-parser) · [`vue`](https://github.com/buchochelliq-labs/intentumdiff-vue-parser) · [`wat`](https://github.com/buchochelliq-labs/intentumdiff-wat-parser) · [`xml`](https://github.com/buchochelliq-labs/intentumdiff-xml-parser) · [`yaml`](https://github.com/buchochelliq-labs/intentumdiff-yaml-parser) · [`zig`](https://github.com/buchochelliq-labs/intentumdiff-zig-parser)

## OpenDataSuite and analytics engineering { #data }

| Repository | Description | Language | Docs |
|---|---|---|---|
| [dbt-skills](https://github.com/buchochelliq-labs/dbt-skills) | Local-first dbt skills, project context and catalog grounding for coding agents. | Python |  |
| [homebrew-tap](https://github.com/buchochelliq-labs/homebrew-tap) | Homebrew formulae: `brew install buchochelliq-labs/tap/ods`. | Ruby |  |
| [open-data-suite](https://github.com/buchochelliq-labs/open-data-suite) | Rust-first, provider-neutral control plane for analytics engineering (dbt, Databricks). | Rust | [Site](https://buchochelliq-labs.github.io/open-data-suite/) |
| [open-data-suite-ontology](https://github.com/buchochelliq-labs/open-data-suite-ontology) | Layered, provenance-preserving ontology served to agents over MCP. | Rust |  |

## rs-rich { #rs-rich }

| Repository | Description | Language | Docs |
|---|---|---|---|
| [rs-rich-cli](https://github.com/buchochelliq-labs/rs-rich-cli) | Python's rich, ported to Rust byte for byte, plus the intuiTUIve TUI framework. | Rust | [Site](https://buchochelliq-labs.github.io/rs-rich-cli/) |
| [rs-rich-doom](https://github.com/buchochelliq-labs/rs-rich-doom) | Doom in the terminal, drawn and driven by rs-rich. | C |  |
| [rs-rich-marketplace](https://github.com/buchochelliq-labs/rs-rich-marketplace) | The signed plugin marketplace index for rs-rich. | Python | [Site](https://buchochelliq-labs.github.io/rs-rich-marketplace/) |

## Tooling and organisation { #other }

| Repository | Description | Language | Docs |
|---|---|---|---|
| [release-kit](https://github.com/buchochelliq-labs/release-kit) | The org's release standard: one file, one command, every registry. | Python | [Site](https://buchochelliq-labs.github.io/release-kit/) |
