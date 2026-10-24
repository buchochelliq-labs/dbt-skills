"""Loopback application boundary: delegates context to the existing MCP core."""

import argparse, asyncio, json, os, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from mcp import Client
from .modelling_mcp import create_server
from .project import discover_project
from .workspace_store import (
    WorkspaceStore,
    WorkspaceError,
    WorkspaceConflict,
    EnvironmentKeyStore,
)
from .native_publication import validate_proposal, export_handoff


class CoreBridge:
    def __init__(self, project, **options):
        self.server = create_server(project, **options)
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(20) or self.error:
            raise WorkspaceError("Context service could not start")

    def _run(self):
        async def serve():
            self.loop = asyncio.get_running_loop()
            self.stop = asyncio.Event()
            try:
                async with Client(self.server, raise_exceptions=True) as self.client:
                    self.allowed = {
                        t.name for t in (await self.client.list_tools()).tools
                    }
                    self.ready.set()
                    await self.stop.wait()
            except Exception:
                self.error = True
                self.ready.set()

        asyncio.run(serve())

    def call(self, name, args):
        if name not in self.allowed or not isinstance(args, dict):
            raise WorkspaceError("Unsupported context operation")

        async def run():
            result = await self.client.call_tool(name, args)
            if result.is_error:
                raise WorkspaceError("Context rejected; refresh or correct the request")
            return result.structured_content

        future = asyncio.run_coroutine_threadsafe(run(), self.loop)
        try:
            return future.result(30)
        except Exception:
            future.cancel()
            raise WorkspaceError(
                "Context rejected; refresh or correct the request. No fallback was used."
            ) from None

    def preferences(self, preferences):
        self.server.application_preferences(preferences)

    def catalog_snapshot(self):
        return self.server.application_catalog_snapshot()

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        self.thread.join(5)


class Application:
    def __init__(self, bridge, store, ontology=None):
        self.bridge = bridge
        self.store = store
        self.ontology = ontology

    def dispatch(self, path, body):
        if not isinstance(body, dict):
            raise WorkspaceError("JSON object required")
        if path == "/api/application/read":
            if self.ontology is None:
                raise WorkspaceError("Application repository not configured")
            return self.ontology.read(body.get("reader"))
        if path == "/api/application/command":
            if self.ontology is None:
                raise WorkspaceError("Application repository not configured")
            return self.ontology.command(
                body.get("name"),
                body.get("payload", {}),
                expected_revision=body.get("expected_revision"),
                reader=body.get("reader"),
            )
        if path == "/api/context":
            return self.bridge.call("modelling_context", {})
        if path == "/api/tools":
            return {
                "schema_version": 1,
                "tools": sorted(self.bridge.allowed),
                "simulation": False,
                "source_records": False,
                "native_writes": False,
            }
        if path == "/api/tool":
            return (
                self.ontology.agent_context(body.get("name"), body.get("arguments", {}))
                if self.ontology
                else self.bridge.call(body.get("name"), body.get("arguments", {}))
            )
        if path == "/api/workspace/read":
            return {**self.store.read(), "history": self.store.history()}
        if path == "/api/workspace/save":
            return self.store.save(
                body.get("document"),
                body.get("expected_revision"),
                body.get("reason", "workspace edit"),
            )
        if path == "/api/workspace/export":
            return self.store.export()
        if path == "/api/workspace/import/preview":
            return self.store.preview_import(body)
        if path == "/api/workspace/import/apply":
            return self.store.apply_import(body.get("preview_id"))
        if path == "/api/publication/check":
            return validate_proposal(body)
        if path == "/api/publication/export":
            return export_handoff(body)
        raise WorkspaceError("Unsupported application operation")


def make_handler(app, token, origins):
    class Handler(BaseHTTPRequestHandler):
        server_version = "UOLLocal/1"

        def log_message(self, *args):
            pass  # never log request paths, tokens or metadata

        def reply(self, status, value):
            payload = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            # Same-origin proxy only. CLI tests may omit Origin, but still require bearer.
            if self.headers.get("Host") not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                return self.reply(403, {"error": "Request not permitted"})
            if (
                self.headers.get("Origin") is not None
                and self.headers["Origin"] not in origins
            ):
                return self.reply(403, {"error": "Request not permitted"})
            if not secrets.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + token
            ):
                return self.reply(
                    401, {"error": "Local session authentication required"}
                )
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON required"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= 1048576:
                    raise ValueError()
                raw = self.rfile.read(n)

                def pairs(items):
                    result = {}
                    for k, v in items:
                        if k in result:
                            raise ValueError()
                        result[k] = v
                    return result

                body = json.loads(
                    raw,
                    object_pairs_hook=pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                )
            except Exception:
                return self.reply(400, {"error": "Invalid bounded JSON request"})
            try:
                self.reply(200, app.dispatch(self.path, body))
            except WorkspaceConflict:
                self.reply(
                    409,
                    {"error": "Workspace changed; reload and review before applying"},
                )
            except WorkspaceError as error:
                self.reply(400, {"error": str(error)})
            except (ValueError, TypeError, KeyError):
                self.reply(
                    400,
                    {
                        "error": "Request rejected; check schema, context and selected revisions"
                    },
                )
            except Exception:
                self.reply(
                    503, {"error": "Local service unavailable; no fallback was used"}
                )

        def do_GET(self):
            self.reply(405, {"error": "Use authenticated POST"})

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-dir", required=True)
    p.add_argument("--target-path", default="artifacts")
    p.add_argument("--policy", default="modelling.yml")
    p.add_argument("--catalog-config", default="catalogs.json")
    p.add_argument("--business-context")
    p.add_argument("--design-decisions")
    p.add_argument("--store", required=True)
    p.add_argument("--key-env")
    p.add_argument("--application-store")
    p.add_argument(
        "--fixture-state",
        help="Explicit fictional simulation fixture, never used as a live fallback",
    )
    p.add_argument("--reader", choices=["steward", "restricted"], default="steward")
    p.add_argument("--native-config")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--origin",
        action="append",
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    args = p.parse_args()
    token = os.environ.get("UOL_LOCAL_TOKEN", "")
    if len(token) < 32:
        p.error(
            "Set UOL_LOCAL_TOKEN to a random local session secret of at least 32 characters"
        )
    bridge = CoreBridge(
        discover_project(args.project_dir, target_path=args.target_path),
        policy_path=args.policy,
        catalog_path=args.catalog_config,
        business_context_path=args.business_context,
        design_decisions_path=args.design_decisions,
    )
    try:
        store = WorkspaceStore(
            args.store,
            key_store=EnvironmentKeyStore(args.key_env) if args.key_env else None,
        )
        from .application_store import ApplicationStore, empty_state
        from .application_api import OntologyApplication

        initial = (
            json.loads(Path(args.fixture_state).read_text())
            if args.fixture_state
            else empty_state()
        )
        if not initial["domains"]:
            initial["domains"] = [
                dict(
                    id="enterprise",
                    name="Enterprise",
                    parent=None,
                    description="Local ontology workspace",
                    owner=None,
                    technicalOwner=None,
                    steward=None,
                    providerPolicy=None,
                    ttl=None,
                )
            ]
        application_store = ApplicationStore(
            args.application_store or str(args.store) + ".application",
            key_store=EnvironmentKeyStore(args.key_env) if args.key_env else None,
            initial_state=initial,
            simulation=bool(args.fixture_state),
        )
        ontology = OntologyApplication(
            application_store, bridge=bridge, reader=args.reader
        )
        ontology.fixture_initial = initial if args.fixture_state else None
        if args.native_config:
            from .native_observation import adapter_from_config

            def current_origin(origin):
                for k in application_store.read()["state"]["knowledge"]:
                    if k["originId"] == origin["id"]:
                        return str(k["version"])
                raise WorkspaceError("Origin unavailable")

            native_config = json.loads(Path(args.native_config).read_text())
            ontology.native_adapter = adapter_from_config(
                native_config, origin_revision_reader=current_origin
            )
            ontology.configure_native_targets(native_config)
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            make_handler(Application(bridge, store, ontology), token, set(args.origin)),
        )
        server.daemon_threads = True
        server.serve_forever()
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
