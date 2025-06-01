from typing import Dict, List, Optional
from urllib.parse import urljoin

import certifi
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import settings


class Scraper:
    def __init__(self):
        self.cl_base_url = settings.CL_BASE_URL
        self.main_base_url = settings.MAIN_BASE_URL
        self.form_action_url = settings.FORM_ACTION_URL
        self.case_search_url = settings.CASE_SEARCH_URL
        self.case_details_url = settings.CASE_DETAILS_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _create_session(self) -> requests.Session:
        """Create a new session with retry logic and SSL verification"""
        session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)

        # Configure SSL verification
        session.verify = certifi.where()  # Use certifi's certificate bundle
        return session

    def submit_view_cl_form(self, date: str) -> str:
        # Simulate form submission to the actual endpoint
        form_data = {
            "t_f_date": date,  # The date of the cause list, e.g. "27/12/2024"
            "urg_ord": "1",  # The list type, e.g. "1" for All Cause Lists
            "action": "show_causeList",  # Action to show the cause list
        }

        try:
            with self._create_session() as session:
                response = session.post(
                    self.form_action_url, data=form_data, headers=self.headers
                )
                response.raise_for_status()
                return response.text
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}", flush=True)
            raise

    def parse_table_and_download_pdfs(self, date: str) -> List[Dict[str, str]]:
        page_html = self.submit_view_cl_form(date)
        soup = BeautifulSoup(page_html, "html.parser")

        rows = soup.select("table#tables11 tr")
        pdfs = []

        for row in rows[2:]:  # Skip the header rows
            cells = row.find_all("td")
            if len(cells) == 3:
                link = cells[0].find("a", href=True)
                list_type = cells[1].text.strip()
                main_sup = cells[2].text.strip()

                if link:
                    pdf_url = link["onclick"].split("'")[
                        1
                    ]  # Extracting the URL from onclick
                    pdf_url = urljoin(
                        self.cl_base_url, pdf_url
                    )  # Make it an absolute URL
                    pdf_name = f"{list_type} | {main_sup}"
                    pdfs.append({"pdf_name": pdf_name, "pdf_url": pdf_url})

        return pdfs

    def submit_view_case_status_form(
        self, case_type: str, case_no: str, case_year: str
    ) -> Optional[tuple[str, str]]:
        """
        Submit the case status search form and get case ID and session cookie

        Args:
            case_type: Type of the case (e.g. 'CR')
            case_no: Case number (e.g. '1234')
            case_year: Year of the case (e.g. '2015')

        Returns:
            Tuple of (case_id, session_cookie) if found, None if not found
        """
        form_data = {
            "t_case_type": case_type,
            "t_case_no": case_no,
            "t_case_year": case_year,
            "submit": "Search Case",
        }

        try:
            with self._create_session() as session:
                response = session.post(
                    self.case_search_url, data=form_data, headers=self.headers
                )
                response.raise_for_status()

                # Get the PHPSESSID cookie
                session_cookie = session.cookies.get("PHPSESSID")
                if not session_cookie:
                    return None

                # Parse response to get case_id
                soup = BeautifulSoup(response.text, "html.parser")
                case_link = soup.find(
                    "a", href=lambda x: x and "enq_caseno.php?case_id=" in x
                )

                if not case_link:
                    return None

                # Extract case_id from the link
                case_id = case_link["href"].split("case_id=")[1]

                return case_id, session_cookie
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}", flush=True)
            return None

    def get_case_details(
        self, case_details: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Get case details by first obtaining the case ID and session cookie, then fetching details.

        Args:
            case_details (Optional[Dict[str, str]]):
                A dictionary containing:
                - "type" (str): Type of the case (e.g., 'CR').
                - "no" (str): Case number (e.g., '1234').
                - "year" (str): Year of the case (e.g., '2015').

        Returns:
            Optional[str]: HTML content containing case details if successful, otherwise None.
        """
        if not case_details:
            return None

        result = self.submit_view_case_status_form(
            case_details["type"], case_details["no"], case_details["year"]
        )
        if not result:
            return None

        case_id, session_cookie = result
        case_details_url = f"{self.case_details_url}?case_id={case_id}"
        headers = {**self.headers, "Cookie": f"PHPSESSID={session_cookie}"}

        try:
            with self._create_session() as session:
                details_response = session.get(case_details_url, headers=headers)
                details_response.raise_for_status()

                html_content = details_response.text if details_response.text else None

                if html_content is None:
                    return None

                # Replace relative paths with absolute URLs
                replacements = {
                    "../data/": f"{self.main_base_url}/data/",
                    "../images/": f"{self.main_base_url}/images/",
                    "../css/": f"{self.main_base_url}/css/",
                    "../js/": f"{self.main_base_url}/js/",
                    "href='./": f"href='{self.main_base_url}/",
                    "href='../": f"href='{self.main_base_url}/",
                }

                for old, new in replacements.items():
                    html_content = html_content.replace(old, new)

                return html_content
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}", flush=True)
            return None
