from fastapi import FastAPI
from app.scraper import Scraper  # Correct import
from app.pdf_searcher import PDFSearcher
from app.emailer import Emailer
import os

app = FastAPI()


@app.get("/init")
async def init_scraper():
    base_url = os.getenv("BASE_URL")
    search_term = os.getenv("SEARCH_TERM")
    recipient_emails = os.getenv("RECIPIENT_EMAILS").split(",")

    scraper = Scraper(base_url)
    pdf_searcher = PDFSearcher()
    emailer = Emailer()

    pdf_links = scraper.get_pdf_links()
    results = {}
    for entry in pdf_links:
        if pdf_searcher.search_in_pdf(entry["url"], search_term):
            key = f"{entry['date']}+{entry['type']}+{entry['main_sup']}"
            results[key] = entry["url"]

    if results:
        emailer.send_email(results, recipient_emails)
        return {
            "message": "Scraper ran successfully, results emailed.",
            "results": results,
        }
    else:
        return {"message": "No matches found."}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
