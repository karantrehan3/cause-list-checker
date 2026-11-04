"""Live checks against the real court sites. Run with: RUN_LIVE=1 pytest -m live

These catch the court changing its site again (endpoints, response shapes, blocking).
"""

from datetime import date, timedelta

import pytest
import requests

from app.clients.court_http import CourtHttpClient
from app.clients.phhc_api import PhhcApi
from app.config import REQUEST_HEADERS
from app.managers.cause_list_manager import CauseListManager
from app.managers.judge_cause_list_manager import (
    match_judge_code,
    search_entries,
    unwrap_records,
)

pytestmark = pytest.mark.live

BENCH = "HON'BLE MR. JUSTICE VIKAS SURI"
LOOKAHEAD_DAYS = 10


@pytest.fixture(scope="module")
def api():
    return PhhcApi(CourtHttpClient())


@pytest.fixture(scope="module")
def judge_code(api):
    code = match_judge_code(BENCH, api.active_judges())
    assert code, "could not match the test bench to an active judge"
    return code


def _upcoming_dates():
    today = date.today()
    return [
        (today + timedelta(days=i)).strftime("%d/%m/%Y") for i in range(LOOKAHEAD_DAYS)
    ]


def _assert_pdf(url):
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=(10, 90))
    assert response.status_code == 200, f"HTTP {response.status_code} for {url}"
    assert response.content[:5] == b"%PDF-", f"not a PDF: {url}"


def test_both_sources_serve_real_pdfs(api):
    fetcher = CauseListManager(CourtHttpClient(), api)
    for day in _upcoming_dates():
        old, new = fetcher.fetch_old_site(day), fetcher.fetch_new_site(day)
        if old and new:
            _assert_pdf(old[0]["pdf_url"])
            _assert_pdf(new[0]["pdf_url"])
            return
    pytest.skip("no date in the next 10 days has lists on both sites")


def test_regular_cause_list_shape_on_latest_date(api, judge_code):
    latest = api.client.get_json(
        f"{api.base_url}/cis_filing/public/get-latest-regular-causelist-date"
    )
    y, m, d = str(latest["cl_date"])[:10].split("-")

    entries = unwrap_records(api.regular_cause_list(judge_code, f"{d}/{m}/{y}"))

    assert entries, "regular cause list returned no entries"
    assert all("case_no" in e for e in entries), "response shape changed"


def test_daily_judge_list_finds_a_case_that_is_listed(api, judge_code):
    """Positive check: pick a real case from the bench's daily list and search for it."""
    for day in _upcoming_dates():
        entries = unwrap_records(api.daily_cause_list(judge_code, day))
        if entries:
            sample = entries[0]
            case_id = f"{sample['case_type']}-{sample['case_no']}-{sample['case_year']}"
            assert sample in search_entries(entries, [case_id])
            return
    pytest.skip("bench has no daily list in the next 10 days")
