"""Diagnostics for failed HTTP responses, to tell IP blocks, WAF pages and app errors apart."""

import re
from typing import Optional

import requests

BODY_SNIPPET_CHARS = 500
EGRESS_IP_URL = "https://checkip.amazonaws.com"

# Headers that reveal what sits in front of the origin (CDN / WAF / proxy) and why it refused.
DIAGNOSTIC_RESPONSE_HEADERS = (
    "Server",
    "Via",
    "X-Cache",
    "X-Powered-By",
    "Content-Type",
    "Content-Length",
    "Location",
    "Retry-After",
    "CF-RAY",
    "X-Amz-Cf-Id",
    "X-Akamai-Request-ID",
    "X-Iinfo",
    "X-CDN",
)

REDACTED_REQUEST_HEADERS = {"authorization", "cookie"}

_egress_ip_cache: Optional[str] = None


def get_egress_ip() -> str:
    """Return the public IP this process makes requests from (cached per process)."""
    global _egress_ip_cache
    if _egress_ip_cache is None:
        try:
            _egress_ip_cache = requests.get(EGRESS_IP_URL, timeout=5).text.strip()
        except requests.exceptions.RequestException as e:
            _egress_ip_cache = f"unknown ({e.__class__.__name__})"
    return _egress_ip_cache


def describe_failed_response(response: requests.Response) -> str:
    """Build a multi-line, log-friendly description of a non-2xx response."""
    request = response.request
    sent_headers = {
        k: ("<redacted>" if k.lower() in REDACTED_REQUEST_HEADERS else v)
        for k, v in (request.headers or {}).items()
    }
    response_headers = {
        h: response.headers[h]
        for h in DIAGNOSTIC_RESPONSE_HEADERS
        if h in response.headers
    }
    set_cookie_names = [c.name for c in response.cookies]
    body = re.sub(r"\s+", " ", response.text or "")[:BODY_SNIPPET_CHARS]

    return "\n".join(
        [
            f"  status: {response.status_code} {response.reason}",
            f"  method/url: {request.method} {response.url}",
            f"  egress_ip: {get_egress_ip()}",
            f"  elapsed: {response.elapsed.total_seconds():.2f}s",
            f"  redirects: {[r.status_code for r in response.history]}",
            f"  request_headers: {sent_headers}",
            f"  response_headers: {response_headers}",
            f"  set_cookie_names: {set_cookie_names}",
            f"  body[:{BODY_SNIPPET_CHARS}]: {body}",
        ]
    )
