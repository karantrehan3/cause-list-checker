import requests
from io import BytesIO
from PyPDF2 import PdfReader


class PDFSearcher:
    def search_in_pdf(self, pdf_url: str, search_term: str) -> bool:
        response = requests.get(pdf_url)
        response.raise_for_status()
        pdf_file = BytesIO(response.content)

        reader = PdfReader(pdf_file)
        for page in reader.pages:
            if search_term in page.extract_text():
                return True
        return False
