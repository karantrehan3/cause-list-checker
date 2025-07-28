from typing import Dict, List, Optional, Tuple
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
        # Common URL replacements for HTML content
        self._url_replacements = {
            "../data/": f"{self.main_base_url}/data/",
            "../images/": f"{self.main_base_url}/images/",
            "../css/": f"{self.main_base_url}/css/",
            "../js/": f"{self.main_base_url}/js/",
            "href='./": f"href='{self.main_base_url}/",
            "href='../": f"href='{self.main_base_url}/",
            "href='enq_caseno": f"href='{self.main_base_url}/enq_caseno",
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

    def _make_request(
        self, method: str, url: str, **kwargs
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with error handling and session management.

        Args:
            method: HTTP method ('GET' or 'POST')
            url: URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response object if successful, None if failed
        """
        try:
            with self._create_session() as session:
                if method.upper() == "GET":
                    response = session.get(url, **kwargs)
                elif method.upper() == "POST":
                    response = session.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            print(f"Error making {method} request to {url}: {e}", flush=True)
            return None

    def _process_html_content(
        self, html_content: str, highlight_cells: bool = False
    ) -> str:
        """
        Process HTML content by replacing relative URLs and optionally highlighting cells.

        Args:
            html_content: Raw HTML content
            highlight_cells: Whether to add yellow highlighting to specific cells

        Returns:
            Processed HTML content
        """
        if not html_content:
            return ""

        # Replace relative paths with absolute URLs
        for old, new in self._url_replacements.items():
            html_content = html_content.replace(old, new)

        # Add yellow highlighting to specific cells if requested
        if highlight_cells:
            html_content = self._highlight_specific_cells(html_content)

        return html_content

    def _highlight_cell_pair(
        self, soup: BeautifulSoup, cell_text: str, exact_match: bool = True
    ) -> None:
        """
        Highlight a cell and its corresponding value cell in the same row.

        Args:
            soup: BeautifulSoup object
            cell_text: Text to search for in cells
            exact_match: Whether to use exact match or substring match
        """
        # Define the search function based on match type
        if exact_match:
            search_func = lambda text: text and text.strip() == cell_text
        else:
            search_func = lambda text: text and cell_text in text.strip()

        cells = soup.find_all(["td", "th"], string=search_func)

        for cell in cells:
            # Highlight the header cell
            cell["style"] = "background-color: #ffff00;"  # Yellow highlight

            # Find and highlight the corresponding value cell (next cell in the same row)
            parent_row = cell.find_parent("tr")
            if parent_row:
                row_cells = parent_row.find_all(["td", "th"])
                try:
                    cell_index = row_cells.index(cell)
                    if cell_index + 1 < len(row_cells):
                        value_cell = row_cells[cell_index + 1]
                        value_cell["style"] = (
                            "background-color: #ffff00;"  # Yellow highlight
                        )
                except ValueError:
                    pass  # Cell not found in the list

    def submit_view_cl_form(self, date: str) -> str:
        # Simulate form submission to the actual endpoint
        form_data = {
            "t_f_date": date,  # The date of the cause list, e.g. "27/12/2024"
            "urg_ord": "1",  # The list type, e.g. "1" for All Cause Lists
            "action": "show_causeList",  # Action to show the cause list
        }

        response = self._make_request(
            "POST", self.form_action_url, data=form_data, headers=self.headers
        )
        if response is None:
            raise requests.exceptions.RequestException("Failed to submit view CL form")
        return response.text

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

        response = self._make_request(
            "POST", self.case_search_url, data=form_data, headers=self.headers
        )
        if response is None:
            return None

        # Get the PHPSESSID cookie
        session_cookie = response.cookies.get("PHPSESSID")
        if not session_cookie:
            return None

        # Parse response to get case_id
        soup = BeautifulSoup(response.text, "html.parser")
        case_link = soup.find("a", href=lambda x: x and "enq_caseno.php?case_id=" in x)

        if not case_link:
            return None

        # Extract case_id from the link
        case_id = case_link["href"].split("case_id=")[1]

        return case_id, session_cookie

    def parse_case_listing_details_section(
        self, html_content: str
    ) -> Tuple[Dict[str, str], str]:
        """
        Parses the 'Case Listing Details' section from the given HTML content.
        Returns a tuple of (judge_details_dict, extracted_rows_html), where:
        - judge_details_dict: Dict[str, str] mapping headers to values
        - extracted_rows_html: str HTML string containing the target row and the next 2 rows
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            target_row = soup.find("th", string="Case Listing Details")
            if not target_row:
                return {}, ""
            target_tr = target_row.find_parent("tr")
            if not target_tr:
                return {}, ""

            # Add the target row and the next 2 rows to the new table (without extracting)
            rows_to_add = [target_tr]
            current_row = target_tr
            headers_row = None
            values_row = None
            for i in range(2):
                next_row = current_row.find_next_sibling("tr")
                if next_row:
                    rows_to_add.append(next_row)
                    if i == 0:
                        headers_row = next_row
                    elif i == 1:
                        values_row = next_row
                    current_row = next_row
                else:
                    break

            judge_details_dict = {}
            if headers_row and values_row:
                headers = [th.get_text(strip=True) for th in headers_row.find_all("th")]
                values = [td.get_text(strip=True) for td in values_row.find_all("td")]
                if len(headers) == len(values):
                    judge_details_dict = dict(zip(headers, values))

            return judge_details_dict
        except Exception as e:
            print(f"Error parsing case listing details: {e}", flush=True)
            return {}, ""

    def _highlight_specific_cells(self, html_content: str) -> str:
        """
        Add yellow highlighting to specific cells in the HTML content.

        Highlights:
        - "Status" cell and its corresponding value cell
        - "Takenup date" cell and its corresponding value cell
        - The complete last row found in the "Case Listing Details" section

        Args:
            html_content (str): The HTML content to process

        Returns:
            str: HTML content with highlighted cells
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Highlight "Status" and its value cell
            self._highlight_cell_pair(soup, "Status", exact_match=True)

            # Highlight "Takenup date" and its value cell
            self._highlight_cell_pair(soup, "Takenup date", exact_match=False)

            # Highlight the complete 2nd row after "Case Listing Details" section
            # Using the same logic as parse_case_listing_details_section
            target_row = soup.find("th", string="Case Listing Details")
            if target_row:
                target_tr = target_row.find_parent("tr")
                if target_tr:
                    current_row = target_tr
                    values_row = None

                    # Get the 2nd row after the target row (same logic as parse_case_listing_details_section)
                    for i in range(2):
                        next_row = current_row.find_next_sibling("tr")
                        if next_row:
                            if i == 1:  # This is the 2nd row after target row
                                values_row = next_row
                            current_row = next_row
                        else:
                            break

                    # Highlight the 2nd row after target row
                    if values_row:
                        cells = values_row.find_all(["td", "th"])
                        for cell in cells:
                            cell["style"] = (
                                "background-color: #ffff00;"  # Yellow highlight
                            )

            return str(soup)
        except Exception as e:
            print(f"Error highlighting cells: {e}", flush=True)
            return html_content

    def get_case_details(
        self, case_id: Optional[str] = None, session_cookie: Optional[str] = None
    ) -> Optional[str]:
        """
        Get case details by fetching the case details page using case ID and session cookie.

        Args:
            case_id (Optional[str]): The case ID obtained from case search.
            session_cookie (Optional[str]): The PHPSESSID cookie value for authentication.

        Returns:
            Optional[str]: HTML content containing case details if successful, otherwise None.
        """
        if not case_id or not session_cookie:
            return None

        case_details_url = f"{self.case_details_url}?case_id={case_id}"
        headers = {**self.headers, "Cookie": f"PHPSESSID={session_cookie}"}

        response = self._make_request("GET", case_details_url, headers=headers)
        if response is None:
            return None

        html_content = response.text if response.text else None
        if html_content is None:
            return None

        # Process HTML content with highlighting
        return self._process_html_content(html_content, highlight_cells=True)

    def get_judge_code(self, judge_name: str, session_cookie: str) -> Optional[str]:
        """
        Get judge code by fetching the judge registration page and parsing the dropdown.

        Args:
            judge_name (str): The name of the judge (e.g., "MR. JUSTICE HARKESH MANUJA")
            session_cookie (str): The PHPSESSID cookie value

        Returns:
            Optional[str]: The judge code value if found, otherwise None
        """
        judge_reg_url = f"{self.main_base_url}/home.php?search_param=jud_reg_cl"
        headers = {**self.headers, "Cookie": f"PHPSESSID={session_cookie}"}

        response = self._make_request("GET", judge_reg_url, headers=headers)
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the select dropdown using the xpath equivalent
        # /html/body/table[1]/tbody/tr[5]/td/table/tbody/tr/td[2]/table/tbody/tr[3]/td[2]/select
        select_element = soup.find("select", {"name": "t_jud_code"})

        if not select_element:
            print(f"Could not find judge dropdown select element", flush=True)
            return None

        # Find the option with matching judge name
        for option in select_element.find_all("option"):
            if (
                judge_name.lower()
                in option.get_text(strip=True).replace("HON'BLE ", "").lower()
            ):
                return option.get("value")

        print(f"Could not find judge code for judge '{judge_name}'", flush=True)
        return None

    def get_judge_registration_html(
        self, date: str, judge_code: str, session_cookie: str
    ) -> Optional[str]:
        """
        Get judge registration HTML content by submitting the form with date and judge code.

        Args:
            date (str): The cause list date in format "DD/MM/YYYY" (e.g., "28/07/2025")
            judge_code (str): The judge code (e.g., "695")
            session_cookie (str): The PHPSESSID cookie value for authentication.

        Returns:
            Optional[str]: HTML content containing judge registration details if successful, otherwise None.
        """
        judge_reg_url = f"{self.main_base_url}/home.php?search_param=jud_reg_cl"
        headers = {**self.headers, "Cookie": f"PHPSESSID={session_cookie}"}

        # Form data as specified in the curl command
        form_data = {"cl_date": date, "t_jud_code": judge_code, "submit": "Search Case"}

        response = self._make_request(
            "POST", judge_reg_url, data=form_data, headers=headers
        )
        if response is None:
            return None

        html_content = response.text if response.text else None
        if html_content is None:
            return None

        # Process HTML content without highlighting
        return self._process_html_content(html_content, highlight_cells=False)

    def _parse_judge_registration_and_create_table(
        self, judge_registration_html: str, search_terms: str
    ) -> Optional[str]:
        """
        Parse judge registration HTML to find rows containing search terms and create a combined table HTML.

        Args:
            judge_registration_html (str): The HTML content of the judge registration page
            search_terms (str): The search terms to look for in the HTML

        Returns:
            Optional[str]: Combined table HTML if search terms are found, None otherwise
        """
        soup = BeautifulSoup(judge_registration_html, "html.parser")
        text_content = soup.get_text().lower()

        if not any(term.lower() in text_content for term in search_terms):
            return None

        # Find the deepest nested tr elements that contain the search term
        max_depth = 0
        deepest_rows = set()
        header_max_depth = 0
        header_row = set()

        for tr in soup.find_all("tr"):
            depth = len(tr.find_parents("table"))
            if "CAUSE LIST FOR".lower() in tr.get_text().lower():
                if depth > header_max_depth:
                    # Found deeper rows, discard previous ones
                    header_max_depth = depth
                    header_row.clear()
                    header_row.add(tr)
                elif depth == header_max_depth:
                    # Same depth, add to set (automatically handles duplicates)
                    header_row.add(tr)

            if any(term.lower() in tr.get_text().lower() for term in search_terms):
                if depth > max_depth:
                    # Found deeper rows, discard previous ones
                    max_depth = depth
                    deepest_rows.clear()
                    deepest_rows.add(tr)
                elif depth == max_depth:
                    # Same depth, add to set (automatically handles duplicates)
                    deepest_rows.add(tr)
                # Rows with depth < max_depth are ignored (memory efficient)

        if deepest_rows:
            # Convert set to list and combine all unique rows into a single table
            header_row = list(header_row)
            unique_rows = list(deepest_rows)

            # Determine the maximum number of columns from data rows
            max_columns = 0
            for tr in unique_rows:
                cells = tr.find_all(["td", "th"])
                max_columns = max(max_columns, len(cells))

            # Create the combined table HTML
            combined_table_html = '<center><table border="1" cellpadding="5" cellspacing="0" class="case-listing-details">'

            # Add header rows with colspan to span all columns
            for tr in header_row:
                # Create a copy of the row to modify
                header_copy = BeautifulSoup(str(tr), "html.parser")
                header_tr = header_copy.find("tr")
                if header_tr:
                    # Find the first cell (td or th) and add colspan
                    first_cell = header_tr.find(["td", "th"])
                    if first_cell and max_columns > 0:
                        first_cell["colspan"] = str(max_columns)
                        # Remove any other cells in the header row
                        other_cells = first_cell.find_next_siblings(["td", "th"])
                        for cell in other_cells:
                            cell.decompose()
                    combined_table_html += str(header_copy)

            for tr in unique_rows:
                combined_table_html += str(tr)
            combined_table_html += "</table></center>"

            for old, new in self._url_replacements.items():
                combined_table_html = combined_table_html.replace(old, new)
            return combined_table_html

        return None

    def get_case_details_and_judge_details(
        self,
        case_details: Optional[Dict[str, str]] = None,
        search_terms: str = None,
        date: str = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Get case details by first obtaining the case ID and session cookie, then fetching details.

        Args:
            case_details (Optional[Dict[str, str]]):
                A dictionary containing:
                - "type" (str): Type of the case (e.g., 'CR').
                - "no" (str): Case number (e.g., '1234').
                - "year" (str): Year of the case (e.g., '2015').
            search_terms (str): The search terms to search for in the judge registration HTML.
            date (str): The cause list date in format "DD/MM/YYYY" (e.g., "28/07/2025").
        Returns:
            Optional[Tuple[str, str]]:
                Tuple of (html_content, combined_table_html) if successful,
                None if any step fails.
        """
        if not case_details:
            return None

        result = self.submit_view_case_status_form(
            case_details["type"], case_details["no"], case_details["year"]
        )
        if not result:
            return None

        case_id, session_cookie = result

        html_content = self.get_case_details(case_id, session_cookie)
        if not html_content:
            return None

        judge_details_dict = self.parse_case_listing_details_section(html_content)
        judge_name = judge_details_dict.get("Bench", "").replace("HON'BLE ", "")
        combined_table_html = None

        if not judge_name:
            return None

        judge_code = self.get_judge_code(judge_name, session_cookie)

        if not judge_code:
            return None

        judge_registration_html = self.get_judge_registration_html(
            date, judge_code, session_cookie
        )

        if not judge_registration_html:
            return None

        combined_table_html = self._parse_judge_registration_and_create_table(
            judge_registration_html, search_terms
        )

        return html_content, combined_table_html
