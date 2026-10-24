"""Authenticated, metadata-only native observations. There is deliberately no writer."""

from copy import deepcopy
import json
import os
from urllib.parse import urlsplit, quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .native_publication import fingerprint

MAX_BYTES = 2 * 1024 * 1024


class ObservationError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ObservationError("Native redirects are prohibited")


def _get(url, headers):
    request = Request(url, headers=headers, method="GET")
    with build_opener(_NoRedirect).open(request, timeout=15) as response:
        return response.status, response.read(MAX_BYTES + 1)


def _json(body):
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ObservationError("Invalid response size")
    value = json.loads(
        body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
    )
    if not isinstance(value, dict):
        raise ObservationError("Expected object")
    return value


class NativeObservationAdapter:
    def __init__(
        self,
        config,
        *,
        origin_revision_reader,
        authorization_reader=None,
        transport=None
    ):
        self.config = deepcopy(config)
        parsed = urlsplit(config["workspace_url"])
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.hostname not in config["trusted_hosts"]
        ):
            raise ObservationError("An explicitly trusted HTTPS workspace is required")
        self.base = config["workspace_url"].rstrip("/")
        self.token_env = config.get("token_env", "DATABRICKS_TOKEN")
        if not isinstance(self.token_env, str) or not self.token_env.isidentifier():
            raise ObservationError("Invalid token environment variable")
        self.targets = {}
        for target in config["targets"]:
            kind, identifier, origin = target["kind"], target["id"], target["origin_id"]
            if kind not in ("genie", "unity_catalog") or not all(
                isinstance(s, str) and s and len(s) <= 2048
                for s in (identifier, origin)
            ):
                raise ObservationError("Invalid configured target")
            key = (kind, identifier)
            if key in self.targets:
                raise ObservationError("Duplicate configured target")
            self.targets[key] = deepcopy(target)
        self.origin_reader = origin_revision_reader
        self.authorization_reader = authorization_reader
        self.transport = transport or _get

    def capabilities(self):
        # UC observations never carry a revision token. Genie requires its real etag.
        return {"read": True, "conditional_write": True, "write_implemented": False}

    def _request(self, path):
        token = os.environ.get(self.token_env)
        if not token or "\n" in token or "\r" in token:
            raise ObservationError("Native credentials unavailable")
        status, body = self.transport(
            self.base + path,
            {"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        if status != 200:
            raise ObservationError("Native read unavailable")
        return _json(body)

    def read_origin_revision(self, origin):
        if origin.get("id") not in {t["origin_id"] for t in self.targets.values()}:
            raise ObservationError("Origin not configured")
        revision = self.origin_reader(deepcopy(origin))
        if not isinstance(revision, str) or not revision:
            raise ObservationError("Origin revision unavailable")
        return revision

    def read_target(self, target):
        configured = self.targets.get((target.get("kind"), target.get("id")))
        if configured is None or set(target) - {"kind", "id"}:
            raise ObservationError("Target not allowlisted")
        identifier = quote(target["id"], safe="")
        token = None
        if target["kind"] == "genie":
            native = self._request(
                "/api/2.0/genie/spaces/" + identifier + "?include_serialized_space=true"
            )
            if native.get("space_id") != target["id"]:
                raise ObservationError("Native identity mismatch")
            serialized = native.get("serialized_space")
            if not isinstance(serialized, str):
                raise ObservationError("Serialized space unavailable")
            document = {
                k: deepcopy(native[k])
                for k in ("title", "description", "warehouse_id", "parent_path")
                if k in native
            }
            document["serialized_space"] = _json(serialized.encode())
            if isinstance(native.get("etag"), str) and native["etag"].strip():
                token = native["etag"]
        else:
            native = self._request("/api/2.1/unity-catalog/tables/" + identifier)
            if native.get("full_name") != target["id"]:
                raise ObservationError("Native identity mismatch")
            tags, page_token = {}, None
            for _ in range(20):
                path = (
                    "/api/2.1/unity-catalog/entity-tag-assignments/tables/"
                    + identifier
                    + "/tags"
                )
                if page_token:
                    path += "?" + urlencode({"page_token": page_token})
                page = self._request(path)
                assignments = page.get("tag_assignments", [])
                if not isinstance(assignments, list):
                    raise ObservationError("Invalid tags")
                for tag in assignments:
                    if (
                        tag.get("entity_name") != target["id"]
                        or tag.get("entity_type") != "tables"
                        or not isinstance(tag.get("tag_key"), str)
                        or tag["tag_key"] in tags
                    ):
                        raise ObservationError("Invalid tag identity")
                    tags[tag["tag_key"]] = tag.get("tag_value", "")
                page_token = page.get("next_page_token")
                if not page_token:
                    break
            else:
                raise ObservationError("Tag pagination exceeded")
            document = {"comment": native.get("comment"), "tags": tags}
        auth = (
            self.authorization_reader(deepcopy(target))
            if self.authorization_reader
            else {}
        )
        audience = auth.get("audience")
        if (
            not isinstance(audience, list)
            or not audience
            or any(not isinstance(x, str) or not x for x in audience)
        ):
            audience = None
        return {
            "document": document,
            "fingerprint": fingerprint(document),
            "revision_token": token,
            "permissions": {"read": True, "write": auth.get("write") is True},
            "audience": audience,
            "target": deepcopy(target),
            "origin_id": configured["origin_id"],
            "provenance": {
                "source": "authenticated_native_get",
                "workspace": self.base,
            },
            "saved_acknowledgement": "unknown",
        }


def adapter_from_config(
    config, *, origin_revision_reader, authorization_reader=None, transport=None
):
    """Operator-only factory; never accept this configuration from an HTTP proposal."""
    return NativeObservationAdapter(
        config,
        origin_revision_reader=origin_revision_reader,
        authorization_reader=authorization_reader,
        transport=transport,
    )
