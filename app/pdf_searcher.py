import PyPDF2
import requests
from io import BytesIO
from typing import List, Tuple


class PDFSearcher:
    def __init__(self, search_term: str):
        self.search_term = search_term

    def search_pdf(self, pdf_url: str) -> Tuple[bool, List[int]]:
        # Fetch the PDF content
        response = requests.get(pdf_url)

        # Log the headers of the response
        if response.status_code != 200:
            return False, []

        # Read the PDF from memory
        pdf_file = BytesIO(response.content)
        reader = PyPDF2.PdfReader(pdf_file)

        # Search for the term in each page
        found_pages = []
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and self.search_term.lower() in text.lower():
                found_pages.append(page_num + 1)  # Page numbers are 1-based

        return bool(found_pages), found_pages