"""
PDF Tracker Manager

This module provides functionality to track existing PDFs and identify new ones.
It maintains an in-memory set of PDF identifiers (pdf_name + pdf_url combination)
to distinguish between existing and new PDFs.
"""

from datetime import datetime
from typing import Dict, List, Set, Tuple


class PDFTracker:
    """
    Manages tracking of existing PDFs to identify new ones.

    Uses an in-memory set to store PDF identifiers and provides methods
    to separate existing vs new PDFs.
    """

    def __init__(self):
        # Set to store existing PDF identifiers (pdf_name + pdf_url + search_terms)
        self._existing_pdfs: Set[str] = set()
        # Track the current physical date to detect day changes
        self._current_physical_date: str = ""

    def _create_pdf_identifier(
        self, pdf_name: str, pdf_url: str, search_terms: List[str]
    ) -> str:
        """
        Create a unique identifier for a PDF based on name, URL, and search terms.

        Args:
            pdf_name: Name of the PDF
            pdf_url: URL of the PDF
            search_terms: List of search terms used

        Returns:
            Unique identifier string
        """
        search_terms_str = ",".join(sorted(search_terms))  # Sort for consistency
        return f"{search_terms_str}|||{pdf_name}|||{pdf_url}"

    def _check_and_clear_if_new_physical_day(self) -> None:
        """
        Check if the physical date has changed and clear memory if it's a new day.
        Uses the current machine date instead of the date parameter.
        """
        current_physical_date = datetime.now().strftime("%d/%m/%Y")

        if self._current_physical_date != current_physical_date:
            if self._current_physical_date:  # Only log if we had a previous date
                print(
                    f"PDF Tracker: New physical day detected ({self._current_physical_date} -> {current_physical_date}). Clearing memory.",
                    flush=True,
                )
            self._existing_pdfs.clear()
            self._current_physical_date = current_physical_date

    def separate_existing_and_new_pdfs(
        self, pdfs: List[Dict[str, str]], search_terms: List[str]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Separate PDFs into existing and new lists.

        Args:
            pdfs: List of PDF dictionaries with 'pdf_name' and 'pdf_url' keys
            search_terms: List of search terms used

        Returns:
            Tuple of (existing_pdfs, new_pdfs)
        """
        # Check if we need to clear memory for a new physical day
        self._check_and_clear_if_new_physical_day()

        existing_pdfs = []
        new_pdfs = []

        for pdf in pdfs:
            identifier = self._create_pdf_identifier(
                pdf["pdf_name"], pdf["pdf_url"], search_terms
            )

            if identifier in self._existing_pdfs:
                existing_pdfs.append(pdf)
            else:
                new_pdfs.append(pdf)
                # Add to existing set for future runs
                self._existing_pdfs.add(identifier)

        return existing_pdfs, new_pdfs

    def clear_existing_pdfs(self) -> None:
        """
        Clear all existing PDFs from memory.
        """
        self._existing_pdfs.clear()
        self._current_physical_date = ""


# Global instance for the application
pdf_tracker = PDFTracker()
