"""Client for the new.phhc.gov.in JSON API (livedb9010.phhc.gov.in).

Every method raises CourtSiteError when the request fails, so callers decide
whether a failure is fatal or should be reported as an incomplete check.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from requests.cookies import RequestsCookieJar

from app.clients.court_http import SLOW_TIMEOUT, CourtHttpClient, CourtSiteError
from app.config import API_REQUEST_HEADERS, settings


def to_api_date(date: str) -> str:
    """'05/11/2026' -> '2026-11-05'."""
    return datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")


class PhhcApi:
    def __init__(
        self,
        client: Optional[CourtHttpClient] = None,
        base_url: Optional[str] = None,
    ):
        self.client = client or CourtHttpClient()
        self.base_url = base_url or settings.PHHC_API_BASE_URL
        self.cookies = RequestsCookieJar()  # the API's own cookies, kept per run

    def _get(
        self, endpoint: str, params: Optional[Dict[str, str]] = None, **kwargs: Any
    ) -> Any:
        return self.client.get_json(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=API_REQUEST_HEADERS,
            cookie_jar=self.cookies,
            **kwargs,
        )

    @staticmethod
    def _case_params(case_type: str, case_no: str, case_year: str) -> Dict[str, str]:
        return {"case_type": case_type, "case_no": case_no, "case_year": case_year}

    # --- Case status -------------------------------------------------------

    def case_info(self, case_type: str, case_no: str, case_year: str) -> Dict:
        data = self._get(
            "/cis_filing/public/getCase",
            self._case_params(case_type, case_no, case_year),
        )
        if not data or not isinstance(data, dict):
            raise CourtSiteError("case not found")
        return data

    def listing_history(
        self, case_type: str, case_no: str, case_year: str
    ) -> List[Dict]:
        data = self._get(
            "/case_listing_detail/public/search",
            self._case_params(case_type, case_no, case_year),
        )
        if isinstance(data, dict):  # API returns {"data": [...]}
            data = data.get("data")
        return data or []

    def related_cases(self, case_type: str, case_no: str, case_year: str) -> List[Dict]:
        params = {**self._case_params(case_type, case_no, case_year), "limit": "100"}
        return self._get("/cis_filing/public/relatedCases", params) or []

    def judgments(self, case_type: str, case_no: str, case_year: str) -> List[Dict]:
        return (
            self._get(
                f"/cis_filing/public/judgmentDetails/{case_no}/{case_year}/{case_type}",
                {"skip": "0", "limit": "1000"},
            )
            or []
        )

    def copy_petitions(self, case_type: str, case_no: str, case_year: str) -> Dict:
        return (
            self._get(
                "/HC-Copying-Applications-Case-Details-Public/",
                self._case_params(case_type, case_no, case_year),
            )
            or {}
        )

    def impugned_orders(self, case_type: str, case_no: str, case_year: str) -> Dict:
        return (
            self._get(
                "/cis_filing/public/getImpugnedOrderDetails",
                self._case_params(case_type, case_no, case_year),
            )
            or {}
        )

    # --- Judges & judge-wise cause lists ------------------------------------

    def active_judges(self) -> List[Dict]:
        return self._get("/cis/judges/active-bench") or []

    def daily_cause_list(self, judge_code: int, date: str) -> Any:
        """Raw getCauseList response (what the 'Judge wise causelist' page uses)."""
        return self._get(
            "/cis_filing/public/getCauseList",
            {"bench_judge_id": str(judge_code), "cause_list_date": to_api_date(date)},
            timeout=SLOW_TIMEOUT,
        )

    def latest_regular_list_date(self) -> str:
        """Date of the most recent regular cause list, as DD/MM/YYYY."""
        data = self._get("/cis_filing/public/get-latest-regular-causelist-date")
        raw = str((data or {}).get("cl_date", ""))[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError as e:
            raise CourtSiteError("no latest regular cause list date") from e

    def regular_cause_list(self, judge_code: int, date: str) -> Any:
        """Raw getRegularCauseList response."""
        return self._get(
            "/cis_filing/public/getRegularCauseList",
            {"bench_judge_id": str(judge_code), "cause_list_date": to_api_date(date)},
            timeout=SLOW_TIMEOUT,
        )

    # --- Daily cause list PDFs ----------------------------------------------

    def daily_pdf_list(self, date: str) -> List[Dict]:
        data = self._get(
            "/public/daily-causelist-pdf/list", {"cl_date": to_api_date(date)}
        )
        if not isinstance(data, list):
            raise CourtSiteError("unexpected daily-causelist-pdf response")
        return data

    def daily_pdf_list_types(self) -> List[Dict]:
        return self._get("/public/daily-causelist-pdf/list-types") or []

    def daily_pdf_url(self, date: str, list_code: str, main_suppl: str) -> str:
        return f"{self.base_url}/public/daily-causelist-pdf/{to_api_date(date)}/{list_code}/{main_suppl}"
