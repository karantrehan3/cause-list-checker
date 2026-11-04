"""An offline stand-in for the court websites and the SMTP server.

Every HTTP request made through `requests` is routed here; anything not
explicitly routed fails the test, and raw sockets are blocked as a backstop,
so end-to-end tests can never reach the real court sites or send real email.
"""

import email
import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import fitz
import requests
from requests.structures import CaseInsensitiveDict

from app.config import settings
from tests.fakes import CASE_DATA, ENTRY, JUDGES, OTHER, wrapped

OLD_PDF_A = "show_cause_list.php?filename=AAA"
OLD_PDF_B = "show_cause_list.php?filename=BBB"

OLD_SITE_HTML = f"""
<table id="tables11">
  <tr><td>Cause lists</td></tr><tr><td>S No / List / Main-Sup</td></tr>
  <tr><td><a href="javascript:;" onclick="window.open('./{OLD_PDF_A}')">1</a></td><td>Ordinary</td><td>Main List</td></tr>
  <tr><td><a href="javascript:;" onclick="window.open('./{OLD_PDF_B}')">2</a></td><td>Urgent</td><td>Supplementary List</td></tr>
</table>
"""


def make_pdf(*pages: str) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


PDF_WITH_CASE = make_pdf(
    "ORDINARY CAUSE LIST", "12. CR-2227-2010 HARYANA WAKF BOARD VS VISHNU MITTAR"
)
PDF_WITHOUT_CASE = make_pdf(
    "URGENT SUPPLEMENTARY LIST", "1. CR-1-2026 STATE OF PUNJAB VS SOMEONE"
)

Body = Union[bytes, str, dict, list, None]
Route = Tuple[int, Body, Dict[str, str]]


def _json(data: Any) -> Route:
    return 200, data, {"Content-Type": "application/json"}


def _pdf(data: bytes) -> Route:
    return 200, data, {"Content-Type": "application/pdf"}


def default_routes() -> Dict[str, Route]:
    """URL substring -> (status, body, headers). First match wins (dict order)."""
    return {
        settings.CL_FORM_ACTION_URL: (
            200,
            OLD_SITE_HTML,
            {"Content-Type": "text/html"},
        ),
        OLD_PDF_A: _pdf(PDF_WITH_CASE),
        OLD_PDF_B: _pdf(PDF_WITHOUT_CASE),
        "/public/daily-causelist-pdf/list-types": _json(
            [{"code": "O", "description": "ORDINARY"}]
        ),
        "/public/daily-causelist-pdf/list": _json(
            [{"list_type": "O", "main_suppl": "M"}]
        ),
        "/public/daily-causelist-pdf/": _pdf(PDF_WITH_CASE),
        "/cis_filing/public/getCase": _json(dict(CASE_DATA)),
        "/case_listing_detail/public/search": _json({"data": []}),
        "/cis_filing/public/relatedCases": _json([]),
        "/cis_filing/public/judgmentDetails/": _json([]),
        "/HC-Copying-Applications-Case-Details-Public/": _json({}),
        "/cis_filing/public/getImpugnedOrderDetails": _json({}),
        "/cis/judges/active-bench": _json(JUDGES),
        "/cis_filing/public/getCauseList": _json(wrapped(OTHER, ENTRY)),
        "/cis_filing/public/getRegularCauseList": _json([]),
        "/cis_filing/public/get-latest-regular-causelist-date": _json(
            {"cl_date": "2026-07-01T00:00:00"}
        ),
        "checkip.amazonaws.com": (200, "127.0.0.1", {"Content-Type": "text/plain"}),
    }


def forbidden() -> Route:
    """What the court's Apache returns when it blocks a request."""
    return (
        403,
        "<html><h1>Forbidden</h1></html>",
        {"Server": "Apache", "Content-Type": "text/html"},
    )


@dataclass
class SentEmail:
    sender: str
    recipients: List[str]
    subject: str
    html: str


@dataclass
class FakeWorld:
    routes: Dict[str, Route] = field(default_factory=default_routes)
    requests_seen: List[Tuple[str, str]] = field(default_factory=list)
    sent_emails: List[SentEmail] = field(default_factory=list)

    def route(
        self,
        url_part: str,
        status: int,
        body: Body = None,
        headers: Optional[Dict] = None,
    ) -> None:
        """Override (or add) a route; inserted first so it wins over defaults."""
        self.routes = {
            url_part: (status, body, headers or {}),
            **{k: v for k, v in self.routes.items() if k != url_part},
        }

    def block(self, url_part: str) -> None:
        status, body, headers = forbidden()
        self.route(url_part, status, body, headers)

    # --- requests.Session.request replacement ------------------------------

    def handle(
        self, session: requests.Session, method: str, url: str, **kwargs: Any
    ) -> requests.Response:
        full_url = (
            requests.Request(method, url, params=kwargs.get("params")).prepare().url
        )
        self.requests_seen.append((method.upper(), full_url))
        for part, (status, body, headers) in self.routes.items():
            if part in full_url:
                return self._response(
                    method, full_url, status, body, headers, kwargs.get("headers")
                )
        raise AssertionError(
            f"Unexpected outbound request in test: {method} {full_url}"
        )

    @staticmethod
    def _response(
        method, url, status, body, headers, request_headers
    ) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response.reason = {
            200: "OK",
            403: "Forbidden",
            429: "Too Many Requests",
            500: "Internal Server Error",
        }.get(status, "")
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        response._content = body.encode() if isinstance(body, str) else (body or b"")
        response.headers = CaseInsensitiveDict(headers)
        response.url = url
        response.elapsed = timedelta(0)
        response.request = requests.Request(
            method, url, headers=request_headers or {}
        ).prepare()
        return response

    # --- smtplib.SMTP replacement -----------------------------------------

    def smtp_factory(self) -> Callable:
        world = self

        class FakeSMTP:
            def __init__(self, *args: Any, **kwargs: Any):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc: Any) -> None:
                return None

            def starttls(self) -> None:
                pass

            def login(self, user: str, password: str) -> None:
                pass

            def sendmail(self, sender: str, recipients: List[str], raw: str) -> None:
                message = email.message_from_string(raw)
                html_part = next(
                    p for p in message.walk() if p.get_content_type() == "text/html"
                )
                subject = str(
                    email.header.make_header(
                        email.header.decode_header(message["Subject"])
                    )
                )
                world.sent_emails.append(
                    SentEmail(
                        sender,
                        list(recipients),
                        subject,
                        html_part.get_payload(decode=True).decode(),
                    )
                )

        return FakeSMTP

    # --- helpers for assertions ------------------------------------------

    def only_email(self) -> SentEmail:
        assert len(self.sent_emails) == 1, [e.subject for e in self.sent_emails]
        return self.sent_emails[0]

    def requested(self, pattern: str) -> List[str]:
        return [url for _, url in self.requests_seen if re.search(pattern, url)]


def block_sockets(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("Real network access attempted during an end-to-end test")
