import pytest

from app.clients.court_http import CourtSiteError
from app.managers.case_manager import CaseManager
from app.managers.cause_list_entries import ListedBench
from app.managers.judge_cause_list_manager import (
    FOUND,
    NOT_FOUND,
    UNAVAILABLE,
    JudgeListOutcome,
)
from tests.fakes import CASE, ENTRY, OTHER, FakeApi, wrapped

TERMS = ["CR-2227-2010"]
DATE = "05/11/2026"


def run(api: FakeApi, date: str = DATE):
    return CaseManager(api).lookup(CASE, TERMS, date)


def test_found_in_daily_list_and_case_status_built():
    api = FakeApi(daily_cause_list=wrapped(OTHER, ENTRY))

    result = run(api)

    assert result.case_id == "CR-2227-2010"
    assert "case_no=2227" in result.case_status_url
    assert "Case Details For Case CR-2227-2010" in result.case_details_html
    assert result.daily.status == FOUND
    assert result.daily.entries_checked == 2
    assert "<td>583</td>" in result.daily.html
    assert result.regular.status == NOT_FOUND
    assert result.issues == []


def test_not_found_reports_entries_checked_and_bench():
    result = run(FakeApi())

    assert result.daily.status == NOT_FOUND
    assert result.daily.entries_checked == 1
    assert result.daily.bench_name == "HON'BLE MR. JUSTICE VIKAS SURI"


def test_case_status_failure_marks_everything_unavailable():
    api = FakeApi(case_info=CourtSiteError("HTTP 403 Forbidden"))

    result = run(api)

    assert result.case_details_html is None
    assert result.daily.status == UNAVAILABLE and result.regular.status == UNAVAILABLE
    assert result.daily.error == "case status unavailable (HTTP 403 Forbidden)"
    assert result.issues == [
        "Case status for CR-2227-2010: case status unavailable (HTTP 403 Forbidden)"
    ]


def test_optional_section_failure_is_reported_but_lookup_continues():
    api = FakeApi(
        judgments=CourtSiteError("timed out"), daily_cause_list=wrapped(ENTRY)
    )

    result = run(api)

    assert result.case_details_html
    assert result.daily.status == FOUND
    assert result.issues == ["Judgment details for CR-2227-2010: timed out"]


def test_daily_list_failure_is_unavailable_not_not_found():
    api = FakeApi(daily_cause_list=CourtSiteError("HTTP 429 Too Many Requests"))

    result = run(api)

    assert result.daily.status == UNAVAILABLE
    assert result.daily.error == "HTTP 429 Too Many Requests"
    assert (
        "Judge-wise cause list for HON'BLE MR. JUSTICE VIKAS SURI: HTTP 429 Too Many Requests"
        in result.issues
    )
    assert result.regular.status == NOT_FOUND


def test_judge_list_failure_marks_both_judge_lists_unavailable():
    api = FakeApi(active_judges=CourtSiteError("connection failed"))

    result = run(api)

    assert result.case_details_html
    assert (
        result.daily.error
        == result.regular.error
        == "judge list unavailable (connection failed)"
    )
    assert result.issues == [
        "Judge-wise cause lists for CR-2227-2010: judge list unavailable (connection failed)"
    ]


def test_unmatched_bench_is_reported():
    api = FakeApi(
        case_info={"case_type": "CR", "bench_name": "HON'BLE MS. JUSTICE NOBODY"}
    )

    result = run(api)

    assert result.daily.status == UNAVAILABLE
    assert "could not match bench" in result.daily.error


def test_case_without_bench_is_reported():
    api = FakeApi(case_info={"case_type": "CR", "bench_name": ""})

    assert run(api).daily.error == "case has no bench assigned"


def test_uses_bench_from_listing_for_the_date_over_current_bench():
    listing = [
        {
            "cl_date": "2026-11-05T00:00:00",
            "cl_type": "REGULAR",
            "sr_no": 12,
            "bench_code": 9001,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE OTHER JUDGE"},
        }
    ]
    api = FakeApi(listing_history=listing)

    result = run(api)

    assert ("daily_cause_list", (701, DATE)) in api.calls
    assert result.daily.bench_name == "HON'BLE MR. JUSTICE OTHER JUDGE"


def test_listing_bench_code_unknown_falls_back_to_listing_bench_name():
    listing = [
        {
            "cl_date": "2026-11-05",
            "bench_code": 1,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE OTHER JUDGE"},
        }
    ]
    api = FakeApi(listing_history=listing)

    run(api)

    assert ("daily_cause_list", (701, DATE)) in api.calls


def test_listing_bench_unresolvable_falls_back_to_current_bench():
    listing = [
        {
            "cl_date": "2026-11-05",
            "bench_code": 1,
            "benchDetails": {"bench_name": "HON'BLE MS. JUSTICE NOBODY"},
        }
    ]
    api = FakeApi(listing_history=listing)

    run(api)

    assert ("daily_cause_list", (650, DATE)) in api.calls


PDF_BENCH = ListedBench(
    name="HON'BLE MR. JUSTICE OTHER JUDGE",
    source="Regular | Supplementary List p. 113",
    is_regular_list=True,
)


def test_uses_bench_from_cause_list_pdf_when_listing_history_lacks_the_date():
    api = FakeApi()

    result = CaseManager(api).lookup(CASE, TERMS, DATE, listed_bench=PDF_BENCH)

    assert ("daily_cause_list", (701, DATE)) in api.calls
    assert result.daily.bench_name == "HON'BLE MR. JUSTICE OTHER JUDGE"
    assert result.daily.bench_source == "Regular | Supplementary List p. 113"
    assert result.regular.bench_source == "Regular | Supplementary List p. 113"


def test_listing_history_bench_wins_over_pdf_bench():
    listing = [
        {
            "cl_date": "2026-11-05",
            "bench_code": 4485,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
        }
    ]
    api = FakeApi(listing_history=listing)

    result = CaseManager(api).lookup(CASE, TERMS, DATE, listed_bench=PDF_BENCH)

    assert ("daily_cause_list", (650, DATE)) in api.calls
    assert result.daily.bench_source == "case listing history"


def test_regular_list_unpublished_but_case_printed_in_regular_pdf_shows_found():
    api = FakeApi(regular_cause_list=[])

    result = CaseManager(api).lookup(CASE, TERMS, DATE, listed_bench=PDF_BENCH)

    assert result.regular.status == FOUND
    assert "Regular | Supplementary List p. 113" in result.regular.html
    assert "HON'BLE MR. JUSTICE OTHER JUDGE" in result.regular.html
    assert result.regular.bench_source == "Regular | Supplementary List p. 113"


def test_case_printed_in_non_regular_pdf_does_not_mark_regular_found():
    api = FakeApi(regular_cause_list=[])
    bench = ListedBench(name=PDF_BENCH.name, source="Ordinary | Main List p. 81")

    result = CaseManager(api).lookup(CASE, TERMS, DATE, listed_bench=bench)

    assert result.regular.status == NOT_FOUND


def test_unmatchable_pdf_bench_falls_back_to_assigned_bench():
    api = FakeApi()
    bench = ListedBench(name="HON'BLE LOK ADALAT BENCH - 2", source="Lok Adalat p. 2")

    result = CaseManager(api).lookup(CASE, TERMS, DATE, listed_bench=bench)

    assert ("daily_cause_list", (650, DATE)) in api.calls
    assert result.daily.bench_source == "case's assigned bench"


def test_regular_list_missing_but_listing_history_says_listed_shows_fallback():
    listing = [
        {
            "cl_date": "2026-11-05T00:00:00",
            "cl_type": "REGULAR",
            "sr_no": 583,
            "bench_code": 4485,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
        }
    ]
    api = FakeApi(listing_history=listing, regular_cause_list=[])

    result = run(api)

    assert result.regular.status == FOUND
    assert "583" in result.regular.html


def test_listing_history_for_other_dates_is_ignored():
    listing = [
        {"cl_date": "2026-07-01T00:00:00", "bench_code": 9001, "benchDetails": {}}
    ]
    api = FakeApi(listing_history=listing)

    run(api)

    assert ("daily_cause_list", (650, DATE)) in api.calls


@pytest.mark.parametrize(
    "outcome, status",
    [
        (JudgeListOutcome(error="x"), UNAVAILABLE),
        (JudgeListOutcome(html="<t/>"), FOUND),
        (JudgeListOutcome(), NOT_FOUND),
    ],
)
def test_outcome_status(outcome, status):
    assert outcome.status == status


def test_regular_list_failure_still_shows_listing_history_and_reports_issue():
    listing = [
        {
            "cl_date": "2026-11-05T00:00:00",
            "cl_type": "REGULAR",
            "sr_no": 583,
            "bench_code": 4485,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
        }
    ]
    api = FakeApi(
        listing_history=listing,
        regular_cause_list=CourtSiteError("HTTP 504 Gateway Timeout"),
    )

    result = run(api)

    assert result.regular.status == FOUND
    assert "583" in result.regular.html
    assert (
        "Judge-wise regular cause list for HON'BLE MR. JUSTICE VIKAS SURI: "
        "HTTP 504 Gateway Timeout" in result.issues
    )


def test_regular_list_failure_without_listing_stays_unavailable():
    api = FakeApi(regular_cause_list=CourtSiteError("HTTP 504 Gateway Timeout"))

    assert run(api).regular.status == UNAVAILABLE


def test_lookup_skipped_without_case_details():
    assert CaseManager(FakeApi()).lookup(None, TERMS, DATE) is None
