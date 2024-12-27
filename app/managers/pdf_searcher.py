import fitz
import requests
import time
import random
from io import BytesIO
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed


class PDFSearcher:
    def __init__(self, search_term: str) -> None:
        self.search_term = search_term

    def fetch_and_search_pdf(self, pdf: Dict[str, str]) -> Optional[Dict[str, Any]]:
        # Add a random delay between 0.5 and 1 seconds
        time.sleep(random.uniform(0.5, 1))

        pdf_name = pdf["pdf_name"]
        pdf_url = pdf["pdf_url"]

        # Fetch the PDF content
        response = requests.get(pdf_url)

        # Log the headers of the response
        if response.status_code != 200:
            return None

        found_pages = []
        # Read the PDF from memory
        with BytesIO(response.content) as pdf_file:
            document = fitz.open(stream=pdf_file.read(), filetype="pdf")

            # Search for the term in each page
            for page_num in range(len(document)):
                page = document.load_page(page_num)
                text = page.get_text()
                if text and self.search_term.lower() in text.lower():
                    found_pages.append(page_num + 1)  # Page numbers are 1-based
            
            document.close()

        response.close()

        if found_pages:
            return {"pdf_name": pdf_name, "pdf_url": pdf_url, "page_nums": found_pages}
        return None

    def search_pdf(self, pdfs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_pdf = {
                executor.submit(self.fetch_and_search_pdf, pdf): pdf for pdf in pdfs
            }
            for future in as_completed(future_to_pdf):
                result = future.result()
                if result:
                    results.append(result)
                del future_to_pdf[future]
        return results
