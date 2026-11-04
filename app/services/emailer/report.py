"""Builds the cause-list email (context + subject) in one place for Lambda and API."""

from typing import Any, Dict, List, Optional

from app.config import settings
from app.managers.case_manager import CaseLookupResult
from app.managers.cause_list_manager import CauseListResult, cause_list_sources

INCOMPLETE_PREFIX = "⚠️ INCOMPLETE – "
FAILED_PREFIX = "❌ SEARCH FAILED – "


def collect_issues(
    cause_lists: CauseListResult, case_lookup: Optional[CaseLookupResult]
) -> List[str]:
    """Every check that could not be completed, in a human-readable form."""
    issues = [
        f"Cause lists from {source}: {reason}"
        for source, reason in cause_lists.source_errors.items()
    ]
    issues += [
        f"{pdf['pdf_name']} ({pdf.get('source', '')}): {pdf['error']}"
        for pdf in cause_lists.pdfs
        if pdf.get("error")
    ]
    if case_lookup:
        issues += case_lookup.issues
    return issues


def is_search_failed(cause_lists: CauseListResult) -> bool:
    """True when not a single cause list could be read."""
    pdfs = cause_lists.pdfs
    return bool(pdfs) and all(pdf.get("error") for pdf in pdfs)


def build_subject(
    search_terms: List[str], date: str, issues: List[str], search_failed: bool
) -> str:
    subject = f"Cause List Search Results for {search_terms} on {date}"
    if search_failed:
        return FAILED_PREFIX + subject
    if issues:
        return INCOMPLETE_PREFIX + subject
    return subject


def build_report(
    search_terms: List[str],
    date: str,
    cause_lists: CauseListResult,
    results: List[Dict[str, Any]],
    case_lookup: Optional[CaseLookupResult],
) -> Dict[str, Any]:
    """Return {"subject": ..., "context": ...} for cause_list_template.html."""
    issues = collect_issues(cause_lists, case_lookup)
    search_failed = is_search_failed(cause_lists)
    context = {
        "search_terms": search_terms,
        "date": date,
        "results": results,
        "pdfs": cause_lists.pdfs,
        "existing_pdfs": cause_lists.existing_pdfs,
        "new_pdfs": cause_lists.new_pdfs,
        "sources": cause_list_sources(),
        "source_errors": cause_lists.source_errors,
        "case_lookup": case_lookup,
        "issues": issues,
        "search_failed": search_failed,
        "urls": {
            "cl_base_url": settings.CL_BASE_URL,
            "case_search_url": settings.CASE_SEARCH_URL,
            "cl_judge_wise_url": settings.CL_JUDGE_WISE_URL,
            "cl_judge_wise_regular_url": settings.CL_JUDGE_WISE_REGULAR_URL,
            "case_status_url": (
                case_lookup.case_status_url if case_lookup else settings.CASE_SEARCH_URL
            ),
        },
    }
    return {
        "subject": build_subject(search_terms, date, issues, search_failed),
        "context": context,
    }
