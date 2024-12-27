import PyPDF2
import requests
from io import BytesIO


class PDFSearcher:
    def __init__(self, search_term: str):
        self.search_term = search_term

    def search_pdf(self, pdf_url: str) -> bool:
        # Fetch the PDF content
        response = requests.get(pdf_url)
        if response.status_code != 200:
            return False

        # Read the PDF from memory
        pdf_file = BytesIO(response.content)
        reader = PyPDF2.PdfReader(pdf_file)

        # Search for the term in each page
        for page in reader.pages:
            text = page.extract_text()
            if text and self.search_term.lower() in text.lower():
                return True

        return False
