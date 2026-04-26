"""
PDF Tracker Manager

Tracks existing PDFs and identifies new ones. Uses in-memory storage for
Docker (long-lived process) and SSM Parameter Store for Lambda (stateless).
Automatically resets when the physical date changes.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple

IST = timezone(timedelta(hours=5, minutes=30))
SSM_PARAM_NAME = "/cause-list-checker/pdf-tracker"


class PDFTracker:
    def __init__(self):
        self._existing_pdfs: Set[str] = set()
        self._current_physical_date: str = ""
        self._use_ssm = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
        self._ssm_client = None

    def _get_ssm_client(self):
        if self._ssm_client is None:
            import boto3

            self._ssm_client = boto3.client("ssm")
        return self._ssm_client

    def _load_from_ssm(self) -> None:
        try:
            client = self._get_ssm_client()
            response = client.get_parameter(Name=SSM_PARAM_NAME)
            data = json.loads(response["Parameter"]["Value"])
            stored_date = data.get("date", "")
            current_date = datetime.now(IST).strftime("%d/%m/%Y")
            if stored_date == current_date:
                self._existing_pdfs = set(data.get("pdfs", []))
                self._current_physical_date = stored_date
            else:
                print(
                    f"PDF Tracker: SSM date mismatch ({stored_date} -> {current_date}). Starting fresh.",
                    flush=True,
                )
                self._existing_pdfs = set()
                self._current_physical_date = current_date
        except Exception as e:
            if "ParameterNotFound" in str(
                type(e).__name__
            ) or "ParameterNotFound" in str(e):
                print(
                    "PDF Tracker: No SSM parameter found. Starting fresh.", flush=True
                )
            else:
                print(
                    f"PDF Tracker: Error reading SSM: {e}. Falling back to empty.",
                    flush=True,
                )
            self._existing_pdfs = set()
            self._current_physical_date = datetime.now(IST).strftime("%d/%m/%Y")

    def _save_to_ssm(self) -> None:
        try:
            client = self._get_ssm_client()
            data = json.dumps(
                {
                    "date": self._current_physical_date,
                    "pdfs": list(self._existing_pdfs),
                }
            )
            client.put_parameter(
                Name=SSM_PARAM_NAME,
                Value=data,
                Type="String",
                Overwrite=True,
            )
        except Exception as e:
            print(f"PDF Tracker: Error writing SSM: {e}", flush=True)

    def _create_pdf_identifier(
        self, pdf_name: str, pdf_url: str, search_terms: List[str]
    ) -> str:
        search_terms_str = ",".join(sorted(search_terms))
        full_id = f"{search_terms_str}|||{pdf_name}|||{pdf_url}"
        if self._use_ssm:
            return hashlib.md5(full_id.encode()).hexdigest()[:8]
        return full_id

    def _check_and_clear_if_new_physical_day(self) -> None:
        current_physical_date = datetime.now(IST).strftime("%d/%m/%Y")

        if self._current_physical_date != current_physical_date:
            if self._current_physical_date:
                print(
                    f"PDF Tracker: New physical day detected ({self._current_physical_date} -> {current_physical_date}). Clearing memory.",
                    flush=True,
                )
            self._existing_pdfs.clear()
            self._current_physical_date = current_physical_date

    def separate_existing_and_new_pdfs(
        self, pdfs: List[Dict[str, str]], search_terms: List[str]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        if self._use_ssm:
            self._load_from_ssm()
        else:
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
                self._existing_pdfs.add(identifier)

        if self._use_ssm:
            self._save_to_ssm()

        return existing_pdfs, new_pdfs

    def clear_existing_pdfs(self) -> None:
        self._existing_pdfs.clear()
        self._current_physical_date = ""


pdf_tracker = PDFTracker()
