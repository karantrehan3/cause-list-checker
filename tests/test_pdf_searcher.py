from unittest.mock import MagicMock, patch

import fitz
import pytest
import requests

from app.config import REQUEST_HEADERS
from app.managers.pdf_searcher import PDFSearcher


def _pdf_bytes(*pages: str) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _response(status: int, content: bytes = b"") -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.content = content
    response.text = content.decode("latin-1")
    return response


PDF = {"pdf_name": "Ordinary | Main List", "pdf_url": "https://court.example/list.pdf"}


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("app.managers.pdf_searcher.time.sleep"):
        yield


def test_download_sends_shared_browser_headers():
    with patch(
        "app.managers.pdf_searcher.requests.get",
        return_value=_response(200, _pdf_bytes("x")),
    ) as get:
        PDFSearcher(["CR-1-2020"]).fetch_and_search_pdf(dict(PDF))

    assert get.call_args.kwargs["headers"] is REQUEST_HEADERS
    assert "python-requests" not in REQUEST_HEADERS["User-Agent"]


def test_finds_term_case_insensitively_and_reports_page_numbers():
    content = _pdf_bytes(
        "nothing here", "CR-2227-2010 Haryana Wakf Board vs Vishnu Mittar"
    )
    pdf = dict(PDF)
    with patch(
        "app.managers.pdf_searcher.requests.get", return_value=_response(200, content)
    ):
        result = PDFSearcher(["vishnu mittar", "CR-9999-2000"]).fetch_and_search_pdf(
            pdf
        )

    assert result["found_pages"] == {"vishnu mittar": [2], "CR-9999-2000": []}
    assert result["num_pages"] == 2
    assert pdf["num_pages"] == 2


def test_no_match_returns_none_but_records_pages_read():
    pdf = dict(PDF)
    with patch(
        "app.managers.pdf_searcher.requests.get",
        return_value=_response(200, _pdf_bytes("a", "b", "c")),
    ):
        assert PDFSearcher(["absent"]).fetch_and_search_pdf(pdf) is None

    assert pdf["num_pages"] == 3


def test_http_403_returns_none_and_logs_diagnostics(capsys):
    pdf = dict(PDF)
    with (
        patch(
            "app.managers.pdf_searcher.requests.get",
            return_value=_response(403, b"Forbidden"),
        ),
        patch(
            "app.managers.pdf_searcher.describe_failed_response",
            return_value="  status: 403",
        ),
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    out = capsys.readouterr().out
    assert "Failed to fetch PDF Ordinary | Main List: HTTP 403" in out
    assert "status: 403" in out
    assert "num_pages" not in pdf


def test_search_pdf_collects_only_matches_across_lists():
    pdfs = [
        {"pdf_name": "A | Main List", "pdf_url": "https://court.example/a.pdf"},
        {"pdf_name": "B | Main List", "pdf_url": "https://court.example/b.pdf"},
    ]
    bodies = {
        "https://court.example/a.pdf": _response(200, _pdf_bytes("CR-2227-2010")),
        "https://court.example/b.pdf": _response(200, _pdf_bytes("unrelated")),
    }
    with patch(
        "app.managers.pdf_searcher.requests.get",
        side_effect=lambda url, **kw: bodies[url],
    ):
        results = PDFSearcher(["CR-2227-2010"]).search_pdf(pdfs)

    assert [r["pdf_name"] for r in results] == ["A | Main List"]


def test_browser_headers_are_complete():
    for header in (
        "User-Agent",
        "Accept",
        "Accept-Language",
        "Upgrade-Insecure-Requests",
    ):
        assert REQUEST_HEADERS.get(header), header
    assert "Chrome/" in REQUEST_HEADERS["User-Agent"]
    assert "application/pdf" in REQUEST_HEADERS["Accept"]


def test_html_error_page_with_200_is_rejected_with_reason():
    response = _response(200, b"<html>Session expired</html>")
    response.headers = {"Content-Type": "text/html"}
    pdf = dict(PDF)
    with (
        patch("app.managers.pdf_searcher.requests.get", return_value=response),
        patch("app.managers.pdf_searcher.describe_failed_response", return_value=""),
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"] == "not a PDF (Content-Type: text/html)"
    assert "num_pages" not in pdf


def test_empty_body_is_rejected():
    pdf = dict(PDF)
    with (
        patch(
            "app.managers.pdf_searcher.requests.get", return_value=_response(200, b"")
        ),
        patch("app.managers.pdf_searcher.describe_failed_response", return_value=""),
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"] == "empty response"


def test_pdf_without_text_is_flagged_not_searched():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    blank = doc.tobytes()
    pdf = dict(PDF)
    with patch(
        "app.managers.pdf_searcher.requests.get", return_value=_response(200, blank)
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"] == "no searchable text in 2 pages (scanned?)"
    assert "num_pages" not in pdf


def test_http_error_reason_recorded_on_pdf():
    pdf = dict(PDF)
    with (
        patch(
            "app.managers.pdf_searcher.requests.get",
            return_value=_response(403, b"Forbidden"),
        ),
        patch("app.managers.pdf_searcher.describe_failed_response", return_value=""),
    ):
        PDFSearcher(["x"]).fetch_and_search_pdf(pdf)

    assert pdf["error"] == "HTTP 403"


def test_match_result_carries_source():
    pdf = {**PDF, "source": "new.phhc.gov.in"}
    with patch(
        "app.managers.pdf_searcher.requests.get",
        return_value=_response(200, _pdf_bytes("CR-1-2020")),
    ):
        result = PDFSearcher(["CR-1-2020"]).fetch_and_search_pdf(pdf)

    assert result["source"] == "new.phhc.gov.in"


def test_unreadable_page_is_skipped_and_others_still_searched():
    content = _pdf_bytes("CR-1-2020 on page one", "page two")
    real_open = fitz.open

    def flaky_open(*args, **kwargs):
        doc = real_open(*args, **kwargs)
        original = doc.load_page
        doc.load_page = lambda n: (
            (_ for _ in ()).throw(RuntimeError("bad page")) if n == 1 else original(n)
        )
        return doc

    pdf = dict(PDF)
    with (
        patch(
            "app.managers.pdf_searcher.requests.get",
            return_value=_response(200, content),
        ),
        patch("app.managers.pdf_searcher.fitz.open", side_effect=flaky_open),
    ):
        result = PDFSearcher(["CR-1-2020"]).fetch_and_search_pdf(pdf)

    assert result["found_pages"] == {"CR-1-2020": [1]}


def test_corrupt_pdf_records_parse_error():
    pdf = dict(PDF)
    with patch(
        "app.managers.pdf_searcher.requests.get",
        return_value=_response(200, b"%PDF-1.4 garbage"),
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"].startswith("could not parse PDF")


def test_network_error_records_download_failure():
    pdf = dict(PDF)
    with patch(
        "app.managers.pdf_searcher.requests.get",
        side_effect=requests.exceptions.ReadTimeout(),
    ):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"] == "download failed (ReadTimeout)"


def test_unexpected_error_is_recorded():
    pdf = dict(PDF)
    with patch("app.managers.pdf_searcher.requests.get", side_effect=KeyError("boom")):
        assert PDFSearcher(["x"]).fetch_and_search_pdf(pdf) is None

    assert pdf["error"] == "unexpected error (KeyError)"


def _entry_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    for x, y, text in [
        (28, 100, "404 ** RSA-4610-2011"),
        (57, 112, "SANGRUR"),
        (168, 100, "KRISHAN CHAND V/S TARSEM CHAND"),
        (362, 100, "ASHISH KASHYAP,"),
        (362, 112, "BALDEV RAJ MAHAJAN"),
    ]:
        page.insert_text((x, y), text, fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def test_matched_entry_is_split_into_columns_from_the_pdf_layout():
    with patch(
        "app.managers.pdf_searcher.requests.get",
        return_value=_response(200, _entry_pdf_bytes()),
    ):
        result = PDFSearcher(["RSA-4610-2011"]).fetch_and_search_pdf(dict(PDF))

    assert result["matches"][0]["columns"] == {
        "case": ["404 ** RSA-4610-2011", "SANGRUR"],
        "parties": ["KRISHAN CHAND V/S TARSEM CHAND"],
        "advocates": ["ASHISH KASHYAP,", "BALDEV RAJ MAHAJAN"],
    }


def test_unreadable_positions_fall_back_to_plain_entry_text():
    document = MagicMock()
    document.load_page.side_effect = RuntimeError("bad page")

    assert PDFSearcher._line_x(document, 1) == []
