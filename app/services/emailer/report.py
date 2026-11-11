"""Builds the cause-list email (context + subject) in one place for Lambda and API."""

from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.managers.case_manager import CaseLookupResult
from app.managers.cause_list_manager import (
    COMPLETE_LIST,
    REGULAR_LIST,
    CauseListResult,
    Pdf,
    cause_list_sources,
    pdf_list_type,
)
from app.utils.search_terms import is_case_number

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


def _is_complete_list(result: Dict[str, Any]) -> bool:
    return pdf_list_type(result["pdf_name"]) == COMPLETE_LIST


def _entry_key(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    return (row.get("item_no"), row.get("case_no"))


def arrange_results(
    results: List[Dict[str, Any]], search_terms: List[str]
) -> List[Dict[str, Any]]:
    """Results ready for the email table, as new dicts (inputs are not changed).

    Each gets `entries` (numbered listings), `context_hits` (text outside any
    entry) and `hidden_duplicates`. The Complete List repeats entries from the
    other lists, so those are hidden there. Lists where a case number matched
    come first.
    """
    case_terms = {term for term in search_terms if is_case_number(term)}
    shown_elsewhere = {
        _entry_key(row)
        for result in results
        if not _is_complete_list(result)
        for row in result.get("matches", [])
        if row.get("is_entry")
    }

    arranged = []
    for result in results:
        rows = result.get("matches", [])
        entries = [row for row in rows if row.get("is_entry")]
        hidden = 0
        if _is_complete_list(result):
            kept = [row for row in entries if _entry_key(row) not in shown_elsewhere]
            hidden, entries = len(entries) - len(kept), kept
        arranged.append(
            {
                **result,
                "entries": entries,
                "context_hits": [row for row in rows if not row.get("is_entry")],
                "hidden_duplicates": hidden,
            }
        )

    def has_case_hit(result: Dict[str, Any]) -> bool:
        return any(case_terms & set(row.get("terms", [])) for row in result["entries"])

    return sorted(arranged, key=lambda result: not has_case_hit(result))


def listing_summary(
    case_lookup: Optional[CaseLookupResult], arranged: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Where the searched case is listed, from evidence tied to its case number.

    A cause-list PDF entry with the case number wins (it has page and court
    room); otherwise the case's listing history entry for the date. Judge-wise
    "found" is not used: a name can match a different case there.
    """
    if not case_lookup:
        return None
    return _summary_from_pdf(case_lookup.case_id, arranged) or _summary_from_history(
        case_lookup.case_id, case_lookup.listing_entry
    )


def _summary_from_pdf(
    case_id: str, arranged: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    for result in arranged:
        for row in result["entries"]:
            if (row.get("case_no") or "").upper() == case_id.upper():
                return _summary(
                    case_id,
                    list_name=result["pdf_name"].replace(" | ", " · "),
                    item_no=row.get("item_no"),
                    bench=" & ".join(row.get("bench") or []) or None,
                    court_room=row.get("court_room"),
                    page=row.get("page"),
                    source="cause-list PDF",
                )
    return None


def _summary_from_history(
    case_id: str, entry: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not entry:
        return None
    details = entry.get("benchDetails")
    sr_no = entry.get("sr_no")
    return _summary(
        case_id,
        list_name=f"{str(entry.get('cl_type') or 'Cause').title()} cause list",
        item_no=str(sr_no) if sr_no is not None else None,
        bench=details.get("bench_name") if isinstance(details, dict) else None,
        source="case listing history",
    )


def _summary(
    case_id: str,
    list_name: str,
    item_no: Optional[str],
    bench: Optional[str],
    source: str,
    court_room: Optional[str] = None,
    page: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "list_name": list_name,
        "item_no": item_no,
        "bench": bench,
        "court_room": court_room,
        "page": page,
        "source": source,
    }


def _lists_read(pdfs: List[Pdf]) -> int:
    return sum(1 for pdf in pdfs if pdf.get("num_pages") and not pdf.get("error"))


def _has_regular_pdf(pdfs: List[Pdf]) -> bool:
    return any(pdf_list_type(pdf["pdf_name"]) == REGULAR_LIST for pdf in pdfs)


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
    arranged = arrange_results(results, search_terms)
    context = {
        "search_terms": search_terms,
        "date": date,
        "results": arranged,
        "listing_summary": listing_summary(case_lookup, arranged),
        "lists_read": _lists_read(cause_lists.pdfs),
        "has_regular_pdf": _has_regular_pdf(cause_lists.pdfs),
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
