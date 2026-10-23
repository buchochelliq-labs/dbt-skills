"""Local dbt-skills project and scripted assistant CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from dbt_skills.project import (
    ProjectError,
    discover_project,
    initialize_project,
    load_runtime_config,
)
from dbt_skills.providers import ModelProviderError, OpenAICompatibleProvider
from dbt_skills.runtime import AgentRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbt-skills",
        description="Inspect a local dbt project or run a scripted project-grounded session.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create local runtime config in a dbt project")
    init.add_argument("--project-dir", default=".")
    init.add_argument("--target-path", help="Resolved artifact directory for project discovery")
    inspect = commands.add_parser("inspect", help="Identify a dbt project and its config")
    inspect.add_argument("--project-dir", default=".")
    inspect.add_argument("--target-path", help="Artifact directory, relative to the project root")
    inspect.add_argument("--artifacts", action="store_true", help="Read local artifact status and resource graph")
    inspect.add_argument("--stale-after-hours", type=float, default=24.0)
    ask = commands.add_parser("ask", help="Send one prompt to the configured model provider")
    ask.add_argument("prompt")
    ask.add_argument("--project-dir", default=".")
    ask.add_argument("--target-path", help="Resolved artifact directory for project discovery")
    ask.add_argument("--model")
    ask.add_argument("--base-url")
    ask.add_argument("--api-key-env")
    ask.add_argument("--timeout", type=float)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command == "init":
        path = initialize_project(args.project_dir, target_path=args.target_path)
        print(json.dumps({"config_path": str(path)}, indent=2))
        return 0

    project = discover_project(args.project_dir, target_path=args.target_path)
    if args.command == "inspect":
        result = project.to_json()
        if args.artifacts:
            from dbt_skills.project_artifacts import inspect_artifacts

            result["artifacts"] = inspect_artifacts(project, stale_after_hours=args.stale_after_hours)
        print(json.dumps(result, indent=2))
        return 0

    config = load_runtime_config(project)
    model = args.model or os.environ.get("DBT_SKILLS_MODEL") or config.model
    if not model:
        raise ProjectError(
            "No model configured; set model.model in .dbt-skills/config.toml "
            "or pass --model"
        )
    provider = OpenAICompatibleProvider(
        base_url=args.base_url or os.environ.get("DBT_SKILLS_BASE_URL") or config.base_url,
        model=model,
        api_key_env=args.api_key_env or config.api_key_env,
        timeout_seconds=(
            args.timeout if args.timeout is not None else config.timeout_seconds
        ),
    )
    reply = AgentRuntime(provider).ask(project, args.prompt)
    print(reply.text)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ProjectError, ModelProviderError, ValueError) as error:
        print(f"dbt-skills: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
