from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.clients.court_http import CourtSiteError
from app.managers.cause_list_manager import NEW_SOURCE, OLD_SOURCE
from app.managers.health_check_manager import (
    FAILED,
    IST,
    LOOKAHEAD_DAYS,
    MAX_REGULAR_LIST_JUDGES,
    OK,
    WARNING,
    CheckResult,
    HealthCheckManager,
    HealthReport,
)
from tests.e2e.fake_world import PDF_WITH_CASE, make_pdf
from tests.fakes import CASE, ENTRY, JUDGES, FakeApi, wrapped

TODAY = datetime(2026, 11, 4, 9, 0, tzinfo=IST)
PDF = {"pdf_name": "Ordinary | Main List", "pdf_url": "https://court/o.pdf"}


def make_manager(api=None, old=None, new=None, pdf_bytes=PDF_WITH_CASE, client=None):
    api = api or FakeApi(
        daily_cause_list=wrapped(ENTRY),
        regular_cause_list=wrapped(ENTRY),
        latest_regular_list_date="01/07/2026",
    )
    if client is None:
        client = MagicMock()
        client.request.return_value = MagicMock(content=pdf_bytes)
    cause_lists = MagicMock()
    cause_lists.fetch_old_site.side_effect = old or (lambda date: [dict(PDF)])
    cause_lists.fetch_new_site.side_effect = new or (lambda date: [dict(PDF)])
    return HealthCheckManager(
        client=client, api=api, cause_lists=cause_lists, today=TODAY
    )


def by_name(report: HealthReport):
    return {c.name: c for c in report.checks}


@pytest.fixture(autouse=True)
def fixed_egress_ip():
    with patch(
        "app.managers.health_check_manager.get_egress_ip", return_value="1.2.3.4"
    ):
        yield


def test_all_checks_pass():
    report = make_manager().run(CASE)

    assert report.healthy
    assert [c.status for c in report.checks] == [OK] * 6
    checks = by_name(report)
    assert (
        "1 list(s) for 05/11/2026" in checks[f"Cause list PDFs ({OLD_SOURCE})"].detail
    )
    assert "2 pages, 2 with text" in checks[f"Cause list PDFs ({NEW_SOURCE})"].detail
    assert checks["Active judges list"].detail == "3 active judges"
    assert (
        "CR-2227-2010 found (HON'BLE MR. JUSTICE VIKAS SURI)"
        == checks["Case status"].detail
    )
    assert (
        "1 entries for HON'BLE MR. JUSTICE VIKAS SURI on 05/11/2026"
        == checks["Judge-wise cause list (daily)"].detail
    )
    assert checks["Judge-wise regular cause list"].detail.startswith(
        "latest list 01/07/2026"
    )
    assert report.egress_ip == "1.2.3.4"
    assert report.runtime.startswith("Python ")


def test_no_lists_published_is_a_warning_not_a_failure():
    manager = make_manager(old=lambda date: [], new=lambda date: [])

    checks = by_name(manager.run(CASE))

    source_check = checks[f"Cause list PDFs ({OLD_SOURCE})"]
    assert source_check.status == WARNING
    assert (
        source_check.detail
        == f"no cause lists published for the next {LOOKAHEAD_DAYS} days"
    )


def test_lists_found_on_a_later_day():
    calls = []

    def old(date):
        calls.append(date)
        return [dict(PDF)] if len(calls) == 3 else []

    checks = by_name(make_manager(old=old).run(CASE))

    assert "for 07/11/2026" in checks[f"Cause list PDFs ({OLD_SOURCE})"].detail


def test_blocked_pdf_download_fails_with_reason():
    client = MagicMock()
    client.request.side_effect = CourtSiteError("HTTP 403 Forbidden")

    report = make_manager(client=client).run(CASE)

    assert not report.healthy
    failed = {c.name: c.detail for c in report.failed}
    assert failed == {
        f"Cause list PDFs ({OLD_SOURCE})": "HTTP 403 Forbidden",
        f"Cause list PDFs ({NEW_SOURCE})": "HTTP 403 Forbidden",
    }


@pytest.mark.parametrize(
    "content, reason",
    [
        (b"<html>Session expired</html>", "downloaded file is not a PDF"),
        (make_pdf("", ""), "PDF has no searchable text (2 pages)"),
    ],
)
def test_unusable_pdf_fails(content, reason):
    checks = by_name(make_manager(pdf_bytes=content).run(CASE))

    assert checks[f"Cause list PDFs ({OLD_SOURCE})"].status == FAILED
    assert checks[f"Cause list PDFs ({OLD_SOURCE})"].detail == reason


def test_source_listing_failure_fails():
    def old(date):
        raise CourtSiteError("HTTP 500 Internal Server Error")

    checks = by_name(make_manager(old=old).run(CASE))

    assert checks[f"Cause list PDFs ({OLD_SOURCE})"].status == FAILED


def test_without_case_details_case_checks_are_skipped_as_warnings():
    checks = by_name(make_manager().run(None))

    assert checks["Case status"].status == WARNING
    assert checks["Judge-wise cause list (daily)"].status == WARNING
    assert checks["Judge-wise regular cause list"].status == OK


def test_case_status_blocked_fails_and_daily_list_is_skipped():
    api = FakeApi(
        case_info=CourtSiteError("HTTP 403 Forbidden"),
        regular_cause_list=wrapped(ENTRY),
        latest_regular_list_date="01/07/2026",
    )

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Case status"].status == FAILED
    assert checks["Case status"].detail == "HTTP 403 Forbidden"
    assert checks["Judge-wise cause list (daily)"].status == WARNING


def test_empty_judges_list_fails():
    api = FakeApi(active_judges=[], latest_regular_list_date="01/07/2026")

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Active judges list"].status == FAILED
    assert checks["Active judges list"].detail == "active judges list is empty"


def test_unmatched_bench_fails_daily_check():
    api = FakeApi(
        case_info={"case_type": "CR", "bench_name": "HON'BLE MS. JUSTICE NOBODY"},
        latest_regular_list_date="01/07/2026",
        regular_cause_list=wrapped(ENTRY),
    )

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Judge-wise cause list (daily)"].status == FAILED
    assert "could not match bench" in checks["Judge-wise cause list (daily)"].detail


def test_daily_list_empty_all_week_is_a_warning():
    api = FakeApi(
        daily_cause_list=[],
        regular_cause_list=wrapped(ENTRY),
        latest_regular_list_date="01/07/2026",
    )

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Judge-wise cause list (daily)"].status == WARNING


def test_changed_response_shape_fails():
    api = FakeApi(
        daily_cause_list=wrapped({"sr_no": 1}),
        regular_cause_list=wrapped(ENTRY),
        latest_regular_list_date="01/07/2026",
    )

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Judge-wise cause list (daily)"].status == FAILED
    assert "response shape changed" in checks["Judge-wise cause list (daily)"].detail


def test_regular_list_tries_case_judge_first_and_limits_calls():
    api = FakeApi(
        daily_cause_list=wrapped(ENTRY),
        regular_cause_list=[],
        latest_regular_list_date="01/07/2026",
    )

    checks = by_name(make_manager(api=api).run(CASE))

    regular_calls = [args for name, args in api.calls if name == "regular_cause_list"]
    assert regular_calls[0] == (650, "01/07/2026")
    assert len(regular_calls) == MAX_REGULAR_LIST_JUDGES
    assert checks["Judge-wise regular cause list"].status == WARNING


def test_missing_latest_regular_date_fails():
    api = FakeApi(
        daily_cause_list=wrapped(ENTRY),
        latest_regular_list_date=CourtSiteError("no latest regular cause list date"),
    )

    checks = by_name(make_manager(api=api).run(CASE))

    assert checks["Judge-wise regular cause list"].status == FAILED


def test_bug_in_a_check_is_reported_and_others_still_run():
    def old(date):
        raise KeyError("pdf_url")

    report = make_manager(old=old).run(CASE)

    check = by_name(report)[f"Cause list PDFs ({OLD_SOURCE})"]
    assert check.status == FAILED
    assert check.detail == "unexpected error: KeyError: 'pdf_url'"
    assert len(report.checks) == 6


def test_report_properties():
    report = HealthReport(
        checks=[
            CheckResult("a", OK, ""),
            CheckResult("b", WARNING, ""),
            CheckResult("c", FAILED, ""),
        ],
        generated_at="2026-11-04 09:00:00 IST",
        egress_ip="x",
        runtime="Python 3.13",
        region="ap-south-1",
    )

    assert [c.name for c in report.failed] == ["c"]
    assert [c.name for c in report.warnings] == ["b"]
    assert report.healthy is False


def test_default_construction_wires_shared_client():
    manager = HealthCheckManager()

    assert manager.api.client is manager.client
    assert manager.cause_lists.client is manager.client
