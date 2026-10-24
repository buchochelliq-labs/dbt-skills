"""Read-only native publication planning. No network transport or write operation."""

from copy import deepcopy
import hashlib
import json
from typing import Protocol


class PublicationError(ValueError):
    """Malformed review proposal; adapter failures are returned as blocked results."""


class PublicationAdapter(Protocol):
    """Implementations must perform fresh authenticated reads, never cached evidence.

    Capabilities are operator configured, not supplied by a proposal. A conditional
    write capability means a verified native compare-and-swap token, not a local hash.
    This interface deliberately has no write method.
    """

    def capabilities(self) -> dict: ...
    def read_target(self, target: dict) -> dict: ...
    def read_origin_revision(self, origin: dict) -> str: ...


def fingerprint(document):
    return hashlib.sha256(
        json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _proposal(proposal):
    try:
        p = deepcopy(proposal)
        if p["schema_version"] != 1 or p["target"]["kind"] not in (
            "unity_catalog",
            "genie",
        ):
            raise ValueError()
        for value in (
            p["target"]["id"],
            p["origin"]["id"],
            p["origin"]["revision"],
            p["base_fingerprint"],
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 2048:
                raise ValueError()
        if len(p["base_fingerprint"]) != 64 or any(
            c not in "0123456789abcdef" for c in p["base_fingerprint"]
        ):
            raise ValueError()
        changes, selected, audience = (
            p["changes"],
            p["selected_change_ids"],
            p["intended_audience"],
        )
        if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
            raise ValueError()
        ids = []
        for change in changes:
            if (
                set(change) != {"id", "path", "value"}
                or not isinstance(change["id"], str)
                or not change["id"]
            ):
                raise ValueError()
            path = change["path"]
            if (
                not isinstance(path, list)
                or not 1 <= len(path) <= 20
                or any(not isinstance(k, str) or not k for k in path)
            ):
                raise ValueError()
            ids.append(change["id"])
        if (
            len(set(ids)) != len(ids)
            or not isinstance(selected, list)
            or not selected
            or any(not isinstance(x, str) for x in selected)
        ):
            raise ValueError()
        if len(set(selected)) != len(selected) or not set(selected) <= set(ids):
            raise ValueError()
        if (
            not isinstance(audience, list)
            or not audience
            or any(not isinstance(x, str) or not x for x in audience)
        ):
            raise ValueError()
        chosen = [c for c in changes if c["id"] in selected]
        for i, c in enumerate(chosen):
            for other in chosen[i + 1 :]:
                a, b = c["path"], other["path"]
                if a[: len(b)] == b or b[: len(a)] == a:
                    raise ValueError()
        if len(json.dumps(p, allow_nan=False).encode()) > 262144:
            raise ValueError()
        return p
    except (KeyError, TypeError, ValueError, OverflowError):
        raise PublicationError("Invalid bounded native publication proposal") from None


def _result(status, **fields):
    return {
        "schema_version": 1,
        "simulation": False,
        "native_write_performed": False,
        "status": status,
        **fields,
    }


def export_handoff(proposal):
    p = _proposal(proposal)
    p["changes"] = [c for c in p["changes"] if c["id"] in p["selected_change_ids"]]
    return _result(
        "export_only",
        proposal=p,
        review_required=True,
        instructions=[
            "Re-read native target and UOL origin revision before review.",
            "Verify permissions and intended audience independently.",
            "Use a verified native conditional token; otherwise apply manually.",
            "For Genie, merge selected edits into the complete current configuration.",
            "Read back actual native state and compare selected values after any external write.",
        ],
    )


def _observed(adapter, p):
    observation = adapter.read_target(deepcopy(p["target"]))
    document = observation["document"]
    if not isinstance(document, dict) or observation.get("fingerprint") != fingerprint(
        document
    ):
        raise ValueError("Invalid observation")
    if observation.get("target", p["target"]) != p["target"]:
        raise ValueError("Target identity mismatch")
    if observation.get("origin_id", p["origin"]["id"]) != p["origin"]["id"]:
        raise ValueError("Origin mapping mismatch")
    return observation


def validate_proposal(proposal, adapter=None):
    """Return a review-only plan. Two fresh reads detect drift, never authorize a write."""
    p = _proposal(proposal)
    if adapter is None:
        return _result(
            "unsupported",
            reason="No authenticated native adapter configured",
            handoff=export_handoff(p),
        )
    try:
        capabilities = adapter.capabilities()
        if capabilities.get("read") is not True:
            return _result(
                "unsupported",
                reason="Native read capability unavailable",
                handoff=export_handoff(p),
            )
        first = _observed(adapter, p)
        if (
            adapter.read_origin_revision(deepcopy(p["origin"]))
            != p["origin"]["revision"]
        ):
            return _result("conflict", reason="UOL origin revision changed")
        if first["fingerprint"] != p["base_fingerprint"]:
            return _result("conflict", reason="Native target fingerprint changed")
        if (
            first.get("permissions", {}).get("read") is not True
            or first.get("permissions", {}).get("write") is not True
        ):
            return _result(
                "blocked", reason="Native read/write permission not verified"
            )
        if not isinstance(first.get("audience"), list) or set(first["audience"]) != set(
            p["intended_audience"]
        ):
            return _result(
                "blocked", reason="Native audience differs from reviewed audience"
            )
        desired = deepcopy(first["document"])
        for change in p["changes"]:
            if change["id"] not in p["selected_change_ids"]:
                continue
            node = desired
            for key in change["path"][:-1]:
                node = node[key]
                if not isinstance(node, dict):
                    raise ValueError("Only existing object paths supported")
            node[change["path"][-1]] = deepcopy(change["value"])
        second = _observed(adapter, p)
        if (
            second != first
            or adapter.read_origin_revision(deepcopy(p["origin"]))
            != p["origin"]["revision"]
        ):
            return _result(
                "conflict",
                reason="Native target, permissions, audience, or UOL origin drifted during validation",
            )
        conditional = (
            capabilities.get("conditional_write") is True
            and isinstance(second.get("revision_token"), str)
            and bool(second["revision_token"])
        )
        return _result(
            "review_ready" if conditional else "export_only",
            target=deepcopy(p["target"]),
            origin=deepcopy(p["origin"]),
            base_fingerprint=first["fingerprint"],
            desired_fingerprint=fingerprint(desired),
            desired_document=desired,
            selected_change_ids=p["selected_change_ids"],
            conditional_write_supported=conditional,
            review_required=True,
            reason="Read-only validation; no publish operation is implemented",
            saved_acknowledgement="unknown",
            handoff=export_handoff(p),
        )
    except Exception:
        # Never echo remote exceptions: responses may contain credentials or metadata.
        return _result("blocked", reason="Native validation failed; no write attempted")


def verify_readback(proposal, adapter):
    """Observe actual state after an independently performed write; never use timers."""
    p = _proposal(proposal)
    try:
        observed = _observed(adapter, p)
        if observed.get("permissions", {}).get("read") is not True:
            return _result("blocked", reason="Native read permission not verified")
        if not isinstance(observed.get("audience"), list) or set(
            observed["audience"]
        ) != set(p["intended_audience"]):
            return _result(
                "blocked", reason="Native audience differs from reviewed audience"
            )
        if (
            adapter.read_origin_revision(deepcopy(p["origin"]))
            != p["origin"]["revision"]
        ):
            return _result("conflict", reason="UOL origin revision changed")
        for change in p["changes"]:
            if change["id"] in p["selected_change_ids"]:
                value = observed["document"]
                for key in change["path"]:
                    value = value[key]
                if value != change["value"]:
                    return _result(
                        "readback_mismatch", reason="Selected native values differ"
                    )
        return _result(
            "readback_verified",
            observed_fingerprint=observed["fingerprint"],
            selected_change_ids=p["selected_change_ids"],
            saved_acknowledgement="unknown",
        )
    except Exception:
        return _result("blocked", reason="Native readback failed")
