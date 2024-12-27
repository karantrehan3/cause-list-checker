import PyPDF2
import requests
from io import BytesIO
import time
import random
from typing import List, Dict


class PDFSearcher:
    def __init__(self, search_term: str):
        self.search_term = search_term

    def search_pdf(self, pdfs: List[Dict[str, str]]) -> List[Dict[str, any]]:
        results = []
        for pdf in pdfs:
            # Add a random delay between 0.5 and 1 seconds
            time.sleep(random.uniform(0.5, 1))

            pdf_name = pdf["pdf_name"]
            pdf_url = pdf["pdf_url"]

            # Fetch the PDF content
            response = requests.get(pdf_url)

            # Log the headers of the response
            if response.status_code != 200:
                continue

            # Read the PDF from memory
            pdf_file = BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_file)

            # Search for the term in each page
            found_pages = []
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and self.search_term.lower() in text.lower():
                    found_pages.append(page_num + 1)  # Page numbers are 1-based

            if found_pages:
                results.append(
                    {"pdf_name": pdf_name, "pdf_url": pdf_url, "page_nums": found_pages}
                )

        return results
