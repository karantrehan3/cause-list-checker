from unittest.mock import MagicMock, patch

import pytest

from app.clients.court_http import CourtSiteError
from app.clients.phhc_api import PhhcApi
from app.managers.cause_list_manager import (
    NEW_SOURCE,
    OLD_SOURCE,
    CauseListManager,
    CauseListResult,
    cause_list_sources,
)

OLD_SITE_HTML = """
<table id="tables11">
  <tr><td>header</td></tr>
  <tr><td>sub-header</td></tr>
  <tr>
    <td><a href="javascript:;" onclick="window.open('./show_cause_list.php?filename=AAA')">View</a></td>
    <td>Ordinary</td><td>Main List</td>
  </tr>
  <tr>
    <td><a href="javascript:;" onclick="window.open('./show_cause_list.php?filename=BBB')">View</a></td>
    <td>Urgent</td><td>Supplementary List</td>
  </tr>
  <tr><td>no link</td><td>Takenup</td><td>Main List</td></tr>
  <tr><td><a href="x">no onclick</a></td><td>Special</td><td>Main List</td></tr>
  <tr><td>short row</td></tr>
</table>
"""

LIST_TYPES = [
    {"code": "O", "description": "ORDINARY"},
    {"code": "G", "description": "COMMERCIAL (ORDINARY)"},
]


@pytest.fixture
def client():
    client = MagicMock()
    client.request.return_value = MagicMock(text=OLD_SITE_HTML)
    return client


@pytest.fixture
def api():
    api = MagicMock(spec=PhhcApi)
    api.daily_pdf_list.return_value = [{"list_type": "O", "main_suppl": "M"}]
    api.daily_pdf_list_types.return_value = LIST_TYPES
    api.daily_pdf_url.side_effect = lambda d, c, s: f"https://api/pdf/{c}/{s}"
    return api


@pytest.fixture
def fetcher(client, api):
    return CauseListManager(client, api)


@pytest.fixture
def tracker():
    with patch("app.managers.cause_list_manager.pdf_tracker") as tracker:
        tracker.separate_existing_and_new_pdfs.side_effect = lambda pdfs, terms: (
            [],
            pdfs,
        )
        yield tracker


def test_sources_listed_old_then_new():
    assert [s["name"] for s in cause_list_sources()] == [OLD_SOURCE, NEW_SOURCE]


def test_old_site_posts_form_and_parses_rows_with_links(fetcher, client):
    pdfs = fetcher.fetch_old_site("05/11/2026")

    method, _ = client.request.call_args.args
    assert method == "POST"
    assert client.request.call_args.kwargs["data"]["t_f_date"] == "05/11/2026"
    assert [p["pdf_name"] for p in pdfs] == [
        "Ordinary | Main List",
        "Urgent | Supplementary List",
    ]
    assert (
        pdfs[0]["pdf_url"]
        == "https://highcourtchd.gov.in/show_cause_list.php?filename=AAA"
    )
    assert {p["source"] for p in pdfs} == {OLD_SOURCE}


def test_new_site_names_lists_from_list_types(fetcher, api):
    api.daily_pdf_list.return_value = [
        {"list_type": "O", "main_suppl": "M"},
        {"list_type": "g", "main_suppl": "s"},
        {"list_type": "", "main_suppl": "M"},  # skipped: no code
        {"list_type": "O", "main_suppl": "X"},  # skipped: unknown main/suppl
    ]

    pdfs = fetcher.fetch_new_site("05/11/2026")

    assert [p["pdf_name"] for p in pdfs] == [
        "Ordinary | Main List",
        "Commercial (Ordinary) | Supplementary List",
    ]
    assert pdfs[1]["pdf_url"] == "https://api/pdf/G/S"
    assert {p["source"] for p in pdfs} == {NEW_SOURCE}


def test_new_site_falls_back_to_codes_when_list_types_fail(fetcher, api):
    api.daily_pdf_list_types.side_effect = CourtSiteError("HTTP 500")

    assert [p["pdf_name"] for p in fetcher.fetch_new_site("05/11/2026")] == [
        "O | Main List"
    ]


def test_fetch_keeps_both_sources_in_full_old_first(fetcher, tracker):
    result = fetcher.fetch("05/11/2026", ["x"])

    assert [p["source"] for p in result.pdfs] == [OLD_SOURCE, OLD_SOURCE, NEW_SOURCE]
    assert result.source_errors == {}
    tracker.separate_existing_and_new_pdfs.assert_called_once()


def test_fetch_records_failed_source_and_keeps_the_other(fetcher, client, tracker):
    client.request.side_effect = CourtSiteError("HTTP 500 Internal Server Error")

    result = fetcher.fetch("05/11/2026", ["x"])

    assert result.source_errors == {OLD_SOURCE: "HTTP 500 Internal Server Error"}
    assert [p["source"] for p in result.pdfs] == [NEW_SOURCE]


def test_fetch_raises_when_every_source_fails(fetcher, client, api, tracker):
    client.request.side_effect = CourtSiteError("HTTP 500")
    api.daily_pdf_list.side_effect = CourtSiteError("timed out")

    with pytest.raises(
        CourtSiteError, match="all cause list sources failed.*HTTP 500.*timed out"
    ):
        fetcher.fetch("05/11/2026", ["x"])


def test_result_pdfs_combines_existing_and_new():
    result = CauseListResult(
        existing_pdfs=[{"pdf_name": "a"}], new_pdfs=[{"pdf_name": "b"}]
    )

    assert [p["pdf_name"] for p in result.pdfs] == ["a", "b"]
