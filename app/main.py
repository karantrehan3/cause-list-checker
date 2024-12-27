from fastapi import FastAPI, HTTPException
from app.scraper import Scraper
from app.pdf_searcher import PDFSearcher
from app.emailer import Emailer
from typing import List
from datetime import datetime
import os

app = FastAPI()


@app.post("/init")
async def init_scraping_and_notification(search_term: str):
    # Initialize the components
    scraper = Scraper()
    searcher = PDFSearcher(search_term=search_term)
    emailer = Emailer()

    # Get today's date in DD/MM/YYYY format
    date = datetime.now().strftime("%d/%m/%Y")

    # Get email recipients from environment variables
    email_list = os.getenv("EMAIL_RECIPIENTS").split(",")

    try:
        # Step 1: Scrape the page and get PDF links
        pdf_links = scraper.parse_table_and_download_pdfs(date)

        print("LOGGING PDF LINKS: ", pdf_links)

        # Step 2: Search for the term in the PDFs
        results = {}
        for pdf_url in pdf_links:
            if searcher.search_pdf(pdf_url):
                list_name = f"{date}-all"
                results[list_name] = pdf_url

        # Step 3: If results found, send an email notification
        if results:
            body = "\n".join([f"{key}: {value}" for key, value in results.items()])
            emailer.send_email(
                recipients=email_list, subject="Cause List Search Results", body=body
            )
            return {"message": "Search completed and email sent!", "results": results}
        else:
            return {"message": "No matching PDFs found for the search term."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint (optional)
@app.get("/health")
async def health_check():
    return {"status": "ok"}
