import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.config import settings
from app.managers.pdf_searcher import PDFSearcher
from app.managers.queue import queue_manager
from app.managers.scraper import Scraper
from app.services.emailer import Emailer
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
    scraper = Scraper()
    searcher = PDFSearcher(search_terms=queued_search.search_terms)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, queued_search.recipient_emails)

    try:
        # Step 1 & 2: Scrape the page and get PDF links & Case details in parallel
        pdfs, result = await asyncio.gather(
            asyncio.to_thread(
                scraper.parse_table_and_download_pdfs, queued_search.date
            ),
            asyncio.to_thread(
                scraper.get_case_details_and_judge_details,
                queued_search.case_details,
                queued_search.search_terms,
                queued_search.date,
            ),
        )

        case_details_html, term_found_in_regular_cause_list = (
            result if result is not None else (None, "")
        )

        if not pdfs:
            send_email(
                emailer,
                queued_search.recipient_emails,
                queued_search.search_terms,
                queued_search.date,
                pdfs,
                [],
                case_details_html,
                term_found_in_regular_cause_list,
            )
            print(f"ALERT! No Cause Lists found for {queued_search.date}", flush=True)
            return True

        print(
            f"PROGRESS! Cause Lists found for {queued_search.date}: ",
            json.dumps(pdfs, indent=2),
            flush=True,
        )

        # Step 3: Search for the terms in the PDFs (run in separate thread)
        results = await asyncio.to_thread(searcher.search_pdf, pdfs)

        print(
            f"PROGRESS! Cause List Search Results for {queued_search.date}: ",
            json.dumps(results, indent=2),
            flush=True,
        )

        # Step 4: If results found, send an email notification
        send_email(
            emailer,
            queued_search.recipient_emails,
            queued_search.search_terms,
            queued_search.date,
            pdfs,
            results,
            case_details_html,
            term_found_in_regular_cause_list,
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


def send_email(
    emailer: Emailer,
    email_list: List[str],
    search_terms: str,
    date: str,
    pdfs: List[Dict[str, str]],
    results: List[Dict[str, Any]],
    case_details_html: Optional[str] = None,
    term_found_in_regular_cause_list: Optional[str] = None,
) -> None:
    context = {
        "search_terms": search_terms,
        "date": date,
        "results": results,
        "pdfs": pdfs,
        "case_details_html": case_details_html,
        "term_found_in_regular_cause_list": term_found_in_regular_cause_list,
        "urls": {
            "cl_base_url": settings.CL_BASE_URL,
            "case_search_url": settings.CASE_SEARCH_URL,
            "cl_judge_wise_regular_url": settings.CL_JUDGE_WISE_REGULAR_URL,
        },
    }
    try:
        emailer.send_email(
            recipients=email_list,
            subject=f"Cause List Search Results for {search_terms} on {date}",
            template_name="cause_list_template.html",
            context=context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending email: {e}")
