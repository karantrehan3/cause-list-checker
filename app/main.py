from fastapi import FastAPI, HTTPException
from app.scraper import Scraper
from app.pdf_searcher import PDFSearcher
from app.emailer import Emailer
from app.error_handler import ErrorHandler
from typing import List, Optional
from datetime import datetime
import os
import json

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/search/cause-list")
async def init_scraping_and_notification(search_term: str, date: Optional[str] = None):
    # Initialize the components
    scraper = Scraper()
    searcher = PDFSearcher(search_term=search_term)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, os.getenv("EMAIL_RECIPIENTS").split(","))

    # Validate and set the date
    if date:
        try:
            datetime.strptime(date, "%d/%m/%Y")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use DD/MM/YYYY."
            )
    else:
        date = datetime.now().strftime("%d/%m/%Y")

    # Get email recipients from environment variables
    email_list = os.getenv("EMAIL_RECIPIENTS").split(",")

    try:
        # Step 1: Scrape the page and get PDF links
        pdfs = scraper.parse_table_and_download_pdfs(date)

        # Step 2: Search for the term in the PDFs
        results = searcher.search_pdf(pdfs)

        print(json.dumps(results, indent=4))

        # Step 3: If results found, send an email notification
        context = {
            "search_term": search_term,
            "date": date,
            "results": results,
            "pdfs": pdfs,
        }
        try:
            emailer.send_email(
                recipients=email_list,
                subject=f"Cause List Search Results for '{search_term}' on { date }",
                template_name="cause_list_template.html",
                context=context,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error sending email: {e}")

        return {"message": "Search completed and email sent!", "results": results}

    except Exception as e:
        error_message, stack_trace = error_handler.handle_exception(
            e, {"search_term": search_term, "date": date}
        )
        raise HTTPException(status_code=500, detail=error_message)
