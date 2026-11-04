from unittest.mock import MagicMock, patch

import pytest
import requests

from app.clients.court_http import (
    CONNECTION_ATTEMPTS,
    DEFAULT_TIMEOUT,
    CourtHttpClient,
    CourtSiteError,
)
from app.config import REQUEST_HEADERS


def _session_returning(*outcomes):
    """A fake session whose request() returns/raises each outcome in turn."""
    session = MagicMock()
    session.__enter__.return_value = session
    session.request.side_effect = list(outcomes)
    return session


def _ok(json_data=None, content_type="application/json"):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.headers = {"Content-Type": content_type}
    if json_data is None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_data
    return response


def _http_error(status, reason):
    response = MagicMock()
    response.status_code = status
    response.reason = reason
    error = requests.exceptions.HTTPError(response=response)
    response.raise_for_status.side_effect = error
    return response


@pytest.fixture
def client():
    return CourtHttpClient()


def test_request_sends_browser_headers_and_default_timeout(client):
    session = _session_returning(_ok({"a": 1}))
    with patch.object(CourtHttpClient, "_create_session", return_value=session):
        client.request("get", "https://court/x")

    method, url = session.request.call_args.args
    assert (method, url) == ("GET", "https://court/x")
    assert session.request.call_args.kwargs["headers"] is REQUEST_HEADERS
    assert session.request.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_http_error_becomes_readable_reason_with_diagnostics(client, capsys):
    session = _session_returning(_http_error(403, "Forbidden"))
    with (
        patch.object(CourtHttpClient, "_create_session", return_value=session),
        patch(
            "app.clients.court_http.describe_failed_response",
            return_value="  status: 403",
        ),
    ):
        with pytest.raises(CourtSiteError) as error:
            client.request("GET", "https://court/x")

    assert error.value.reason == "HTTP 403 Forbidden"
    assert "status: 403" in capsys.readouterr().out


def test_connection_errors_are_retried_then_reported(client):
    failures = [requests.exceptions.ConnectionError("reset")] * CONNECTION_ATTEMPTS
    session = _session_returning(*failures)
    with (
        patch.object(CourtHttpClient, "_create_session", return_value=session),
        patch("app.clients.court_http.time.sleep") as sleep,
    ):
        with pytest.raises(CourtSiteError, match="connection failed"):
            client.request("GET", "https://court/x")

    assert session.request.call_count == CONNECTION_ATTEMPTS
    assert sleep.call_count == CONNECTION_ATTEMPTS - 1


def test_connection_error_then_success_returns_response(client):
    good = _ok({"ok": True})
    session = _session_returning(requests.exceptions.ConnectionError("reset"), good)
    with (
        patch.object(CourtHttpClient, "_create_session", return_value=session),
        patch("app.clients.court_http.time.sleep"),
    ):
        assert client.request("GET", "https://court/x") is good


@pytest.mark.parametrize(
    "exception, reason",
    [
        (requests.exceptions.ReadTimeout("slow"), "timed out"),
        (
            requests.exceptions.TooManyRedirects("loop"),
            "request failed (TooManyRedirects)",
        ),
    ],
)
def test_other_request_failures_have_reasons(client, exception, reason):
    session = _session_returning(exception)
    with patch.object(CourtHttpClient, "_create_session", return_value=session):
        with pytest.raises(CourtSiteError) as error:
            client.request("GET", "https://court/x")

    assert error.value.reason == reason


def test_get_json_returns_parsed_body(client):
    session = _session_returning(_ok([{"x": 1}]))
    with patch.object(CourtHttpClient, "_create_session", return_value=session):
        assert client.get_json("https://court/api", params={"a": "b"}) == [{"x": 1}]

    assert session.request.call_args.kwargs["params"] == {"a": "b"}


def test_get_json_rejects_non_json_body(client):
    session = _session_returning(_ok(None, content_type="text/html"))
    with patch.object(CourtHttpClient, "_create_session", return_value=session):
        with pytest.raises(
            CourtSiteError, match="invalid response \\(Content-Type: text/html\\)"
        ):
            client.get_json("https://court/api")


def test_create_session_verifies_tls_and_mounts_retries():
    session = CourtHttpClient._create_session()

    assert session.verify
    assert session.get_adapter("https://court").max_retries.total == 3
