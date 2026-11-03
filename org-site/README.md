# buchochelliq-labs.github.io

The landing page and documentation hub for [Buchochelliq Labs](https://github.com/buchochelliq-labs),
built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

Live at **https://buchochelliq-labs.github.io/**.

Each project keeps its own docs site at `https://buchochelliq-labs.github.io/<repo>/`.
This site links to those sites. It doesn't duplicate them.

## Develop

```sh
pip install -r requirements.txt
python scripts/gen_catalog.py   # refresh docs/catalog.md from the GitHub API
mkdocs serve                    # http://127.0.0.1:8000
```

## Layout

| Path | What it is |
|---|---|
| `docs/index.md` | Landing page |
| `docs/projects/` | One overview page per project family |
| `docs/catalog.md` | Generated list of every public repository. Don't edit it by hand. |
| `scripts/gen_catalog.py` | Catalog generator. Edit `GROUPS` and `FALLBACK_DESCRIPTIONS` here. |
| `.github/workflows/deploy.yml` | Builds and deploys to GitHub Pages on every push to `main`, and nightly |

## Adding a project

1. Add `docs/projects/<name>.md`.
2. Add it to `nav` in `mkdocs.yml` and to the cards in `docs/index.md`.
3. If the repository prefix doesn't match an existing group, add one to `GROUPS` in `scripts/gen_catalog.py`.
