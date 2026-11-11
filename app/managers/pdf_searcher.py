import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Dict, List, Optional

import fitz
import requests

from app.config import REQUEST_HEADERS
from app.managers.cause_list_entries import find_entries
from app.utils.http_debug import describe_failed_response


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
            response = requests.get(pdf_url, headers=REQUEST_HEADERS, timeout=(10, 30))

            if response.status_code != 200:
                print(
                    f"Failed to fetch PDF {pdf_name}: HTTP {response.status_code}\n"
                    f"{describe_failed_response(response)}",
                    flush=True,
                )
                pdf["error"] = f"HTTP {response.status_code}"
                return None

            invalid_reason = self._invalid_pdf_reason(response)
            if invalid_reason:
                print(
                    f"Downloaded file for {pdf_name} is not a usable PDF: {invalid_reason}\n"
                    f"{describe_failed_response(response)}",
                    flush=True,
                )
                pdf["error"] = invalid_reason
                return None

            num_pages = 0
            page_texts: List[str] = []
            # Read the PDF from memory
            try:
                with BytesIO(response.content) as pdf_file:
                    with fitz.open(stream=pdf_file.read(), filetype="pdf") as document:
                        num_pages = len(document)
                        for page_num in range(num_pages):
                            try:
                                page_texts.append(
                                    document.load_page(page_num).get_text()
                                )
                            except Exception as page_error:
                                print(
                                    f"Error reading page {page_num + 1} of PDF {pdf_name}: {page_error}",
                                    flush=True,
                                )
                                page_texts.append("")  # keep page numbers aligned
                        # Must stay inside `with`: positions are read lazily.
                        found_pages, matches = find_entries(
                            page_texts,
                            self.search_terms,
                            lambda page_no: self._line_x(document, page_no),
                        )

                response.close()
                pages_with_text = sum(1 for text in page_texts if text.strip())

                if num_pages == 0 or pages_with_text == 0:
                    reason = (
                        "PDF has no pages"
                        if num_pages == 0
                        else f"no searchable text in {num_pages} pages (scanned?)"
                    )
                    print(f"Cannot search {pdf_name}: {reason}", flush=True)
                    pdf["error"] = reason
                    return None

                pdf["num_pages"] = num_pages
                print(
                    f"PDF OK {pdf_name} [{pdf.get('source', '')}]: "
                    f"{len(response.content)} bytes, {num_pages} pages, "
                    f"{pages_with_text} with text",
                    flush=True,
                )

                if any(found_pages.values()):
                    return {
                        "pdf_name": pdf_name,
                        "pdf_url": pdf_url,
                        "source": pdf.get("source", ""),
                        "found_pages": found_pages,
                        "matches": matches,
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
                pdf["error"] = f"could not parse PDF ({pdf_error.__class__.__name__})"
                return None
        except requests.exceptions.RequestException as e:
            print(
                f"Error fetching PDF {pdf_name} from {pdf_url}: {e}",
                flush=True,
            )
            pdf["error"] = f"download failed ({e.__class__.__name__})"
            return None
        except Exception as e:
            print(
                f"Unexpected error processing PDF {pdf_name}: {e}",
                flush=True,
            )
            pdf["error"] = f"unexpected error ({e.__class__.__name__})"
            return None

    @staticmethod
    def _line_x(document: Any, page_no: int) -> List[float]:
        # Same flags as get_text(), or lines stop lining up with the text.
        try:
            blocks = document.load_page(page_no - 1).get_text(
                "dict", flags=fitz.TEXTFLAGS_TEXT
            )["blocks"]
        except Exception:
            return []
        return [
            line["bbox"][0]
            for block in blocks
            for line in block.get("lines", [])
            if "".join(span["text"] for span in line["spans"]).strip()
        ]

    @staticmethod
    def _invalid_pdf_reason(response: requests.Response) -> Optional[str]:
        """Return why a 200 response isn't a PDF (e.g. an HTML error page), else None."""
        content = response.content or b""
        if not content:
            return "empty response"
        if not content.lstrip()[:5] == b"%PDF-":
            content_type = response.headers.get("Content-Type", "unknown")
            return f"not a PDF (Content-Type: {content_type})"
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
