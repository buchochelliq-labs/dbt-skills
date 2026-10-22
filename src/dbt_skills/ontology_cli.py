"""Command-line controls for the local Unified Ontology Layer."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from dbt_skills.ontology import (
    JSONSnapshotProvider,
    LocalOntologyStore,
    OntologyClaim,
    SyncScope,
    default_store_path,
)
from dbt_skills.ontology_sources import (
    DBT_MANIFEST_PROVIDER,
    ODS_LINEAGE_PROVIDER,
    configured_provider,
    manifest_source_id,
    ods_source_id,
)
from dbt_skills.project import discover_project


def _scope_from_args(args: argparse.Namespace) -> SyncScope:
    return SyncScope(
        include_namespaces=frozenset(args.include_namespace),
        exclude_namespaces=frozenset(args.exclude_namespace),
        include_entity_types=frozenset(args.include_entity_type),
        exclude_entity_types=frozenset(args.exclude_entity_type),
        include_properties=frozenset(args.include_property),
        exclude_properties=frozenset(args.exclude_property),
        include_record_ids=frozenset(args.include_record_id),
        exclude_record_ids=frozenset(args.exclude_record_id),
    )


def _add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--include-namespace", action="append", default=[])
    parser.add_argument("--exclude-namespace", action="append", default=[])
    parser.add_argument("--include-entity-type", action="append", default=[])
    parser.add_argument("--exclude-entity-type", action="append", default=[])
    parser.add_argument("--include-property", action="append", default=[])
    parser.add_argument("--exclude-property", action="append", default=[])
    parser.add_argument("--include-record-id", action="append", default=[])
    parser.add_argument("--exclude-record-id", action="append", default=[])


def _json_arg(value: str, label: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} must be valid JSON: {error}") from error


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbt-skills-uol",
        description="Manage the local Unified Ontology Layer cache and overlay.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path (default: current user's application-data folder)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    source = commands.add_parser("source", help="Configure ontology sources")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add_json = source_commands.add_parser(
        "add-json", help="Register a local JSON snapshot source (sync starts disabled)"
    )
    add_json.add_argument("source_id")
    add_json.add_argument("snapshot", type=Path)
    add_json.add_argument("--enable", action="store_true")
    _add_scope_arguments(add_json)

    add_manifest = source_commands.add_parser(
        "add-manifest", help="Register one project's dbt manifest as a disabled source"
    )
    add_manifest.add_argument("source_id")
    add_manifest.add_argument("project_dir", type=Path)
    add_manifest.add_argument("--manifest", type=Path)
    add_manifest.add_argument("--enable", action="store_true")
    _add_scope_arguments(add_manifest)

    add_ods = source_commands.add_parser(
        "add-ods", help="Register an optional ODS MCP lineage source as disabled"
    )
    add_ods.add_argument("source_id")
    add_ods.add_argument("ods_command")
    add_ods.add_argument("project_dir", type=Path)
    add_ods.add_argument("target_dir", type=Path)
    add_ods.add_argument("--artifacts", choices=("auto", "json", "info-schema"), default="auto")
    add_ods.add_argument("--expected-version", default="0.0.2")
    add_ods.add_argument("--focus", action="append", required=True)
    add_ods.add_argument("--change", action="append", required=True)
    add_ods.add_argument("--enable", action="store_true")
    _add_scope_arguments(add_ods)

    set_enabled = source_commands.add_parser("enable", help="Enable a source for sync")
    set_enabled.add_argument("source_id")
    set_disabled = source_commands.add_parser("disable", help="Pause sync for a source")
    set_disabled.add_argument("source_id")

    set_scope = source_commands.add_parser(
        "scope", help="Replace a source's sync scope and discard its cached snapshot"
    )
    set_scope.add_argument("source_id")
    _add_scope_arguments(set_scope)

    commands.add_parser("status", help="Show source sync status and cache-read setting")
    sync = commands.add_parser("sync", help="Synchronize one configured source")
    sync.add_argument("source_id")
    sync.add_argument("--full-refresh", action="store_true")
    sync.add_argument(
        "--restart",
        action="store_true",
        help="Discard any incomplete sync and start a fresh full refresh",
    )
    sync.add_argument("--page-size", type=int, default=500)

    cache_reads = commands.add_parser("cache-reads", help="Enable or disable provider-cache reads")
    cache_reads.add_argument("setting", choices=("on", "off"))

    purge = commands.add_parser("purge", help="Purge synchronized provider data, not the local overlay")
    purge_group = purge.add_mutually_exclusive_group(required=True)
    purge_group.add_argument("--source")
    purge_group.add_argument("--all-sources", action="store_true")

    search = commands.add_parser("search", help="Search the local indexed ontology")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    neighborhood = commands.add_parser("neighbors", help="Traverse local relationships")
    neighborhood.add_argument("entity_id")
    neighborhood.add_argument("--depth", type=int, default=1)
    neighborhood.add_argument("--max-claims", type=int, default=500)

    add_claim = commands.add_parser("overlay-add", help="Add an attributed local assertion")
    add_claim.add_argument("--subject", required=True)
    add_claim.add_argument("--predicate", required=True)
    add_claim.add_argument("--object-json", required=True)
    add_claim.add_argument("--kind", choices=("literal", "entity"), default="literal")
    add_claim.add_argument("--author", required=True)
    add_claim.add_argument("--claim-id", default=None)
    add_claim.add_argument("--namespace")
    add_claim.add_argument("--entity-type")
    add_claim.add_argument("--evidence-json", default="{}")
    add_claim.add_argument("--rationale")

    link = commands.add_parser("overlay-link", help="Add an evidence-backed local link between claims")
    link.add_argument("--subject-source", required=True)
    link.add_argument("--subject-claim", required=True)
    link.add_argument("--predicate", required=True)
    link.add_argument("--object-source", required=True)
    link.add_argument("--object-claim", required=True)
    link.add_argument("--evidence-json", required=True)
    link.add_argument("--author", required=True)
    link.add_argument("--rationale")

    delete_claim = commands.add_parser("overlay-delete", help="Delete one local overlay assertion")
    delete_claim.add_argument("claim_id")
    commands.add_parser("overlay-clear", help="Delete all user-authored local overlay assertions")
    return parser


def _store(args: argparse.Namespace) -> LocalOntologyStore:
    return LocalOntologyStore(args.db or default_store_path())


def _run(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.command == "source":
        if args.source_command in ("add-json", "add-manifest", "add-ods"):
            if args.source_command == "add-json":
                source_id = args.source_id
                snapshot = args.snapshot.expanduser().resolve()
                if not snapshot.is_file():
                    raise FileNotFoundError(f"Ontology JSON snapshot not found: {snapshot}")
                provider_name = JSONSnapshotProvider.provider_name
                options = {"snapshot_path": str(snapshot)}
            elif args.source_command == "add-manifest":
                project = discover_project(args.project_dir)
                manifest = (
                    args.manifest.expanduser().resolve()
                    if args.manifest
                    else project.manifest_path
                )
                if args.source_id == "auto":
                    source_id = manifest_source_id(project)
                else:
                    source_id = args.source_id
                if not manifest.is_file():
                    raise FileNotFoundError(f"dbt manifest not found: {manifest}")
                provider_name = DBT_MANIFEST_PROVIDER
                options = {
                    "project_dir": str(project.root),
                    "manifest_path": str(manifest),
                }
            else:
                project = discover_project(args.project_dir)
                target_dir = args.target_dir.expanduser().resolve()
                source_id = (
                    ods_source_id(project, target_dir)
                    if args.source_id == "auto"
                    else args.source_id
                )
                provider_name = ODS_LINEAGE_PROVIDER
                options = {
                    "command": args.ods_command,
                    "project_dir": str(project.root),
                    "target_dir": str(target_dir),
                    "artifacts": args.artifacts,
                    "expected_version": args.expected_version,
                    "focus": args.focus,
                    "changes": args.change,
                }
            store.register_source(
                source_id,
                provider_name,
                scope=_scope_from_args(args),
                options=options,
                enabled=args.enable,
            )
            _print(store.source_status(source_id))
        elif args.source_command in ("enable", "disable"):
            store.set_source_enabled(args.source_id, args.source_command == "enable")
            _print(store.source_status(args.source_id))
        elif args.source_command == "scope":
            store.configure_source_scope(args.source_id, _scope_from_args(args))
            _print(store.source_status(args.source_id))
        return 0

    if args.command == "status":
        _print(
            {
                "cache_reads_enabled": store.cache_reads_enabled(),
                "sources": store.sources(),
            }
        )
    elif args.command == "sync":
        if args.restart:
            store.discard_pending_sync(args.source_id)
        result = asyncio.run(
            store.sync_source(
                args.source_id,
                configured_provider(store, args.source_id),
                full_refresh=args.full_refresh or args.restart,
                page_size=args.page_size,
            )
        )
        _print(result)
    elif args.command == "cache-reads":
        store.set_cache_reads_enabled(args.setting == "on")
        _print({"cache_reads_enabled": store.cache_reads_enabled()})
    elif args.command == "purge":
        if args.all_sources:
            store.purge_provider_cache()
        else:
            store.purge_source_cache(args.source)
        _print({"purged": "all_provider_cache" if args.all_sources else args.source})
    elif args.command == "search":
        _print([asdict(record) for record in store.search(args.query, limit=args.limit)])
    elif args.command == "neighbors":
        _print(
            [
                asdict(record)
                for record in store.neighborhood(
                    args.entity_id, depth=args.depth, max_claims=args.max_claims
                )
            ]
        )
    elif args.command == "overlay-add":
        claim = OntologyClaim(
            claim_id=args.claim_id or str(uuid.uuid4()),
            subject_id=args.subject,
            predicate=args.predicate,
            object_value=_json_arg(args.object_json, "object-json"),
            object_kind=args.kind,
            namespace=args.namespace,
            entity_type=args.entity_type,
            evidence=_json_arg(args.evidence_json, "evidence-json"),
        )
        _print(asdict(store.add_overlay_claim(claim, author=args.author, rationale=args.rationale)))
    elif args.command == "overlay-link":
        _print(
            asdict(
                store.create_link(
                    args.subject_source,
                    args.subject_claim,
                    args.predicate,
                    args.object_source,
                    args.object_claim,
                    evidence=_json_arg(args.evidence_json, "evidence-json"),
                    author=args.author,
                    rationale=args.rationale,
                )
            )
        )
    elif args.command == "overlay-delete":
        store.delete_overlay_claim(args.claim_id)
        _print({"deleted_overlay_claim": args.claim_id})
    elif args.command == "overlay-clear":
        store.clear_overlay()
        _print({"deleted": "all_overlay_claims"})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"dbt-skills-uol: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
