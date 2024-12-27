from fastapi import FastAPI, HTTPException
from app.scraper import Scraper
from app.pdf_searcher import PDFSearcher
from app.emailer import Emailer
from typing import List, Optional
from datetime import datetime
import os
import json
import time
import random

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
        pdf_links = scraper.parse_table_and_download_pdfs(date)

        # Step 2: Search for the term in the PDFs
        results = []
        for pdf_name, pdf_url in pdf_links.items():
            # Add a random delay between 3 and 5 seconds
            time.sleep(random.uniform(0.5, 1))

            try:
                found, page_nums = searcher.search_pdf(pdf_url)
                if found:
                    results.append(
                        {
                            "pdf_name": pdf_name,
                            "pdf_url": pdf_url,
                            "page_nums": page_nums,
                        }
                    )
            except Exception as e:
                print(f"Error searching PDF {pdf_name}: {e}")

        print(json.dumps(results, indent=4))

        # Step 3: If results found, send an email notification
        if results:
            body = "\n".join(
                [
                    f'<a href="{result["pdf_url"]}">{result["pdf_name"]}</a>: Found on pages {", ".join(map(str, result["page_nums"]))}'
                    for result in results
                ]
            )
            try:
                emailer.send_email(
                    recipients=email_list,
                    subject="Cause List Search Results",
                    body=body,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error sending email: {e}")

            return {"message": "Search completed and email sent!", "results": results}
        else:
            return {"message": "No matching PDFs found for the search term."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
