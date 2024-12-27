import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class PDFScraper:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def submit_view_cl_form(self, date: str):
        # Simulate form submission to the actual endpoint
        form_data = {
            "t_f_date": date,  # The date of the cause list, e.g. "27/12/2024"
            "urg_ord": "1",  # The list type, e.g. "1" for All Cause Lists
            "action": "show_causeList",  # Action to show the cause list
        }

        form_action_url = "https://highcourtchd.gov.in/view_causeList.php"
        response = requests.post(form_action_url, data=form_data)

        return response.text  # Return the HTML page content

    def parse_table_and_download_pdfs(self, date: str):
        page_html = self.submit_view_cl_form(date)
        soup = BeautifulSoup(page_html, "html.parser")

        rows = soup.select("table#tables11 tr")
        pdf_links = []

        for row in rows:
            link = row.find("a", href=True)
            if link:
                pdf_url = link["onclick"].split("'")[
                    1
                ]  # Extracting the URL from onclick
                pdf_links.append(
                    urljoin(self.base_url, pdf_url)
                )  # Make it an absolute URL

        return pdf_links
