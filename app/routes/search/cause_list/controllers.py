import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.config import settings
from app.managers.pdf_searcher import PDFSearcher
from app.managers.scraper import Scraper
from app.services.emailer import Emailer
from app.utils.error_handler import ErrorHandler

search_lock = asyncio.Lock()


async def scrape_search_and_notify(
    search_terms: List[str],
    date: Optional[str] = None,
    recipient_emails: Optional[List[str]] = None,
    case_details: Dict[str, str] = None,
) -> Dict[str, Any]:
    if search_lock.locked():
        raise HTTPException(status_code=429, detail="Too Many Requests")

    if not recipient_emails:
        recipient_emails = settings.EMAIL_RECIPIENTS.split(",")

    if not date:
        date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    async def process_search_and_notify():
        scraper = Scraper()
        searcher = PDFSearcher(search_terms=search_terms)
        emailer = Emailer()
        error_handler = ErrorHandler(emailer, recipient_emails)

        async with search_lock:
            try:
                # Step 1 & 2: Scrape the page and get PDF links & Case details in parallel
                pdfs, result = await asyncio.gather(
                    asyncio.to_thread(scraper.parse_table_and_download_pdfs, date),
                    asyncio.to_thread(
                        scraper.get_case_details_and_judge_details,
                        case_details,
                        search_terms,
                        date,
                    ),
                )

                case_details_html, term_found_in_regular_cause_list = (
                    result if result is not None else (None, "")
                )

                if not pdfs:
                    send_email(
                        emailer,
                        recipient_emails,
                        search_terms,
                        date,
                        pdfs,
                        [],
                        case_details_html,
                        term_found_in_regular_cause_list,
                    )
                    print("ALERT! No Cause Lists found", flush=True)
                    return

                print(
                    "PROGRESS! Cause Lists found: ",
                    json.dumps(pdfs, indent=2),
                    flush=True,
                )

                # Step 3: Search for the terms in the PDFs (run in separate thread)
                results = await asyncio.to_thread(searcher.search_pdf, pdfs)

                print(
                    "PROGRESS! Cause List Search Results: ",
                    json.dumps(results, indent=2),
                    flush=True,
                )

                # Step 4: If results found, send an email notification
                send_email(
                    emailer,
                    recipient_emails,
                    search_terms,
                    date,
                    pdfs,
                    results,
                    case_details_html,
                    term_found_in_regular_cause_list,
                )

                print(
                    "SUCCESS! Search completed and email sent! ",
                    json.dumps(results, indent=2),
                    flush=True,
                )
                return

            except Exception as e:
                error_message, stack_trace = error_handler.handle_exception(
                    e, {"search_terms": search_terms, "date": date}
                )
                raise HTTPException(status_code=500, detail=error_message)

    asyncio.create_task(process_search_and_notify())
    return {"message": "Search and notification process started"}


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
