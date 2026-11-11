import pytest

from app.managers.case_manager import CaseLookupResult
from app.managers.cause_list_manager import NEW_SOURCE, OLD_SOURCE, CauseListResult
from app.services.emailer.report import (
    FAILED_PREFIX,
    INCOMPLETE_PREFIX,
    arrange_results,
    listing_summary,
    build_report,
    build_subject,
    collect_issues,
    is_search_failed,
)

READ = {"pdf_name": "Ordinary | Main List", "source": OLD_SOURCE, "num_pages": 3}
BLOCKED = {"pdf_name": "Urgent | Main List", "source": NEW_SOURCE, "error": "HTTP 403"}


def lookup(issues=()):
    return CaseLookupResult(
        case_id="CR-1-2020", case_status_url="https://status", issues=list(issues)
    )


def test_collect_issues_from_sources_pdfs_and_case_checks():
    lists = CauseListResult(
        new_pdfs=[READ, BLOCKED], source_errors={OLD_SOURCE: "HTTP 500"}
    )

    assert collect_issues(lists, lookup(["Case status for CR-1-2020: timed out"])) == [
        f"Cause lists from {OLD_SOURCE}: HTTP 500",
        f"Urgent | Main List ({NEW_SOURCE}): HTTP 403",
        "Case status for CR-1-2020: timed out",
    ]


def test_collect_issues_empty_when_all_good():
    assert collect_issues(CauseListResult(new_pdfs=[READ]), None) == []


@pytest.mark.parametrize(
    "pdfs, failed",
    [([], False), ([READ], False), ([READ, BLOCKED], False), ([BLOCKED], True)],
)
def test_is_search_failed_only_when_no_list_was_read(pdfs, failed):
    assert is_search_failed(CauseListResult(new_pdfs=pdfs)) is failed


@pytest.mark.parametrize(
    "issues, failed, prefix",
    [([], False, ""), (["x"], False, INCOMPLETE_PREFIX), (["x"], True, FAILED_PREFIX)],
)
def test_subject_prefix(issues, failed, prefix):
    subject = build_subject(["CR-1-2020"], "05/11/2026", issues, failed)

    assert (
        subject == f"{prefix}Cause List Search Results for ['CR-1-2020'] on 05/11/2026"
    )


def test_build_report_context():
    lists = CauseListResult(existing_pdfs=[READ], new_pdfs=[BLOCKED])
    case = lookup()

    report = build_report(["CR-1-2020"], "05/11/2026", lists, [], case)
    context = report["context"]

    assert report["subject"].startswith(INCOMPLETE_PREFIX)
    assert context["pdfs"] == [READ, BLOCKED]
    assert context["new_pdfs"] == [BLOCKED]
    assert context["case_lookup"] is case
    assert context["urls"]["case_status_url"] == "https://status"
    assert [s["name"] for s in context["sources"]] == [OLD_SOURCE, NEW_SOURCE]
    assert context["search_failed"] is False


def test_build_report_without_case_uses_search_url():
    report = build_report(
        ["x"], "05/11/2026", CauseListResult(new_pdfs=[READ]), [], None
    )

    assert report["subject"] == "Cause List Search Results for ['x'] on 05/11/2026"
    assert report["context"]["urls"]["case_status_url"].startswith("https://")
    assert report["context"]["issues"] == []


TERMS = ["Krishan Chand", "RSA-4610-2011"]


def _entry(item_no, case_no, terms):
    return {"terms": terms, "is_entry": True, "item_no": item_no, "case_no": case_no}


def _result(pdf_name, matches):
    return {"pdf_name": pdf_name, "found_pages": {}, "matches": matches}


CONTEXT_HIT = {"terms": ["Krishan Chand"], "is_entry": False, "page": 92}


def test_lists_with_case_number_hits_come_first():
    ordinary = _result("Ordinary | Main List", [_entry("296", "CWP-1-2026", TERMS[:1])])
    regular = _result(
        "Regular | Supplementary List", [_entry("404", "RSA-4610-2011", TERMS)]
    )

    arranged = arrange_results([ordinary, regular], TERMS)

    assert [r["pdf_name"] for r in arranged] == [
        "Regular | Supplementary List",
        "Ordinary | Main List",
    ]


def test_complete_list_hides_entries_already_shown_in_other_lists():
    ordinary = _result("Ordinary | Main List", [_entry("296", "CWP-1-2026", TERMS[:1])])
    complete = _result(
        "Complete List | Main List",
        [_entry("296", "CWP-1-2026", TERMS[:1]), _entry("7", "CR-9-2020", TERMS[:1])],
    )

    arranged = arrange_results([complete, ordinary], TERMS)
    shown = {r["pdf_name"]: r for r in arranged}

    assert [e["item_no"] for e in shown["Complete List | Main List"]["entries"]] == [
        "7"
    ]
    assert shown["Complete List | Main List"]["hidden_duplicates"] == 1
    assert shown["Ordinary | Main List"]["hidden_duplicates"] == 0


def test_context_hits_are_kept_apart_from_entries():
    urgent = _result(
        "Urgent | Main List", [CONTEXT_HIT, _entry("141", "FAO-1-2026", TERMS[:1])]
    )

    arranged = arrange_results([urgent], TERMS)[0]

    assert [e["item_no"] for e in arranged["entries"]] == ["141"]
    assert arranged["context_hits"] == [CONTEXT_HIT]


def test_arrange_does_not_mutate_and_handles_results_without_matches():
    plain = {"pdf_name": "Ordinary | Main List", "found_pages": {"x": [3]}}
    original = dict(plain)

    arranged = arrange_results([plain], ["x"])[0]

    assert plain == original
    assert arranged["entries"] == [] and arranged["context_hits"] == []


def test_build_report_passes_arranged_results():
    regular = _result(
        "Regular | Supplementary List", [_entry("404", "RSA-4610-2011", TERMS)]
    )

    report = build_report(
        TERMS, "12/11/2026", CauseListResult(new_pdfs=[READ]), [regular], None
    )

    assert report["context"]["results"][0]["entries"][0]["item_no"] == "404"


def _case_lookup(listing_entry=None):
    return CaseLookupResult(
        case_id="RSA-4610-2011",
        case_status_url="https://status",
        listing_entry=listing_entry,
    )


PDF_ENTRY = {
    **_entry("404", "RSA-4610-2011", TERMS),
    "page": 113,
    "bench": ["HON'BLE MR. JUSTICE VIRINDER AGGARWAL"],
    "court_room": "12",
}
LISTING = {
    "cl_date": "2026-07-01T00:00:00",
    "cl_type": "REGULAR",
    "sr_no": 583,
    "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
}


def test_listing_summary_prefers_the_pdf_entry_with_the_case_number():
    results = arrange_results(
        [_result("Regular | Supplementary List", [PDF_ENTRY])], TERMS
    )

    summary = listing_summary(_case_lookup(LISTING), results)

    assert summary == {
        "case_id": "RSA-4610-2011",
        "list_name": "Regular · Supplementary List",
        "item_no": "404",
        "bench": "HON'BLE MR. JUSTICE VIRINDER AGGARWAL",
        "court_room": "12",
        "page": 113,
        "source": "cause-list PDF",
    }


def test_listing_summary_falls_back_to_listing_history():
    summary = listing_summary(_case_lookup(LISTING), [])

    assert summary == {
        "case_id": "RSA-4610-2011",
        "list_name": "Regular cause list",
        "item_no": "583",
        "bench": "HON'BLE MR. JUSTICE VIKAS SURI",
        "court_room": None,
        "page": None,
        "source": "case listing history",
    }


def test_no_listing_summary_without_case_evidence():
    other_case = _result("Ordinary | Main List", [_entry("1", "CWP-1-2026", TERMS[:1])])

    assert listing_summary(_case_lookup(), arrange_results([other_case], TERMS)) is None
    assert listing_summary(None, []) is None


def test_build_report_counts_lists_read_and_notes_missing_regular_pdf():
    lists = CauseListResult(new_pdfs=[READ, BLOCKED])

    context = build_report(["x"], "01/07/2026", lists, [], None)["context"]

    assert context["lists_read"] == 1
    assert context["has_regular_pdf"] is False
    assert context["listing_summary"] is None


def test_build_report_sees_regular_pdf():
    regular = {"pdf_name": "Regular | Main List", "source": OLD_SOURCE, "num_pages": 9}

    context = build_report(
        ["x"], "12/11/2026", CauseListResult(new_pdfs=[regular]), [], None
    )["context"]

    assert context["has_regular_pdf"] is True
