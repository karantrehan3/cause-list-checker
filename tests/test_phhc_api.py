from unittest.mock import MagicMock

import pytest

from app.managers.court_http import SLOW_TIMEOUT, CourtSiteError
from app.managers.phhc_api import PhhcApi, to_api_date

BASE = "https://api.court"


@pytest.fixture
def client():
    return MagicMock()


@pytest.fixture
def api(client):
    return PhhcApi(client, base_url=BASE)


def _called(client):
    call = client.get_json.call_args
    return call.args[0], call.kwargs.get("params"), call.kwargs


def test_to_api_date():
    assert to_api_date("05/11/2026") == "2026-11-05"


def test_case_info_hits_get_case(api, client):
    client.get_json.return_value = {"case_no": "2227"}

    assert api.case_info("CR", "2227", "2010") == {"case_no": "2227"}
    url, params, _ = _called(client)
    assert url == f"{BASE}/cis_filing/public/getCase"
    assert params == {"case_type": "CR", "case_no": "2227", "case_year": "2010"}


@pytest.mark.parametrize("payload", [None, {}, []])
def test_case_info_raises_when_case_missing(api, client, payload):
    client.get_json.return_value = payload

    with pytest.raises(CourtSiteError, match="case not found"):
        api.case_info("CR", "1", "2000")


@pytest.mark.parametrize(
    "payload, expected",
    [({"data": [{"a": 1}]}, [{"a": 1}]), ([{"b": 2}], [{"b": 2}]), (None, [])],
)
def test_listing_history_unwraps_data(api, client, payload, expected):
    client.get_json.return_value = payload

    assert api.listing_history("CR", "2227", "2010") == expected
    assert _called(client)[0] == f"{BASE}/case_listing_detail/public/search"


@pytest.mark.parametrize(
    "method, path, default",
    [
        ("related_cases", "/cis_filing/public/relatedCases", []),
        ("judgments", "/cis_filing/public/judgmentDetails/2227/2010/CR", []),
        ("copy_petitions", "/HC-Copying-Applications-Case-Details-Public/", {}),
        ("impugned_orders", "/cis_filing/public/getImpugnedOrderDetails", {}),
    ],
)
def test_case_detail_endpoints_and_empty_defaults(api, client, method, path, default):
    client.get_json.return_value = None

    assert getattr(api, method)("CR", "2227", "2010") == default
    assert _called(client)[0] == f"{BASE}{path}"


def test_active_judges(api, client):
    client.get_json.return_value = [{"judge_code": 1}]

    assert api.active_judges() == [{"judge_code": 1}]
    assert _called(client)[0] == f"{BASE}/cis/judges/active-bench"


@pytest.mark.parametrize(
    "method, path",
    [
        ("daily_cause_list", "/cis_filing/public/getCauseList"),
        ("regular_cause_list", "/cis_filing/public/getRegularCauseList"),
    ],
)
def test_judge_wise_lists_use_bench_date_and_slow_timeout(api, client, method, path):
    client.get_json.return_value = []

    getattr(api, method)(650, "05/11/2026")
    url, params, kwargs = _called(client)
    assert url == f"{BASE}{path}"
    assert params == {"bench_judge_id": "650", "cause_list_date": "2026-11-05"}
    assert kwargs["timeout"] == SLOW_TIMEOUT


def test_daily_pdf_list(api, client):
    client.get_json.return_value = [{"list_type": "O", "main_suppl": "M"}]

    assert api.daily_pdf_list("05/11/2026") == [{"list_type": "O", "main_suppl": "M"}]
    url, params, _ = _called(client)
    assert url == f"{BASE}/public/daily-causelist-pdf/list"
    assert params == {"cl_date": "2026-11-05"}


def test_daily_pdf_list_rejects_unexpected_shape(api, client):
    client.get_json.return_value = {"error": "x"}

    with pytest.raises(CourtSiteError, match="unexpected"):
        api.daily_pdf_list("05/11/2026")


def test_daily_pdf_list_types_and_url(api, client):
    client.get_json.return_value = None

    assert api.daily_pdf_list_types() == []
    assert (
        api.daily_pdf_url("05/11/2026", "O", "M")
        == f"{BASE}/public/daily-causelist-pdf/2026-11-05/O/M"
    )
