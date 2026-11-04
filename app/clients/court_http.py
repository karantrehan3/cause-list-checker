"""HTTP access to the court websites, with retries and readable failure reasons."""

import time
from typing import Any, Dict, Optional

import certifi
import requests
from requests.adapters import HTTPAdapter
from requests.cookies import RequestsCookieJar
from urllib3.exceptions import IncompleteRead
from urllib3.util.retry import Retry

from app.config import REQUEST_HEADERS
from app.utils.http_debug import describe_failed_response

DEFAULT_TIMEOUT = (10, 30)  # (connect, read) seconds
SLOW_TIMEOUT = (15, 90)  # judge-wise cause lists can take a while
CONNECTION_ATTEMPTS = 3
RETRY_STATUSES = (500, 502, 503, 504)


class CourtSiteError(Exception):
    """A court site request failed. `reason` is short and safe to show in emails."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class CourtHttpClient:
    def __init__(self, headers: Optional[Dict[str, str]] = None):
        self.headers = headers or REQUEST_HEADERS

    @staticmethod
    def _create_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=list(RETRY_STATUSES),
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount("https://", adapter)
        session.verify = certifi.where()
        return session

    def request(
        self,
        method: str,
        url: str,
        cookie_jar: Optional[RequestsCookieJar] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send a request; return the 2xx response or raise CourtSiteError.

        Pass `cookie_jar` to keep cookies across requests like a browser does
        (cookies the server sets are stored back into the jar).
        """
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        kwargs.setdefault("headers", self.headers)

        for attempt in range(1, CONNECTION_ATTEMPTS + 1):
            try:
                with self._create_session() as session:
                    if cookie_jar is not None:
                        session.cookies = cookie_jar
                    response = session.request(method.upper(), url, **kwargs)
                    response.raise_for_status()
                    return response
            except (IncompleteRead, requests.exceptions.ConnectionError) as e:
                if attempt < CONNECTION_ATTEMPTS:
                    wait = attempt * 2
                    print(
                        f"Connection error {attempt}/{CONNECTION_ATTEMPTS} for {method} {url}: {e}. "
                        f"Retrying in {wait}s...",
                        flush=True,
                    )
                    time.sleep(wait)
                    continue
                print(f"Connection failed for {method} {url}: {e}", flush=True)
                raise CourtSiteError("connection failed") from e
            except requests.exceptions.HTTPError as e:
                response = e.response
                print(
                    f"HTTP error on {method} {url}:\n{describe_failed_response(response)}",
                    flush=True,
                )
                raise CourtSiteError(
                    f"HTTP {response.status_code} {response.reason or ''}".strip()
                ) from e
            except requests.exceptions.Timeout as e:
                print(f"Timed out: {method} {url}: {e}", flush=True)
                raise CourtSiteError("timed out") from e
            except requests.exceptions.RequestException as e:
                print(f"Request error on {method} {url}: {e}", flush=True)
                raise CourtSiteError(f"request failed ({e.__class__.__name__})") from e

        raise CourtSiteError(
            "connection failed"
        )  # unreachable; keeps type checkers happy

    def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET a JSON endpoint; raise CourtSiteError on failure or non-JSON body."""
        response = self.request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as e:
            content_type = response.headers.get("Content-Type", "unknown")
            print(f"Invalid JSON from {url} (Content-Type: {content_type})", flush=True)
            raise CourtSiteError(
                f"invalid response (Content-Type: {content_type})"
            ) from e
