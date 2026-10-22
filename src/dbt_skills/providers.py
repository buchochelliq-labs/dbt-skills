"""Replaceable model-provider seam and an OpenAI-compatible HTTP adapter."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ModelProviderError(RuntimeError):
    """Raised when a model provider fails or returns an incompatible response."""


@dataclass(frozen=True, slots=True)
class ModelReply:
    text: str
    provider: str
    model: str


class ModelProvider(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> ModelReply: ...


def _is_loopback(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _completion_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Model base URL must be an HTTP(S) URL with a hostname")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Model base URL cannot contain credentials, query, or fragment")
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
        raise ValueError("Unencrypted HTTP is allowed only for localhost model endpoints")
    return f"{base_url.rstrip('/')}/chat/completions"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _open_request(request: Request, *, timeout: float):
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


class OpenAICompatibleProvider:
    """Adapter for OpenAI Chat Completions-compatible local or hosted endpoints.

    Credentials are read from the named environment variable for each call and
    are never persisted. Only text completion is supported; this adapter does
    not expose tools or execute model-generated actions.
    """

    provider_name = "openai-compatible"
    max_response_bytes = 8 * 1024 * 1024

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        timeout_seconds: float = 60,
    ):
        if not model.strip():
            raise ValueError("A model name is required")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a finite positive number")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env):
            raise ValueError("api_key_env must be an environment variable name")
        self.url = _completion_url(base_url.strip())
        self.model = model.strip()
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def complete(self, *, system_prompt: str, user_prompt: str) -> ModelReply:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        api_key = os.environ.get(self.api_key_env)
        if api_key and not _is_loopback(urlsplit(self.url).hostname):
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with _open_request(request, timeout=self.timeout_seconds) as response:
                response_body = response.read(self.max_response_bytes + 1)
            if len(response_body) > self.max_response_bytes:
                raise ModelProviderError("Model provider response exceeds the 8 MiB limit")
            document = json.loads(response_body)
        except HTTPError as error:
            error.close()
            raise ModelProviderError(
                f"Model provider returned HTTP {error.code}"
            ) from None
        except (URLError, TimeoutError, OSError, HTTPException) as error:
            raise ModelProviderError(
                f"Cannot reach model provider ({type(error).__name__})"
            ) from None
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ModelProviderError("Model provider returned invalid JSON") from error
        if not isinstance(document, Mapping):
            raise ModelProviderError("Model provider response must be a JSON object")
        choices = document.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ModelProviderError("Model provider response has no completion choice")
        message = choices[0].get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise ModelProviderError("Model provider response has no text completion")
        return ModelReply(
            text=message["content"],
            provider=self.provider_name,
            model=self.model,
        )
