from fastapi import HTTPException
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any, Optional
from app.managers.scraper import Scraper
from app.managers.pdf_searcher import PDFSearcher
from app.services.emailer import Emailer
from app.utils.error_handler import ErrorHandler
from app.config import settings


async def scrape_search_and_notify(
    search_term: str,
    date: Optional[str] = None,
    recipient_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not recipient_emails:
        recipient_emails = settings.EMAIL_RECIPIENTS.split(",")

    if not date:
        date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    scraper = Scraper()
    searcher = PDFSearcher(search_term=search_term)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, recipient_emails)

    try:
        # Step 1: Scrape the page and get PDF links
        pdfs = scraper.parse_table_and_download_pdfs(date)
        if not pdfs:
            send_email(emailer, recipient_emails, search_term, date, pdfs, [])
            return {"message": "No Cause Lists found"}

        # Step 2: Search for the term in the PDFs
        results = searcher.search_pdf(pdfs)

        print("Cause List Search Results: ", json.dumps(results, indent=4))

        # Step 3: If results found, send an email notification
        send_email(emailer, recipient_emails, search_term, date, pdfs, results)

        return {"message": "Search completed and email sent!", "results": results}

    except Exception as e:
        error_message, stack_trace = error_handler.handle_exception(
            e, {"search_term": search_term, "date": date}
        )
        raise HTTPException(status_code=500, detail=error_message)


def send_email(
    emailer: Emailer,
    email_list: List[str],
    search_term: str,
    date: str,
    pdfs: List[Dict[str, str]],
    results: List[Dict[str, Any]],
) -> None:
    context = {
        "search_term": search_term,
        "date": date,
        "results": results,
        "pdfs": pdfs,
    }
    try:
        emailer.send_email(
            recipients=email_list,
            subject=f"Cause List Search Results for '{search_term}' on {date}",
            template_name="cause_list_template.html",
            context=context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending email: {e}")
