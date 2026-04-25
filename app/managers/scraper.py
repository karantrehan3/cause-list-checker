import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import certifi
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.exceptions import IncompleteRead
from urllib3.util.retry import Retry

from app.config import settings
from app.managers.pdf_tracker import pdf_tracker


class Scraper:
    def __init__(self):
        self.cl_base_url = settings.CL_BASE_URL
        self.cl_form_action_url = settings.CL_FORM_ACTION_URL
        self.phhc_api_base_url = settings.PHHC_API_BASE_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _create_session(self) -> requests.Session:
        """Create a new session with retry logic and SSL verification"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount("https://", adapter)
        session.verify = certifi.where()
        return session

    def _make_request(
        self, method: str, url: str, max_retries: int = 3, **kwargs
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with error handling and session management.

        Args:
            method: HTTP method ('GET' or 'POST')
            url: URL to request
            max_retries: Maximum number of retry attempts for connection errors
            **kwargs: Additional arguments for requests

        Returns:
            Response object if successful, None if failed
        """
        if "timeout" not in kwargs:
            kwargs["timeout"] = (10, 30)

        for attempt in range(max_retries):
            try:
                with self._create_session() as session:
                    if method.upper() == "GET":
                        response = session.get(url, stream=False, **kwargs)
                    elif method.upper() == "POST":
                        response = session.post(url, stream=False, **kwargs)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    response.raise_for_status()
                    return response
            except (IncompleteRead, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(
                        f"Connection error on attempt {attempt + 1}/{max_retries} for {method} {url}: {e}. Retrying in {wait_time}s...",
                        flush=True,
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    print(
                        f"Error making {method} request to {url} after {max_retries} attempts: {e}",
                        flush=True,
                    )
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Error making {method} request to {url}: {e}", flush=True)
                return None

        return None

    # -------------------------------------------------------------------------
    # Step 1: PDF scraping from highcourtchd.gov.in (unchanged)
    # -------------------------------------------------------------------------

    def submit_view_cl_form(self, date: str) -> str:
        form_data = {
            "t_f_date": date,
            "urg_ord": "1",
            "action": "show_causeList",
        }

        response = self._make_request(
            "POST", self.cl_form_action_url, data=form_data, headers=self.headers
        )
        if response is None:
            raise requests.exceptions.RequestException("Failed to submit view CL form")
        return response.text

    def parse_table_and_download_pdfs(
        self, date: str, search_terms: List[str] = None
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Parse the cause list table and separate PDFs into existing and new.

        Args:
            date: The date for which to parse the cause list
            search_terms: List of search terms used (optional for backward compatibility)

        Returns:
            Tuple of (existing_pdfs, new_pdfs)
        """
        page_html = self.submit_view_cl_form(date)
        soup = BeautifulSoup(page_html, "html.parser")

        rows = soup.select("table#tables11 tr")
        pdfs = []

        for row in rows[2:]:
            cells = row.find_all("td")
            if len(cells) == 3:
                link = cells[0].find("a", href=True)
                list_type = cells[1].text.strip()
                main_sup = cells[2].text.strip()

                if link:
                    pdf_url = link["onclick"].split("'")[1]
                    pdf_url = urljoin(self.cl_base_url, pdf_url)
                    pdf_name = f"{list_type} | {main_sup}"
                    pdfs.append({"pdf_name": pdf_name, "pdf_url": pdf_url})

        if search_terms is None:
            search_terms = []
        existing_pdfs, new_pdfs = pdf_tracker.separate_existing_and_new_pdfs(
            pdfs, search_terms
        )

        return existing_pdfs, new_pdfs

    # -------------------------------------------------------------------------
    # Step 2: Case details & judge cause list via new phhc API
    # -------------------------------------------------------------------------

    def _api_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
        timeout: tuple = (10, 30),
    ) -> Optional[Any]:
        """
        Make a GET request to the PHHC API and return parsed JSON.

        Args:
            endpoint: API endpoint path (e.g., '/cis_filing/public/getCase')
            params: Query parameters
            timeout: (connect_timeout, read_timeout) tuple

        Returns:
            Parsed JSON (dict or list) if successful, None if failed
        """
        url = f"{self.phhc_api_base_url}{endpoint}"
        response = self._make_request(
            "GET", url, headers=self.headers, params=params, timeout=timeout
        )
        if response is None:
            return None
        try:
            return response.json()
        except ValueError as e:
            print(f"Error parsing JSON from {url}: {e}", flush=True)
            return None

    def _fetch_case_info(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[Dict]:
        """Fetch case details from the PHHC API."""
        data = self._api_get(
            "/cis_filing/public/getCase",
            params={"case_no": case_no, "case_type": case_type, "case_year": case_year},
        )
        if not data or isinstance(data, list):
            print(
                f"No case data found for {case_type}-{case_no}-{case_year}", flush=True
            )
            return None
        return data

    def _fetch_case_listing_history(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[List[Dict]]:
        """Fetch case listing history from the PHHC API."""
        data = self._api_get(
            "/case_listing_detail/public/search",
            params={"case_no": case_no, "case_year": case_year, "case_type": case_type},
        )
        if not data:
            return None
        # API returns {"data": [...]}
        if isinstance(data, dict):
            return data.get("data")
        return data

    def _fetch_active_judges(self) -> Optional[List[Dict]]:
        """Fetch list of active judges from the PHHC API."""
        return self._api_get("/cis/judges/active-bench")

    def _normalize_judge_name(self, name: str) -> str:
        """Strip HON'BLE prefix, court room suffix, and normalize whitespace."""
        name = re.sub(r"(?i)^HON'BLE\s+", "", name)
        name = re.sub(r"\s*\(Court Room No\.\s*\d+\)\s*$", "", name)
        return " ".join(name.split()).strip()

    def _match_judge_code(
        self, bench_name: str, active_judges: List[Dict]
    ) -> Optional[int]:
        """
        Match a bench name from case data to a judge_code from the active judges list.

        Args:
            bench_name: e.g. "HON'BLE MR. JUSTICE HARKESH MANUJA"
            active_judges: List from /cis/judges/active-bench

        Returns:
            judge_code (int) if found, None otherwise
        """
        cleaned = self._normalize_judge_name(bench_name).lower()
        if not cleaned:
            return None

        for judge in active_judges:
            judge_name = judge.get("judge_name", "")
            if cleaned == judge_name.lower():
                return judge.get("judge_code")

        # Fallback: substring match
        for judge in active_judges:
            judge_name = judge.get("judge_name", "").lower()
            if cleaned in judge_name or judge_name in cleaned:
                return judge.get("judge_code")

        print(f"Could not match judge code for bench '{bench_name}'", flush=True)
        return None

    def _fetch_regular_cause_list(
        self, judge_code: int, date: str
    ) -> Optional[List[Dict]]:
        """
        Fetch the regular cause list for a judge on a given date.

        Args:
            judge_code: The judge code from active-bench API
            date: Date in DD/MM/YYYY format (converted to YYYY-MM-DD for API)

        Returns:
            List of cause list entries, or None
        """
        try:
            dt = datetime.strptime(date, "%d/%m/%Y")
            api_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {date}", flush=True)
            return None

        return self._api_get(
            "/cis_filing/public/getRegularCauseList",
            params={"bench_judge_id": str(judge_code), "cause_list_date": api_date},
            timeout=(15, 90),  # Longer timeout — this endpoint can be slow
        )

    def _search_cause_list_entries(
        self, entries: List[Dict], search_terms: List[str]
    ) -> List[Dict]:
        """Filter cause list entries that contain any of the search terms."""
        matching = []
        for entry in entries:
            searchable = " ".join(
                str(entry.get(field, ""))
                for field in [
                    "pet_name",
                    "res_name",
                    "pet_adv_name",
                    "res_adv_name",
                    "case_type",
                    "case_no",
                    "case_year",
                ]
            ).lower()
            if any(term.lower() in searchable for term in search_terms):
                matching.append(entry)
        return matching

    def _format_api_date(self, date_str: Optional[str], fmt: str = "%d-%b-%Y") -> str:
        """Convert API datetime string like '2026-01-14T00:00:00' to display format."""
        if not date_str:
            return ""
        try:
            # Handle both date-only strings and datetime strings
            clean = str(date_str).replace("+05:30", "").split("T")[0]
            dt = datetime.strptime(clean, "%Y-%m-%d")
            return dt.strftime(fmt)
        except (ValueError, AttributeError):
            return str(date_str)

    def _fetch_related_cases(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[List[Dict]]:
        """Fetch related cases/miscellaneous applications."""
        return self._api_get(
            "/cis_filing/public/relatedCases",
            params={
                "case_type": case_type,
                "case_no": case_no,
                "case_year": case_year,
                "limit": "100",
            },
        )

    def _fetch_judgment_details(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[List[Dict]]:
        """Fetch judgment/order details for a case."""
        return self._api_get(
            f"/cis_filing/public/judgmentDetails/{case_no}/{case_year}/{case_type}",
            params={"skip": "0", "limit": "1000"},
        )

    def _fetch_copy_petition(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[Dict]:
        """Fetch copy petition details."""
        return self._api_get(
            "/HC-Copying-Applications-Case-Details-Public/",
            params={"case_no": case_no, "case_year": case_year, "case_type": case_type},
        )

    def _fetch_impugned_orders(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[Dict]:
        """Fetch impugned order details."""
        return self._api_get(
            "/cis_filing/public/getImpugnedOrderDetails",
            params={"case_no": case_no, "case_year": case_year, "case_type": case_type},
        )

    def _case_status_url(self, case_type: str, case_no: str, case_year) -> str:
        """Build a link to the case status page on the new PHHC site."""
        return f"https://new.phhc.gov.in/case-status/case-no?case_no={case_no}&case_type={case_type}&case_year={case_year}"

    def _case_link(self, case_type: str, case_no: str, case_year) -> str:
        """Build an <a> tag linking to the case status page."""
        label = f"{case_type}-{case_no}-{case_year}"
        url = self._case_status_url(case_type, case_no, case_year)
        return f'<a href="{url}">{label}</a>'

    def _build_case_details_html(
        self,
        case_data: Dict,
        listing_history: Optional[List[Dict]] = None,
        related_cases: Optional[List[Dict]] = None,
        judgments: Optional[List[Dict]] = None,
        copy_petition: Optional[Dict] = None,
        impugned_orders: Optional[Dict] = None,
    ) -> str:
        """
        Generate HTML for case details matching the new.phhc.gov.in layout.

        Sections:
        1. Case Details
        2. Related Cases/Miscellaneous Applications
        3. Case Listing Details
        4. Copy Petition Details
        5. Judgment Details
        6. Impugned Orders
        """
        # Style constants matching the dark navy theme from the site
        hdr = 'style="background-color: #1a2a4a; color: white; padding: 8px; text-align: center;"'
        sub_hdr = 'style="background-color: #2a3a5a; color: white; padding: 6px; text-align: center; font-weight: bold;"'
        lbl = 'style="font-weight: bold; padding: 8px; text-align: left; width: 22%;"'
        val = 'style="padding: 8px; text-align: left;"'
        tbl = 'border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 900px; border: 1px solid #ddd;"'
        hl = 'style="background-color: #ffff00; padding: 8px; text-align: left;"'

        case_type = case_data.get("case_type", "")
        case_no = case_data.get("case_no", "")
        case_year = case_data.get("case_year", "")

        # Build status string: "PENDING on 06-Aug-2025 by HON'BLE MR. JUSTICE ..."
        status_desc = (
            case_data.get("status", {}).get("status_desc", "")
            if isinstance(case_data.get("status"), dict)
            else ""
        )
        status_date = self._format_api_date(case_data.get("t_status_date"))
        bench_name = case_data.get("bench_name", "")
        status_full = status_desc
        if status_date:
            status_full += f" on {status_date}"
        if bench_name:
            status_full += f" by {bench_name}"

        reg_date = self._format_api_date(case_data.get("reg_date"))
        diary_no = case_data.get("case_diary_no", "")
        category = case_data.get("category", "")
        cat_desc = case_data.get("cat_desc", "")
        category_full = f"{category} {cat_desc}".strip() if category else cat_desc
        pet_name = case_data.get("pet_name", "").strip()
        res_name = case_data.get("res_name", "").strip()
        party_detail = (
            f"(O&M) {pet_name} Vs {res_name}"
            if pet_name and res_name
            else f"{pet_name} {res_name}".strip()
        )
        pet_adv = case_data.get("pet_adv_name", "") or ""
        pet_adv_enroll = case_data.get("pet_adv_enrollment_year", "") or ""
        if pet_adv and pet_adv_enroll:
            pet_adv = f"{pet_adv} ({pet_adv_enroll})"
        res_adv = case_data.get("res_adv_name", "") or ""
        res_adv_enroll = case_data.get("res_adv_enrollment_year", "") or ""
        if res_adv and res_adv_enroll:
            res_adv = f"{res_adv} ({res_adv_enroll})"
        elif not res_adv and res_adv_enroll:
            res_adv = f"({res_adv_enroll})"
        district = (
            case_data.get("district", {}).get("name", "")
            if isinstance(case_data.get("district"), dict)
            else ""
        )
        list_type = case_data.get("list_type", "")
        list_type_full = {"R": "REGULAR", "O": "ORDINARY", "U": "URGENT"}.get(
            list_type, list_type
        )
        final_order_date = self._format_api_date(
            case_data.get("final_order_date_uploaded_on")
        )

        # Final order link
        final_order_url = case_data.get("order", "")
        if final_order_url and not final_order_url.startswith("http"):
            final_order_url = f"{self.phhc_api_base_url}{final_order_url}"

        # Main case detail as a link
        main_case_raw = case_data.get("main_case_filling_no", "")
        main_case_html = ""
        if main_case_raw:
            parts = main_case_raw.split(",")
            if len(parts) == 3:
                main_case_html = self._case_link(
                    parts[0].strip(), parts[1].strip(), parts[2].strip()
                )
            else:
                main_case_html = main_case_raw

        next_date = self._format_api_date(case_data.get("listing_or_proposal_date"))

        # --- Links at the top ---
        html = "<center>\n"
        if final_order_url and final_order_date:
            html += f'<p><a href="{final_order_url}" style="color: #0066cc; font-weight: bold;">View Judgement Final Order (Dated {final_order_date})</a></p>\n'

        # --- Section 1: Case Details ---
        html += f"""<table {tbl}>
  <tr><td colspan="4" {hdr}>Case Details For Case {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {lbl}>Diary Number</td><td {val}>{diary_no}</td><td {lbl}>Registration Date</td><td {val}>{reg_date}</td></tr>
  <tr><td {lbl}>Category</td><td colspan="3" {val}>{category_full}</td></tr>
  <tr><td {lbl}>Party Detail</td><td colspan="3" {val}>{party_detail}</td></tr>
  <tr><td {lbl}>Advocate Name</td><td {val}>{pet_adv}</td><td {lbl}>District</td><td {val}>{district}</td></tr>
  <tr><td {lbl}>Respondent Advocate Name</td><td {val}>{res_adv}</td><td {lbl}>List Type</td><td {val}>{list_type_full}</td></tr>
  <tr><td {lbl} {hl}>Status</td><td colspan="3" {hl}>{status_full}</td></tr>
  <tr><td {lbl}>Final Order Uploaded On</td><td colspan="3" {val}>{final_order_date}</td></tr>
  <tr><td {lbl}>Main Case Detail</td><td {val}>{main_case_html}</td><td colspan="2"></td></tr>
  <tr><td {lbl} {hl}>Next Date</td><td colspan="3" {hl}>{next_date}</td></tr>
</table>
"""

        # --- Section 2: Related Cases/Miscellaneous Applications ---
        if related_cases:
            html += f"""<br/>
<table {tbl}>
  <tr><td colspan="2" {hdr}>Related Cases/Miscellaneous Applications</td></tr>
"""
            for rc in related_cases:
                doc = rc.get("case_documents", {}) if isinstance(rc, dict) else {}
                rc_type = doc.get("case_type", "")
                rc_no = doc.get("case_no", "")
                rc_year = doc.get("case_year", "")
                rc_link = self._case_link(rc_type, rc_no, rc_year) if rc_type else ""

                order_details = rc.get("order_details", [])
                order_link_html = ""
                if order_details:
                    for od in order_details:
                        od_url = od.get("order", "")
                        if od_url and not od_url.startswith("http"):
                            od_url = f"{self.phhc_api_base_url}{od_url}"
                        od_date = self._format_api_date(od.get("orderdate"))
                        if od_url:
                            date_label = f" Dated {od_date}" if od_date else ""
                            order_link_html += (
                                f' &nbsp;<a href="{od_url}">View Order{date_label}</a>'
                            )

                rc_main = f"IN {case_type}-{case_no}-{case_year}"
                html += f"  <tr><td {val}>{rc_link}{order_link_html}</td><td {val}>{rc_main}</td></tr>\n"
            html += "</table>\n"

        # --- Section 3: Case Listing Details ---
        if listing_history:
            html += f"""<br/>
<table {tbl}>
  <tr><td colspan="3" {hdr}>Case Listing Details</td></tr>
  <tr><td {sub_hdr}>Cause List Date</td><td {sub_hdr}>List Type-Sr. No.</td><td {sub_hdr}>Bench</td></tr>
"""
            for i, entry in enumerate(listing_history):
                cl_date = self._format_api_date(entry.get("cl_date"))
                cl_type = entry.get("cl_type", "")
                sr_no = entry.get("sr_no", "")
                type_sr = f"{cl_type}:{sr_no}"
                bench = (
                    entry.get("benchDetails", {}).get("bench_name", "")
                    if isinstance(entry.get("benchDetails"), dict)
                    else ""
                )
                row_style = hl if i == 0 else val
                html += f"  <tr><td {row_style}>{cl_date}</td><td {row_style}>{type_sr}</td><td {row_style}>{bench}</td></tr>\n"
            html += "</table>\n"

        # --- Section 4: Copy Petition Details ---
        if copy_petition:
            items = (
                copy_petition.get("items", [])
                if isinstance(copy_petition, dict)
                else []
            )
            if items:
                html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Details of Copy Petition Applied in {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {sub_hdr}>Petition Type/No</td><td {sub_hdr}>Petition Date</td><td {sub_hdr}>Applied By</td><td {sub_hdr}>Petition Status</td></tr>
"""
                for item in items:
                    pet_code = item.get("pet_code", "")
                    petrf_no = item.get("petrf_no", "")
                    pet_label = f"{pet_code}:{petrf_no}" if pet_code else str(petrf_no)
                    pet_type_no = f'<a href="https://new.phhc.gov.in/copy_petition_search_page?app_no={petrf_no}">{pet_label}</a>'
                    pet_date = item.get("pet_date", "")
                    pet_type = item.get("pet_type", "")
                    applname = item.get("applname", "")
                    applied_by = (
                        f"<strong>{pet_type}</strong><br/>{applname}"
                        if pet_type
                        else applname
                    )
                    pet_status = item.get("pet_status", "")
                    html += f"  <tr><td {val}>{pet_type_no}</td><td {val}>{pet_date}</td><td {val}>{applied_by}</td><td {val}>{pet_status}</td></tr>\n"
                html += "</table>\n"

        # --- Section 5: Judgment Details ---
        if judgments:
            html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Judgment Details For Case: {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {sub_hdr}>Order Date</td><td {sub_hdr}>Order and Case ID</td><td {sub_hdr}>Bench</td><td {sub_hdr}>Judgment Link</td></tr>
"""
            for j in judgments:
                order_date = self._format_api_date(j.get("orderdate"))
                order_type_code = j.get("order_type", "")
                order_type = {"I": "Interim Order", "F": "Final Order"}.get(
                    order_type_code, order_type_code
                )
                j_bench = j.get("bench_name", "")
                order_url = j.get("order", "")
                if order_url and not order_url.startswith("http"):
                    order_url = f"{self.phhc_api_base_url}{order_url}"
                link_html = f'<a href="{order_url}">View Order</a>' if order_url else ""
                html += f"  <tr><td {val}>{order_date}</td><td {val}>{order_type}</td><td {val}>{j_bench}</td><td {val}>{link_html}</td></tr>\n"
            html += "</table>\n"

        # --- Section 6: Impugned Orders ---
        if (
            impugned_orders
            and isinstance(impugned_orders, dict)
            and impugned_orders.get("authority")
        ):
            imp_date = self._format_api_date(impugned_orders.get("order_date"))
            if not imp_date or imp_date == "":
                imp_date = "Invalid date"
            imp_type_code = impugned_orders.get("order_type", "")
            imp_type = {"I": "Interim", "F": "Final"}.get(imp_type_code, imp_type_code)
            imp_authority = impugned_orders.get("authority", "")
            imp_district = impugned_orders.get("district", "")
            html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Impugned Orders</td></tr>
  <tr><td {sub_hdr}>Order Date</td><td {sub_hdr}>Order Type</td><td {sub_hdr}>Authority</td><td {sub_hdr}>District</td></tr>
  <tr><td {val}>{imp_date}</td><td {val}>{imp_type}</td><td {val}>{imp_authority}</td><td {val}>{imp_district}</td></tr>
</table>
"""

        html += "</center>"
        return html

    def _build_judge_cause_list_html(
        self, matching_entries: List[Dict], judge_name: str, date: str
    ) -> Optional[str]:
        """
        Generate HTML table for matching cause list entries.

        Args:
            matching_entries: Filtered entries from getRegularCauseList
            judge_name: The judge's name for the header
            date: The cause list date

        Returns:
            HTML string if entries found, None otherwise
        """
        if not matching_entries:
            return None

        html = f"""<center>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 700px;" class="case-listing-details">
  <tr><td colspan="7" style="text-align:center; font-weight:bold; background-color: #f2f2f2;">
    CAUSE LIST FOR {judge_name} ON {date}
  </td></tr>
  <tr><th>Sr No</th><th>Case</th><th>Petitioner</th><th>Respondent</th><th>Pet. Advocate</th><th>Res. Advocate</th><th>Hearing</th></tr>
"""
        for entry in matching_entries:
            sr_no = entry.get("sr_no", "")
            case = f"{entry.get('case_type', '')}-{entry.get('case_no', '')}-{entry.get('case_year', '')}"
            pet = entry.get("pet_name", "") or ""
            res = entry.get("res_name", "") or ""
            pet_adv = entry.get("pet_adv_name", "") or ""
            res_adv = entry.get("res_adv_name", "") or ""
            hearing = "Yes" if entry.get("hearing_status") == "Y" else "No"
            html += f"  <tr><td>{sr_no}</td><td>{case}</td><td>{pet}</td><td>{res}</td><td>{pet_adv}</td><td>{res_adv}</td><td>{hearing}</td></tr>\n"

        html += "</table></center>"
        return html

    def _build_listing_found_html(
        self, listing_entry: Dict, judge_name: str, date: str
    ) -> str:
        """
        Build a simple HTML confirmation that the case was found in the regular cause list.
        Used as fallback when the full cause list API times out.

        Args:
            listing_entry: The matching entry from case_listing_detail
            judge_name: The judge's bench name
            date: The cause list date

        Returns:
            HTML string confirming the listing
        """
        cl_type = listing_entry.get("cl_type", "REGULAR")
        sr_no = listing_entry.get("sr_no", "N/A")
        bench = (
            listing_entry.get("benchDetails", {}).get("bench_name", judge_name)
            if isinstance(listing_entry.get("benchDetails"), dict)
            else judge_name
        )

        return f"""<center>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 700px;" class="case-listing-details">
  <tr><td colspan="4" style="text-align:center; font-weight:bold; background-color: #f2f2f2;">
    {cl_type} CAUSE LIST — {bench} — {date}
  </td></tr>
  <tr><th>Date</th><th>List Type</th><th>Sr No</th><th>Bench</th></tr>
  <tr style="background-color: #ffff00;">
    <td>{date}</td><td>{cl_type}</td><td>{sr_no}</td><td>{bench}</td>
  </tr>
</table></center>"""

    def get_case_details_and_judge_details(
        self,
        case_details: Optional[Dict[str, str]] = None,
        search_terms: List[str] = None,
        date: str = None,
    ) -> Optional[Tuple[str, str, str]]:
        """
        Get case details and judge-wise cause list info via the PHHC API.

        Args:
            case_details: Dict with keys "type", "no", "year"
            search_terms: List of search terms to look for in the cause list
            date: Cause list date in DD/MM/YYYY format

        Returns:
            Tuple of (case_details_html, cause_list_table_html, case_status_url)
            if successful, None if case_details not provided or case not found.
        """
        if not case_details:
            return None

        case_type = case_details["type"]
        case_no = case_details["no"]
        case_year = case_details["year"]

        # Step 1: Fetch case info (required)
        case_data = self._fetch_case_info(case_type, case_no, case_year)
        if not case_data:
            print(
                f"Failed to fetch case info for {case_type}-{case_no}-{case_year}",
                flush=True,
            )
            return None

        print(
            f"PROGRESS! Case info fetched for {case_type}-{case_no}-{case_year}",
            flush=True,
        )

        # Step 2: Fetch all supplementary data (all optional, failures don't block)
        listing_history = self._fetch_case_listing_history(
            case_type, case_no, case_year
        )
        related_cases = self._fetch_related_cases(case_type, case_no, case_year)
        judgments = self._fetch_judgment_details(case_type, case_no, case_year)
        copy_petition = self._fetch_copy_petition(case_type, case_no, case_year)
        impugned_orders = self._fetch_impugned_orders(case_type, case_no, case_year)

        # Step 3: Build case details HTML with all sections
        case_details_html = self._build_case_details_html(
            case_data,
            listing_history=listing_history,
            related_cases=related_cases,
            judgments=judgments,
            copy_petition=copy_petition,
            impugned_orders=impugned_orders,
        )

        # Step 4: Check if case is listed for the target date
        combined_table_html = None
        bench_name = case_data.get("bench_name", "")
        matching_listing = None

        if listing_history and date:
            try:
                target_dt = datetime.strptime(date, "%d/%m/%Y")
                target_date_str = target_dt.strftime("%Y-%m-%d")
            except ValueError:
                target_date_str = None

            if target_date_str:
                for entry in listing_history:
                    cl_date = entry.get("cl_date", "")
                    if cl_date and cl_date.startswith(target_date_str):
                        matching_listing = entry
                        break

            if matching_listing:
                print(
                    f"PROGRESS! Case {case_type}-{case_no}-{case_year} found in listing for {date}",
                    flush=True,
                )

        # Step 5: Try to get judge-wise regular cause list
        if bench_name and search_terms and date:
            active_judges = self._fetch_active_judges()
            if active_judges:
                judge_code = self._match_judge_code(bench_name, active_judges)
                if judge_code:
                    print(
                        f"PROGRESS! Matched judge '{bench_name}' to code {judge_code}",
                        flush=True,
                    )
                    cause_list = self._fetch_regular_cause_list(judge_code, date)
                    if cause_list:
                        matching = self._search_cause_list_entries(
                            cause_list, search_terms
                        )
                        combined_table_html = self._build_judge_cause_list_html(
                            matching, bench_name, date
                        )
                    elif matching_listing:
                        print(
                            f"PROGRESS! Full cause list unavailable, using listing history as fallback",
                            flush=True,
                        )
                        combined_table_html = self._build_listing_found_html(
                            matching_listing, bench_name, date
                        )

        case_status_url = self._case_status_url(case_type, case_no, case_year)
        return case_details_html, combined_table_html, case_status_url
