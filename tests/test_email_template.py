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
    assert "No search results found in the 1 cause-list PDF that could be read" in html


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


ENTRY_ROW = {
    "terms": ["Krishan Chand", "RSA-4610-2011"],
    "is_entry": True,
    "item_no": "404",
    "case_no": "RSA-4610-2011",
    "page": 113,
    "last_page": 114,
    "bench": ["HON'BLE MR. JUSTICE VIRINDER AGGARWAL"],
    "court_room": "12",
    "lines": ["404 ** RSA-4610-2011", "KRISHAN CHAND V/S TARSEM CHAND <AND> ORS."],
    "truncated": True,
}
CONTEXT_ROW = {
    **ENTRY_ROW,
    "terms": ["Krishan Chand"],
    "is_entry": False,
    "item_no": None,
    "case_no": None,
    "page": 7,
    "last_page": 7,
    "bench": [],
    "court_room": None,
    "lines": ["notice about KRISHAN CHAND"],
    "truncated": False,
}


def test_matched_entries_sit_in_a_detail_row_under_their_list():
    result = {
        **OLD_PDF,
        "pdf_name": "Regular | Supplementary List",
        "found_pages": {"CR-2227-2010": [113]},
        "matches": [ENTRY_ROW, CONTEXT_ROW],
    }

    html = render(results=[result])

    list_row = html.index('<tr class="list-row">')
    detail_row = html.index('<tr class="detail-row">')
    assert list_row < detail_row
    assert '<td colspan="5">' in html[detail_row:]
    assert "<th>Found</th>" in html
    assert "<h2>Matched Entries</h2>" not in html
    found_cell = html[list_row:detail_row]
    assert "#404" in found_cell and "RSA-4610-2011" in found_cell
    assert "pp. 113–114" in found_cell
    assert "p. 7 &middot; text outside a numbered entry" in found_cell
    details = html[detail_row:]
    assert "HON&#39;BLE MR. JUSTICE VIRINDER AGGARWAL" in details
    assert "CR NO 12" in details
    assert "&lt;AND&gt;" in details  # PDF text is escaped, never raw HTML
    assert "entry continues in the PDF" in details
    assert "notice about KRISHAN CHAND" not in html  # context hits stay one line


def test_complete_list_notes_entries_hidden_as_duplicates():
    regular = {**OLD_PDF, "pdf_name": "Regular | Main List", "matches": [ENTRY_ROW]}
    complete = {
        **OLD_PDF,
        "pdf_name": "Complete List | Main List",
        "matches": [ENTRY_ROW],
    }

    html = render(results=[complete, regular])

    assert "1 entry also in other lists above" in html
    assert html.count('<tr class="detail-row">') == 1


def test_results_without_matches_fall_back_to_pages_per_term():
    result = {**OLD_PDF, "found_pages": {"CR-2227-2010": [3]}}

    html = render(results=[result])

    assert "<strong>CR-2227-2010:</strong>" in html
    assert '<tr class="detail-row">' not in html


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


def test_entry_with_columns_renders_case_parties_advocates_table():
    columns = {
        "case": ["404 ** RSA-4610-2011", "CM-13421-C-2011"],
        "parties": ["KRISHAN CHAND V/S TARSEM CHAND", "AND ORS."],
        "advocates": [", ASHISH KASHYAP,,", "BALDEV RAJ MAHAJAN,"],
    }
    result = {
        **OLD_PDF,
        "found_pages": {"CR-2227-2010": [113]},
        "matches": [{**ENTRY_ROW, "columns": columns}],
    }

    html = render(results=[result])

    assert "<th>Case</th><th>Parties</th><th>Advocates</th>" in html
    assert "404 ** RSA-4610-2011<br>CM-13421-C-2011" in html
    assert "KRISHAN CHAND V/S TARSEM CHAND<br>AND ORS." in html
    assert ", ASHISH KASHYAP,,<br>BALDEV RAJ MAHAJAN," in html
    assert '<pre class="entry-text">' not in html


def test_judge_wise_sections_say_which_bench_was_checked_and_why():
    outcome = JudgeListOutcome(
        entries_checked=12,
        bench_name="HON'BLE MR. JUSTICE VIRINDER AGGARWAL",
        bench_source="Regular | Supplementary List, item 404, p. 113",
    )
    html = render(case_lookup=case(daily=outcome, regular=outcome))

    assert (
        html.count(
            "Bench checked: HON&#39;BLE MR. JUSTICE VIRINDER AGGARWAL "
            "(from Regular | Supplementary List, item 404, p. 113)"
        )
        == 2
    )


def test_summary_line_tops_the_email_when_the_case_is_listed():
    lookup = case(
        listing_entry={
            "cl_type": "REGULAR",
            "sr_no": 583,
            "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
        }
    )

    html = render(case_lookup=lookup)

    summary = html.index('listing-summary"')
    assert summary < html.index("Cause Lists Searched")
    assert (
        "CR-2227-2010 is listed on 05/11/2026: Regular cause list, item 583, "
        "HON&#39;BLE MR. JUSTICE VIKAS SURI (from case listing history)"
    ) in " ".join(html[summary:].split())


def test_no_summary_line_when_case_not_listed():
    assert 'listing-summary"' not in render(case_lookup=case())


def test_not_found_message_counts_lists_and_explains_missing_regular_pdf():
    html = render(case_lookup=case())

    assert "No search results found in the 2 cause-list PDFs." in html
    assert "No Regular cause list PDF was published for this date" in html
    assert "see the Judge-Wise Regular Cause List below" in html


def test_not_found_message_without_case_skips_judge_wise_pointer():
    html = render()

    assert "No Regular cause list PDF was published for this date." in html
    assert "Judge-Wise Regular Cause List below" not in html
