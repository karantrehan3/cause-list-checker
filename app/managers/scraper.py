"""Facade used by the Lambda handler and the FastAPI routes."""

from typing import Dict, List, Optional

from app.managers.case_lookup import CaseLookup, CaseLookupResult
from app.managers.cause_list_sources import CauseListFetcher, CauseListResult
from app.managers.court_http import CourtHttpClient
from app.managers.phhc_api import PhhcApi


class Scraper:
    def __init__(self, client: Optional[CourtHttpClient] = None):
        client = client or CourtHttpClient()
        api = PhhcApi(client)
        self.cause_list_fetcher = CauseListFetcher(client, api)
        self.case_lookup = CaseLookup(api)

    def fetch_cause_lists(self, date: str, search_terms: List[str]) -> CauseListResult:
        """Cause list PDFs from both sites. Raises CourtSiteError only if both fail."""
        return self.cause_list_fetcher.fetch(date, search_terms)

    def lookup_case(
        self, case_details: Optional[Dict[str, str]], search_terms: List[str], date: str
    ) -> Optional[CaseLookupResult]:
        """Case status + judge-wise lists; None when no case number was given."""
        if not case_details:
            return None
        return self.case_lookup.run(case_details, search_terms, date)
