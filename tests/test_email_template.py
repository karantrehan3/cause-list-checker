import pytest

from app.managers.case_manager import CaseLookupResult, JudgeListOutcome
from app.managers.cause_list_manager import NEW_SOURCE, OLD_SOURCE, CauseListResult
from app.services.emailer import Emailer
from app.services.emailer.report import build_report

OLD_PDF = {
    "pdf_name": "Ordinary | Main List",
    "pdf_url": "https://old/o",
    "source": OLD_SOURCE,
    "num_pages": 411,
}
NEW_PDF = {
    "pdf_name": "Ordinary | Main List",
    "pdf_url": "https://new/o",
    "source": NEW_SOURCE,
    "num_pages": 411,
}


def render(pdfs=(OLD_PDF, NEW_PDF), results=(), case_lookup=None, source_errors=None):
    lists = CauseListResult(new_pdfs=list(pdfs), source_errors=source_errors or {})
    report = build_report(
        ["CR-2227-2010"], "05/11/2026", lists, list(results), case_lookup
    )
    return (
        Emailer()
        .env.get_template("cause_list_template.html")
        .render({**report["context"], "generated_timestamp": "now"})
    )


def case(**kwargs):
    defaults = dict(
        case_id="CR-2227-2010",
        case_status_url="https://status",
        case_details_html="<p>CASE</p>",
    )
    return CaseLookupResult(**{**defaults, **kwargs})


def test_one_cause_list_table_per_source_with_pages():
    html = render()

    assert html.count("Cause Lists Searched &mdash;") == 2
    assert html.index(OLD_SOURCE) < html.index(NEW_SOURCE)
    assert "411 pages" in html
    assert 'issues-banner"' not in html


def test_unread_list_shows_reason_and_banner():
    html = render(pdfs=[OLD_PDF, {**NEW_PDF, "num_pages": None, "error": "HTTP 403"}])

    assert "❌ Not read (HTTP 403)" in html
    assert "⚠️ Some checks could not be completed" in html
    assert f"Ordinary | Main List ({NEW_SOURCE}): HTTP 403" in html
    assert "No search results found in the lists that could be read" in html


def test_all_lists_unread_shows_search_failed():
    html = render(pdfs=[{**OLD_PDF, "num_pages": None, "error": "HTTP 403"}])

    assert "❌ SEARCH FAILED: no cause list could be read." in html


def test_failed_source_shows_its_error():
    html = render(pdfs=[NEW_PDF], source_errors={OLD_SOURCE: "HTTP 500"})

    assert f"Could not get cause lists from {OLD_SOURCE}: HTTP 500" in html
    assert f"Cause lists from {OLD_SOURCE}: HTTP 500" in html


def test_source_with_no_lists_shows_warning():
    assert f"No cause lists from {NEW_SOURCE}" in render(pdfs=[OLD_PDF])


def test_results_table_shows_source():
    result = {**OLD_PDF, "found_pages": {"CR-2227-2010": [3]}}

    html = render(results=[result])

    assert "✅ Search results found." in html
    assert f"<td>{OLD_SOURCE}</td>" in html


def test_no_case_details_hides_case_sections():
    html = render()

    assert "Judge-Wise Cause List" not in html
    assert "Case Status Details" not in html


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (
            JudgeListOutcome(
                html="<table>DAILY</table>", entries_checked=5, bench_name="J"
            ),
            "✅ Search term found in Judge-Wise Cause List",
        ),
        (
            JudgeListOutcome(entries_checked=61, bench_name="JUSTICE X"),
            "(61 entries checked for JUSTICE X)",
        ),
        (
            JudgeListOutcome(error="HTTP 429 Too Many Requests"),
            "⚠️ Could not check Judge-Wise Cause List: HTTP 429 Too Many Requests",
        ),
    ],
)
def test_daily_judge_wise_three_states(outcome, expected):
    html = render(case_lookup=case(daily=outcome))

    assert expected in html
    assert "Judge-Wise Regular Cause List" in html
    assert "<p>CASE</p>" in html


def test_case_status_unavailable_message():
    html = render(
        case_lookup=case(
            case_details_html=None, issues=["Case status for CR-2227-2010: HTTP 403"]
        )
    )

    assert "⚠️ Case status for CR-2227-2010 could not be loaded" in html
    assert "Case status for CR-2227-2010: HTTP 403" in html
