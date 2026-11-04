"""Coverage for supporting modules on the request path: diagnostics, email, tracker, validation."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import ValidationError

from app.managers.pdf_tracker import PDFTracker
from app.routes.search.cause_list.validators import SearchRequest
from app.services.emailer import Emailer
from app.utils import http_debug
from app.utils.error_handler import ErrorHandler
from app.utils.helpers import get_weekend_dates

# --- http_debug ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_egress_cache():
    http_debug._egress_ip_cache = None
    yield
    http_debug._egress_ip_cache = None


def test_egress_ip_is_fetched_once_and_cached():
    with patch.object(
        http_debug.requests, "get", return_value=MagicMock(text="1.2.3.4\n")
    ) as get:
        assert http_debug.get_egress_ip() == "1.2.3.4"
        assert http_debug.get_egress_ip() == "1.2.3.4"

    get.assert_called_once()


def test_egress_ip_failure_is_reported_not_raised():
    with patch.object(
        http_debug.requests, "get", side_effect=requests.exceptions.ConnectTimeout()
    ):
        assert http_debug.get_egress_ip() == "unknown (ConnectTimeout)"


def test_describe_failed_response_redacts_secrets_and_shows_server_clues():
    response = requests.models.Response()
    response.status_code = 403
    response.reason = "Forbidden"
    response.url = "https://court/x"
    response._content = b"<html>  <h1>Forbidden</h1> </html>"
    response.headers.update({"Server": "Apache", "X-Unrelated": "no"})
    response.elapsed = __import__("datetime").timedelta(seconds=0.15)
    response.request = requests.Request(
        "GET",
        "https://court/x",
        headers={"Cookie": "secret", "Authorization": "token", "User-Agent": "UA"},
    ).prepare()

    with patch.object(http_debug, "get_egress_ip", return_value="9.9.9.9"):
        text = http_debug.describe_failed_response(response)

    assert "status: 403 Forbidden" in text
    assert "egress_ip: 9.9.9.9" in text
    assert "'Server': 'Apache'" in text and "X-Unrelated" not in text
    assert "secret" not in text and "token" not in text and "<redacted>" in text
    assert "<html> <h1>Forbidden</h1> </html>" in text


# --- Emailer & ErrorHandler -----------------------------------------------------


def test_emailer_renders_template_and_sends_over_smtp():
    with patch("app.services.emailer.smtplib.SMTP") as smtp:
        Emailer().send_email(
            ["a@b.c"], "Subject", "error_template.html", {"error_message": "boom"}
        )

    server = smtp.return_value.__enter__.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once()
    sent = server.sendmail.call_args.args
    assert sent[1] == ["a@b.c"]
    assert "Subject: Subject" in sent[2]


def test_emailer_propagates_smtp_failures():
    with patch("app.services.emailer.smtplib.SMTP", side_effect=OSError("smtp down")):
        with pytest.raises(OSError):
            Emailer().send_email(["a@b.c"], "S", "error_template.html", {})


def test_error_handler_emails_and_returns_message():
    emailer = MagicMock()
    try:
        raise ValueError("bad thing")
    except ValueError as e:
        message, trace = ErrorHandler(emailer, ["a@b.c"]).handle_exception(
            e, {"date": "05/11/2026"}
        )

    assert message == "bad thing"
    assert "ValueError" in trace
    assert (
        emailer.send_email.call_args.kwargs["context"]["error_message"] == "bad thing"
    )


def test_error_handler_survives_email_failure():
    emailer = MagicMock()
    emailer.send_email.side_effect = OSError("smtp down")

    message, _ = ErrorHandler(emailer, ["a@b.c"]).handle_exception(
        RuntimeError("x"), {}
    )

    assert message == "x"


# --- PDF tracker (in-memory mode) -----------------------------------------------


def test_tracker_marks_repeat_pdfs_as_existing_per_search():
    tracker = PDFTracker()
    tracker._use_ssm = False
    pdf = {"pdf_name": "Ordinary | Main List", "pdf_url": "https://old/o"}

    assert tracker.separate_existing_and_new_pdfs([pdf], ["x"]) == ([], [pdf])
    assert tracker.separate_existing_and_new_pdfs([pdf], ["x"]) == ([pdf], [])
    assert tracker.separate_existing_and_new_pdfs([pdf], ["other"]) == ([], [pdf])

    tracker.clear_existing_pdfs()
    assert tracker.separate_existing_and_new_pdfs([pdf], ["x"]) == ([], [pdf])


def test_tracker_ssm_mode_round_trips_state():
    tracker = PDFTracker()
    tracker._use_ssm = True
    ssm = MagicMock()
    ssm.get_parameter.side_effect = Exception("ParameterNotFound")
    tracker._ssm_client = ssm
    pdf = {"pdf_name": "A", "pdf_url": "u"}

    _, new = tracker.separate_existing_and_new_pdfs([pdf], ["x"])

    assert new == [pdf]
    ssm.put_parameter.assert_called_once()


# --- Request validation & weekend dates ---------------------------------------


def test_search_request_strips_terms_and_accepts_valid_payload():
    request = SearchRequest(
        search_terms=[" CR-1-2020 ", " "],
        date="05/11/2026",
        case_details={"type": "CR", "no": "1", "year": "2020"},
    )

    assert request.search_terms == ["CR-1-2020"]


@pytest.mark.parametrize(
    "payload",
    [
        {"search_terms": []},
        {"search_terms": ["x"], "date": "2026-11-05"},
        {"search_terms": ["x"], "case_details": {"type": "CR"}},
        {"search_terms": ["x"], "recipient_emails": ["not-an-email"]},
    ],
)
def test_search_request_rejects_bad_payloads(payload):
    with pytest.raises(ValidationError):
        SearchRequest(**payload)


@pytest.mark.parametrize(
    "target, expected_count",
    [
        ("05/11/2026", 1),
        ("06/11/2026", 4),
        ("07/11/2026", 3),
        ("08/11/2026", 2),
    ],  # Thu, Fri, Sat, Sun
)
def test_weekend_dates(target, expected_count):
    dates = get_weekend_dates(target)

    assert dates[0] == target
    assert len(dates) == expected_count
