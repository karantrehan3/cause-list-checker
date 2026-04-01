import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Dict, List, Optional

import fitz
import requests


class PDFSearcher:
    def __init__(self, search_terms: List[str]) -> None:
        self.search_terms = search_terms

    def fetch_and_search_pdf(self, pdf: Dict[str, str]) -> Optional[Dict[str, Any]]:
        # Add a random delay between 0.5 and 1 seconds
        time.sleep(random.uniform(0.5, 1))

        pdf_name = pdf["pdf_name"]
        pdf_url = pdf["pdf_url"]

        try:
            # Fetch the PDF content with timeout
            response = requests.get(pdf_url, timeout=(10, 30))

            # Log the headers of the response
            if response.status_code != 200:
                print(
                    f"Failed to fetch PDF {pdf_name}: HTTP {response.status_code}",
                    flush=True,
                )
                return None

            found_pages = {term: [] for term in self.search_terms}
            num_pages = 0
            # Read the PDF from memory
            try:
                with BytesIO(response.content) as pdf_file:
                    with fitz.open(stream=pdf_file.read(), filetype="pdf") as document:
                        num_pages = len(document)
                        # Search for the terms in each page
                        for page_num in range(num_pages):
                            try:
                                page = document.load_page(page_num)
                                text = page.get_text()
                                if text:
                                    for term in self.search_terms:
                                        if term.lower() in text.lower():
                                            found_pages[term].append(
                                                page_num + 1
                                            )  # Page numbers are 1-based
                            except Exception as page_error:
                                print(
                                    f"Error reading page {page_num + 1} of PDF {pdf_name}: {page_error}",
                                    flush=True,
                                )
                                continue

                response.close()

                pdf["num_pages"] = num_pages

                if any(found_pages.values()):
                    return {
                        "pdf_name": pdf_name,
                        "pdf_url": pdf_url,
                        "found_pages": found_pages,
                        "num_pages": num_pages,
                    }
                else:
                    # Log when no terms found for debugging
                    print(
                        f"No search terms found in PDF {pdf_name} (searched {num_pages} pages, terms: {self.search_terms})",
                        flush=True,
                    )
                return None
            except Exception as pdf_error:
                print(
                    f"Error parsing PDF {pdf_name}: {pdf_error}",
                    flush=True,
                )
                return None
        except requests.exceptions.RequestException as e:
            print(
                f"Error fetching PDF {pdf_name} from {pdf_url}: {e}",
                flush=True,
            )
            return None
        except Exception as e:
            print(
                f"Unexpected error processing PDF {pdf_name}: {e}",
                flush=True,
            )
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
