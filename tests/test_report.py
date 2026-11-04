import pytest

from app.managers.case_lookup import CaseLookupResult
from app.managers.cause_list_sources import NEW_SOURCE, OLD_SOURCE, CauseListResult
from app.services.emailer.report import (
    FAILED_PREFIX,
    INCOMPLETE_PREFIX,
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
