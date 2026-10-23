"""Read-only CLI for policy validation, explicit naming and document discovery."""

import argparse
import json
import sys

from .modelling_policy import PolicyError, discover_policy_files, load_document, resolve_policy_name
from .project import ProjectError, discover_project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "discover", "render", "infer", "compare", "propose"):
        command = commands.add_parser(name)
        command.add_argument("path")
        if name in ("infer", "compare", "propose"):
            command.add_argument("--target-path")
        if name == "propose":
            command.add_argument("--policy", required=True)
            command.add_argument("--rule", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("--rationale", required=True)
            command.add_argument("--decision", choices=("exception", "standard_change"), default="exception")
            command.add_argument("--template")
            command.add_argument("--proposals")
        if name == "compare":
            command.add_argument("--policy", required=True)
            command.add_argument("--model")
            command.add_argument("--context", action="append", default=[], metavar="DIMENSION=VALUE")
        if name == "render":
            command.add_argument("--rule", required=True)
            command.add_argument("--value", action="append", default=[], metavar="TOKEN=VALUE")
    args = parser.parse_args(argv)
    try:
        if args.command == "propose":
            from .decision_proposals import prepare_decision
            result = prepare_decision(discover_project(args.path, target_path=args.target_path), args.policy,
                                      args.rule, args.model, args.rationale, decision=args.decision,
                                      template=args.template, proposals_path=args.proposals)
        elif args.command == "compare":
            from .policy_comparison import compare_model_names
            context = {}
            for item in args.context:
                key, separator, value = item.partition("=")
                if not separator or key in context:
                    raise PolicyError("Context requires unique DIMENSION=VALUE arguments")
                context[key] = value
            result = compare_model_names(discover_project(args.path, target_path=args.target_path), args.policy,
                                         model_id=args.model, context=context)
        elif args.command == "infer":
            from .convention_discovery import infer_conventions
            result = infer_conventions(discover_project(args.path, target_path=args.target_path))
        elif args.command == "discover":
            result = discover_policy_files(args.path)
        elif args.command == "validate":
            loaded = load_document(args.path)
            result = {"status": "valid", "kind": loaded["document"]["kind"], "provenance": loaded["provenance"]}
        else:
            values = {}
            for item in args.value:
                key, separator, value = item.partition("=")
                if not separator or key in values:
                    raise PolicyError("Values require unique TOKEN=VALUE arguments")
                values[key] = value
            result = resolve_policy_name(args.path, args.rule, values)
        print(json.dumps(result, indent=2))
        return 0
    except PolicyError as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 2
    except ProjectError:
        print(json.dumps({"status": "error", "message": "Cannot inspect the selected dbt project"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
