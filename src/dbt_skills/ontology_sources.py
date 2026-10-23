"""Local dbt artifact sources projected into the Unified Ontology Layer."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from dbt_skills.ods_mcp import ODSAnalysis, ODSMCPConfig, ODSUnavailable, analyze_ods
from dbt_skills.ontology import (
    JsonObject,
    JSONSnapshotProvider,
    LocalOntologyStore,
    OntologyClaim,
    OntologyProvider,
    ProviderContractError,
    SyncPage,
)
from dbt_skills.project import ProjectError, ProjectInfo, discover_project


DBT_MANIFEST_PROVIDER = "dbt_manifest"
ODS_LINEAGE_PROVIDER = "ods_column_lineage"
_ARTIFACT_COLLECTIONS = (
    "nodes",
    "sources",
    "exposures",
    "metrics",
    "semantic_models",
    "saved_queries",
)
_MAX_PROJECTED_CLAIMS = 100_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def manifest_source_id(project: ProjectInfo) -> str:
    identity = os.path.normcase(str(project.root.resolve()))
    return f"dbt-manifest:{_digest(identity)[:16]}"


def ods_source_id(project: ProjectInfo, target_dir: str | Path) -> str:
    identity = f"{os.path.normcase(str(project.root.resolve()))}|{os.path.normcase(str(Path(target_dir).resolve()))}"
    return f"ods-column-lineage:{_digest(identity)[:16]}"


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


class ManifestSnapshotProvider:
    """Read a matching dbt manifest as resource and resource-lineage claims."""

    provider_name = DBT_MANIFEST_PROVIDER
    supports_incremental = False

    def __init__(self, project_dir: str | Path, manifest_path: str | Path | None = None):
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.manifest_path = (
            Path(manifest_path).expanduser().resolve()
            if manifest_path is not None
            else None
        )
        self._cached_revision: str | None = None
        self._cached_claims: list[OntologyClaim] | None = None

    def _read_claims(self, content: bytes) -> tuple[list[OntologyClaim], str]:
        try:
            project = discover_project(
                self.project_dir,
                target_path=self.manifest_path.parent if self.manifest_path is not None else None,
            )
        except ProjectError as error:
            raise ProviderContractError(str(error)) from error
        path = self.manifest_path or project.manifest_path
        try:
            document = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProviderContractError(
                f"dbt manifest is invalid JSON ({type(error).__name__})"
            ) from None
        if not isinstance(document, Mapping):
            raise ProviderContractError("dbt manifest must contain a JSON object")
        metadata = document.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ProviderContractError("dbt manifest has no metadata object")
        manifest_project = _string(metadata.get("project_name"))
        if manifest_project is None:
            raise ProviderContractError("dbt manifest has no project identity")
        if manifest_project != project.name:
            raise ProviderContractError(
                f"dbt manifest project {manifest_project!r} does not match "
                f"selected project {project.name!r}"
            )
        schema_version = _string(metadata.get("dbt_schema_version"))
        dbt_version = _string(metadata.get("dbt_version"))
        generated_at = _string(metadata.get("generated_at"))
        source_version = schema_version or dbt_version or "unknown"
        observed_at = _now()
        artifact_revision = _digest(content)
        common_evidence: JsonObject = {
            "project_name": project.name,
            "manifest_generated_at": generated_at,
            "dbt_schema_version": schema_version,
            "dbt_version": dbt_version,
            "invocation_id": _string(metadata.get("invocation_id")),
            "artifact": str(path),
            "artifact_sha256": artifact_revision,
        }

        resources: dict[str, Mapping[str, object]] = {}
        for collection_name in _ARTIFACT_COLLECTIONS:
            collection = document.get(collection_name, {})
            if collection is None:
                continue
            if not isinstance(collection, Mapping):
                raise ProviderContractError(
                    f"dbt manifest {collection_name} must be an object"
                )
            for unique_id, raw in collection.items():
                if not isinstance(unique_id, str) or not isinstance(raw, Mapping):
                    continue
                resources[unique_id] = raw

        claims: list[OntologyClaim] = []
        for unique_id, resource in sorted(resources.items()):
            resource_type = _string(resource.get("resource_type"))
            if resource_type is None:
                resource_type = unique_id.split(".", 1)[0]
            resource_value = {
                key: value
                for key in (
                    "name",
                    "resource_type",
                    "package_name",
                    "original_file_path",
                    "database",
                    "schema",
                    "alias",
                    "description",
                )
                if (value := _string(resource.get(key))) is not None
            }
            claims.append(
                OntologyClaim(
                    claim_id=f"resource:{unique_id}",
                    subject_id=unique_id,
                    predicate="dbt_resource",
                    object_value=resource_value,
                    object_kind="literal",
                    native_id=unique_id,
                    namespace=project.name,
                    entity_type=resource_type,
                    source_version=source_version,
                    observed_at=observed_at,
                    evidence=dict(common_evidence),
                    derivation={"kind": "manifest_resource"},
                )
            )
            dependencies = resource.get("depends_on")
            dependency_ids = dependencies.get("nodes", []) if isinstance(dependencies, Mapping) else []
            if not isinstance(dependency_ids, list):
                raise ProviderContractError(
                    f"dbt manifest dependency list is invalid for {unique_id}"
                )
            for dependency_id in sorted(set(item for item in dependency_ids if isinstance(item, str))):
                claims.append(
                    OntologyClaim(
                        claim_id=f"depends:{unique_id}:{dependency_id}",
                        subject_id=unique_id,
                        predicate="depends_on",
                        object_value=dependency_id,
                        object_kind="entity",
                        native_id=f"{unique_id}->{dependency_id}",
                        namespace=project.name,
                        entity_type="resource_lineage",
                        source_version=source_version,
                        observed_at=observed_at,
                        evidence=dict(common_evidence),
                        derivation={"kind": "manifest_resource_lineage"},
                    )
                )
        if not claims:
            raise ProviderContractError("dbt manifest contains no supported project resources")
        if len(claims) > _MAX_PROJECTED_CLAIMS:
            raise ProviderContractError(
                f"dbt manifest projection exceeds {_MAX_PROJECTED_CLAIMS} claims"
            )
        return claims, artifact_revision

    async def fetch_page(
        self,
        *,
        cursor: str | None,
        page_size: int,
        full_refresh: bool,
    ) -> SyncPage:
        del full_refresh
        path = self.manifest_path
        if path is None:
            try:
                project = await asyncio.to_thread(discover_project, self.project_dir)
            except ProjectError as error:
                raise ProviderContractError(str(error)) from error
            path = project.manifest_path
        try:
            content = await asyncio.to_thread(path.read_bytes)
        except OSError as error:
            raise ProviderContractError(
                f"Cannot read dbt manifest {path}: {error}"
            ) from error
        revision = _digest(content)
        offset = 0
        if cursor:
            try:
                cursor_revision, raw_offset = cursor.split(":", 1)
                offset = int(raw_offset)
            except ValueError as error:
                raise ProviderContractError("dbt manifest cursor is invalid") from error
            if cursor_revision != revision:
                raise ProviderContractError(
                    "dbt manifest changed during a resumable sync; restart the refresh"
                )
        if self._cached_revision == revision and self._cached_claims is not None:
            claims = self._cached_claims
        else:
            claims, _ = await asyncio.to_thread(self._read_claims, content)
            self._cached_revision = revision
            self._cached_claims = claims
        if offset < 0 or offset > len(claims):
            raise ProviderContractError("dbt manifest cursor is outside the artifact")
        selected = claims[offset : offset + page_size]
        next_offset = offset + len(selected)
        done = next_offset >= len(claims)
        return SyncPage(
            claims=selected,
            next_cursor=None if done else f"{revision}:{next_offset}",
            done=done,
        )


def _column_id(endpoint: Mapping[str, object]) -> str:
    model = next(
        (
            value
            for key in ("model", "node", "resource", "unique_id", "id", "name")
            if (value := _string(endpoint.get(key))) is not None
        ),
        None,
    )
    column = _string(endpoint.get("column"))
    if model and column:
        return f"{model}.{column}"
    return f"ods-column:{_stable_json(dict(endpoint))}"


def ods_analysis_to_claims(
    analysis: ODSAnalysis,
    project: ProjectInfo,
) -> list[OntologyClaim]:
    """Convert one ODS analysis without upgrading missing output to zero lineage."""
    summary = analysis.project_summary
    dbt_version = _string(summary.get("dbt_version"))
    if dbt_version is None:
        raise ProviderContractError("ODS result has no dbt version")
    if summary.get("project_name") not in (None, project.name):
        raise ProviderContractError(
            f"ODS project {summary.get('project_name')!r} does not match "
            f"selected project {project.name!r}"
        )
    lineage = analysis.lineage
    raw_edges = lineage.get("column_edges", [])
    if not isinstance(raw_edges, list):
        raise ProviderContractError("ODS column_edges must be a list")
    if len(raw_edges) > _MAX_PROJECTED_CLAIMS:
        raise ProviderContractError(
            f"ODS result exceeds {_MAX_PROJECTED_CLAIMS} column edges"
        )

    observed_at = _now()
    common_evidence: JsonObject = {
        "project_name": project.name,
        "target_dir": summary.get("target_dir"),
        "dbt_version": dbt_version,
        "ods_server_version": analysis.provider_version,
        "mcp_protocol_version": analysis.protocol_version,
        "analysis_coverage": analysis.coverage,
        "analysis_reason": analysis.reason,
        "artifact_source": summary.get("artifacts"),
        "observed_at": observed_at,
    }
    claims = [
        OntologyClaim(
            claim_id="column-lineage-coverage",
            subject_id=f"dbt_project:{project.name}",
            predicate="column_lineage_coverage",
            object_value=analysis.coverage,
            object_kind="literal",
            native_id=f"{project.name}:{summary.get('target_dir')}",
            namespace=project.name,
            entity_type="lineage_coverage",
            source_version=analysis.provider_version,
            observed_at=observed_at,
            evidence={
                **common_evidence,
                "opaque_models": analysis.opaque.get("opaque", []),
            },
            derivation={"kind": "ods_static_sql_analysis"},
        )
    ]
    seen: set[str] = set()
    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            raise ProviderContractError("ODS column lineage edge must be an object")
        source = edge.get("from")
        target = edge.get("to")
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            raise ProviderContractError("ODS column lineage edge needs from/to objects")
        source_id = _column_id(source)
        target_id = _column_id(target)
        if source_id == target_id:
            raise ProviderContractError("ODS column lineage edge cannot link a column to itself")
        edge_revision = _digest(_stable_json(dict(edge)))
        if edge_revision in seen:
            continue
        seen.add(edge_revision)
        claims.append(
            OntologyClaim(
                claim_id=f"column-edge:{edge_revision}",
                subject_id=target_id,
                predicate="column_depends_on",
                object_value=source_id,
                object_kind="entity",
                native_id=edge_revision,
                namespace=project.name,
                entity_type="column_lineage",
                source_version=analysis.provider_version,
                observed_at=observed_at,
                evidence={**common_evidence, "ods_edge": dict(edge)},
                derivation={
                    "kind": "ods_static_column_lineage",
                    "edge_kind": edge.get("kind"),
                },
            )
        )
    opaque_records = analysis.opaque.get("opaque", [])
    if isinstance(opaque_records, list):
        for index, opaque in enumerate(opaque_records):
            if not isinstance(opaque, Mapping):
                continue
            opaque_name = _string(opaque.get("name")) or f"unknown-{index}"
            claims.append(
                OntologyClaim(
                    claim_id=f"opaque:{_digest(_stable_json(dict(opaque)))}",
                    subject_id=f"dbt_resource:{project.name}.{opaque_name}",
                    predicate="column_lineage_unavailable",
                    object_value={
                        "reason": opaque.get("reason"),
                        "diagnostics": opaque.get("diagnostics", []),
                    },
                    object_kind="literal",
                    native_id=_string(opaque.get("id")),
                    namespace=project.name,
                    entity_type="lineage_diagnostic",
                    source_version=analysis.provider_version,
                    observed_at=observed_at,
                    evidence=dict(common_evidence),
                    derivation={"kind": "ods_opaque_model_diagnostic"},
                )
            )
    if len(claims) > _MAX_PROJECTED_CLAIMS:
        raise ProviderContractError(
            f"ODS result projection exceeds {_MAX_PROJECTED_CLAIMS} claims"
        )
    return claims


class ClaimsSnapshotProvider:
    """Immutable claim snapshot with revision-checked pagination."""

    supports_incremental = False

    def __init__(self, provider_name: str, claims: Sequence[OntologyClaim]):
        self.provider_name = provider_name
        self.claims = tuple(claims)
        self.revision = _digest(
            _stable_json(
                [
                    {
                        "claim_id": claim.claim_id,
                        "subject_id": claim.subject_id,
                        "predicate": claim.predicate,
                        "object_value": claim.object_value,
                    }
                    for claim in self.claims
                ]
            )
        )

    async def fetch_page(
        self,
        *,
        cursor: str | None,
        page_size: int,
        full_refresh: bool,
    ) -> SyncPage:
        del full_refresh
        offset = 0
        if cursor:
            try:
                revision, raw_offset = cursor.split(":", 1)
                offset = int(raw_offset)
            except ValueError as error:
                raise ProviderContractError("snapshot cursor is invalid") from error
            if revision != self.revision:
                raise ProviderContractError("snapshot changed during a resumable sync")
        if offset < 0 or offset > len(self.claims):
            raise ProviderContractError("snapshot cursor is outside the claim set")
        selected = self.claims[offset : offset + page_size]
        next_offset = offset + len(selected)
        done = next_offset >= len(self.claims)
        return SyncPage(
            claims=selected,
            next_cursor=None if done else f"{self.revision}:{next_offset}",
            done=done,
        )


class ODSLineageProvider:
    """Optional ODS MCP adapter whose results are projected as column claims."""

    provider_name = ODS_LINEAGE_PROVIDER
    supports_incremental = False

    def __init__(
        self,
        *,
        config: ODSMCPConfig,
        project: ProjectInfo,
        focus: Sequence[str],
        changes: Sequence[str],
    ):
        self.config = config
        self.project = project
        self.focus = tuple(focus)
        self.changes = tuple(changes)
        self._snapshot: ClaimsSnapshotProvider | None = None

    async def fetch_page(
        self,
        *,
        cursor: str | None,
        page_size: int,
        full_refresh: bool,
    ) -> SyncPage:
        if self._snapshot is None:
            result = await analyze_ods(
                self.config,
                focus=self.focus,
                changes=self.changes,
            )
            if isinstance(result, ODSUnavailable):
                raise ProviderContractError(
                    f"ODS lineage is unavailable: {result.reason}"
                )
            self._snapshot = ClaimsSnapshotProvider(
                self.provider_name,
                ods_analysis_to_claims(result, self.project),
            )
        return await self._snapshot.fetch_page(
            cursor=cursor,
            page_size=page_size,
            full_refresh=full_refresh,
        )


def configured_provider(
    store: LocalOntologyStore,
    source_id: str,
    *,
    selected_project: ProjectInfo | None = None,
) -> OntologyProvider:
    """Recreate a configured local provider without enabling or changing it."""
    config = store.source_config(source_id)
    provider_name = config.get("provider_name")
    options = config.get("options")
    if not isinstance(options, Mapping):
        raise ProviderContractError(f"Source {source_id} has invalid provider options")

    if provider_name == JSONSnapshotProvider.provider_name:
        snapshot_path = _string(options.get("snapshot_path"))
        if snapshot_path is None:
            raise ProviderContractError(f"JSON source {source_id} has no snapshot path")
        return JSONSnapshotProvider(snapshot_path)

    if provider_name == DBT_MANIFEST_PROVIDER:
        project_dir = _string(options.get("project_dir"))
        manifest_path = _string(options.get("manifest_path"))
        if project_dir is None:
            raise ProviderContractError(f"Manifest source {source_id} has no project directory")
        try:
            project = discover_project(
                project_dir,
                target_path=Path(manifest_path).expanduser().resolve().parent if manifest_path else None,
            )
        except ProjectError as error:
            raise ProviderContractError(str(error)) from error
        if selected_project is not None and project.root != selected_project.root:
            raise ProviderContractError(
                f"Manifest source {source_id} does not match the selected dbt project"
            )
        return ManifestSnapshotProvider(project.root, manifest_path)

    if provider_name == ODS_LINEAGE_PROVIDER:
        project_dir = _string(options.get("project_dir"))
        target_dir = _string(options.get("target_dir"))
        command = _string(options.get("command"))
        artifacts = _string(options.get("artifacts")) or "auto"
        expected_version = _string(options.get("expected_version")) or "0.0.2"
        focus = options.get("focus")
        changes = options.get("changes")
        if (
            project_dir is None
            or target_dir is None
            or command is None
            or not isinstance(focus, list)
            or not focus
            or any(not isinstance(item, str) or not item.strip() for item in focus)
            or not isinstance(changes, list)
            or not changes
            or any(not isinstance(item, str) or not item.strip() for item in changes)
        ):
            raise ProviderContractError(f"ODS source {source_id} has incomplete configuration")
        try:
            project = discover_project(project_dir, target_path=Path(target_dir).expanduser().resolve())
        except ProjectError as error:
            raise ProviderContractError(str(error)) from error
        if selected_project is not None and project.root != selected_project.root:
            raise ProviderContractError(
                f"ODS source {source_id} does not match the selected dbt project"
            )
        if artifacts not in ("auto", "json", "info-schema"):
            raise ProviderContractError(f"ODS source {source_id} has invalid artifact mode")
        return ODSLineageProvider(
            config=ODSMCPConfig(
                command=command,
                project_dir=project.root,
                target_dir=Path(target_dir),
                artifacts=artifacts,
                expected_version=expected_version,
            ),
            project=project,
            focus=focus,
            changes=changes,
        )

    raise ProviderContractError(
        f"No local sync adapter is registered for provider {provider_name!r}"
    )
