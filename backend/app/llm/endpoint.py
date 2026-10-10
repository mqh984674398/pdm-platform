"""Where inference may run: local Ollama on this machine or the plant LAN only (LLM-04, SEC-04, STK-04).

An endpoint is accepted when its host is a loopback or private (RFC 1918 / unique-local) IP address,
``localhost``, or a host name an administrator put on the allowlist. Public addresses, other host
names, credentials in the URL and non-HTTP schemes are refused. Host names are not resolved here, so
a public name cannot slip through DNS; names must be listed explicitly.

Models are refused when they are cloud-routed (Ollama ``*-cloud`` / ``:cloud`` tags run remotely),
when they name a remote registry host, or when an allowlist exists and does not include them.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Collection
from urllib.parse import urlsplit


class EndpointRejected(ValueError):
    pass


class ModelRejected(ValueError):
    pass


CLOUD_TAG = re.compile(r"(^|[:\-_.])cloud($|[:\-_.])", re.IGNORECASE)


def validate_endpoint(url: str, allowed_hosts: Collection[str] = ()) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise EndpointRejected(f"scheme '{parts.scheme}' is not allowed; use http or https")
    if parts.username or parts.password:
        raise EndpointRejected("credentials in the endpoint URL are not allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise EndpointRejected("the endpoint has no host")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise EndpointRejected("give the Ollama base URL only (no path or query)")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or (ip.is_private and not ip.is_link_local and not ip.is_multicast):
            return f"{parts.scheme}://{parts.netloc}"
        raise EndpointRejected(
            f"{host} is not a loopback or private LAN address; remote inference is refused"
        )
    if host == "localhost" or host in {h.lower() for h in allowed_hosts}:
        return f"{parts.scheme}://{parts.netloc}"
    raise EndpointRejected(f"host '{host}' is not on the LAN allowlist; remote inference is refused")


def validate_model(name: str, allowed: Collection[str] = (), installed: Collection[str] | None = None) -> str:
    n = name.strip()
    if not n:
        raise ModelRejected("no model selected")
    if CLOUD_TAG.search(n):
        raise ModelRejected(
            f"'{n}' is a cloud-routed model; only models running on the local Ollama are allowed"
        )
    if "/" in n and "." in n.split("/", 1)[0]:
        raise ModelRejected(
            f"'{n}' names a remote registry host; install the model locally and select its local name"
        )
    if allowed and n not in allowed:
        raise ModelRejected(f"'{n}' is not on the model allowlist")
    if installed is not None and n not in installed:
        raise ModelRejected(f"'{n}' is not installed on the local Ollama")
    return n
