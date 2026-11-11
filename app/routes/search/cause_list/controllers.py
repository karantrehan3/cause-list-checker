import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.config import settings
from app.managers.case_manager import CaseManager, listed_bench_from
from app.managers.cause_list_manager import CauseListManager
from app.managers.pdf_searcher import PDFSearcher
from app.managers.queue import queue_manager
from app.services.emailer import Emailer
from app.services.emailer.report import build_report
from app.utils.error_handler import ErrorHandler
from app.utils.helpers import get_weekend_dates


@dataclass
class QueuedSearch:
    search_terms: List[str]
    date: str
    recipient_emails: List[str]
    case_details: Optional[Dict[str, str]] = None


async def scrape_search_and_notify(
    search_terms: List[str],
    date: Optional[str] = None,
    recipient_emails: Optional[List[str]] = None,
    case_details: Dict[str, str] = None,
) -> Dict[str, Any]:
    # Ensure queue processor is running
    await queue_manager.start_processor()

    if not recipient_emails:
        recipient_emails = settings.EMAIL_RECIPIENTS.split(",")

    if not date:
        date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    # Get all dates to process based on weekend logic
    dates_to_process = get_weekend_dates(date)

    print(f"Processing dates: {dates_to_process}", flush=True)

    # Queue all the searches
    for process_date in dates_to_process:
        await queue_search_task(
            search_terms=search_terms,
            date=process_date,
            recipient_emails=recipient_emails,
            case_details=case_details,
            max_attempts=3,
        )
        print(f"Queued search for date: {process_date}", flush=True)

    return {
        "message": f"Search and notification process queued for {len(dates_to_process)} date(s)",
        "dates": dates_to_process,
        "queue_size": queue_manager.get_queue_status()["queue_size"],
    }


async def queue_search_task(
    search_terms: List[str],
    date: str,
    recipient_emails: List[str],
    case_details: Optional[Dict[str, str]] = None,
    max_attempts: int = 3,
):
    """Queue a search task with the standard search method."""

    task_id = f"search_{date}_{'_'.join(search_terms)}"
    queued_search = QueuedSearch(search_terms, date, recipient_emails, case_details)
    await queue_manager.add_task(
        process_single_search,
        queued_search,
        max_attempts=max_attempts,
        task_id=task_id,
    )


async def process_single_search(queued_search: QueuedSearch) -> bool:
    """
    Process a single search with retry logic.

    Args:
        queued_search: The search to process

    Returns:
        True if successful, False if failed after max attempts
    """
    cause_list_manager = CauseListManager()
    case_manager = CaseManager(cause_list_manager.api)
    searcher = PDFSearcher(search_terms=queued_search.search_terms)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, queued_search.recipient_emails)

    try:
        # Step 1: Cause lists
        cause_lists = await asyncio.to_thread(
            cause_list_manager.fetch,
            queued_search.date,
            queued_search.search_terms,
        )

        # Step 2: Search for the terms in the PDFs (run in separate thread)
        pdfs = cause_lists.pdfs
        results = await asyncio.to_thread(searcher.search_pdf, pdfs) if pdfs else []
        if not pdfs:
            print(f"ALERT! No Cause Lists found for {queued_search.date}", flush=True)

        # Step 3: Case checks; after the PDFs, which supply the bench
        case_lookup = await asyncio.to_thread(
            case_manager.lookup,
            queued_search.case_details,
            queued_search.search_terms,
            queued_search.date,
            listed_bench=listed_bench_from(results, queued_search.case_details),
        )

        print(
            f"PROGRESS! Cause List Search Results for {queued_search.date}: ",
            json.dumps(results, indent=2),
            flush=True,
        )

        # Step 4: Email the report
        send_report(
            emailer,
            queued_search.recipient_emails,
            build_report(
                queued_search.search_terms,
                queued_search.date,
                cause_lists,
                results,
                case_lookup,
            ),
        )

        print(
            f"SUCCESS! Search completed and email sent for {queued_search.date}! ",
            json.dumps(results, indent=2),
            flush=True,
        )
        return True

    except Exception as e:
        error_message, stack_trace = error_handler.handle_exception(
            e, {"search_terms": queued_search.search_terms, "date": queued_search.date}
        )
        print(
            f"ERROR! Search failed for {queued_search.date}: {error_message}",
            flush=True,
        )
        return False


def send_report(
    emailer: Emailer, email_list: List[str], report: Dict[str, Any]
) -> None:
    for issue in report["context"]["issues"]:
        print(f"ISSUE! {issue}", flush=True)
    try:
        emailer.send_email(
            recipients=email_list,
            subject=report["subject"],
            template_name="cause_list_template.html",
            context=report["context"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending email: {e}")
