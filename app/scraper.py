import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os


class Scraper:
    def __init__(self):
        self.base_url = os.getenv("BASE_URL")
        self.form_action_url = os.getenv("FORM_ACTION_URL")

    def submit_view_cl_form(self, date: str):
        # Simulate form submission to the actual endpoint
        form_data = {
            "t_f_date": date,  # The date of the cause list, e.g. "27/12/2024"
            "urg_ord": "1",  # The list type, e.g. "1" for All Cause Lists
            "action": "show_causeList",  # Action to show the cause list
        }

        response = requests.post(self.form_action_url, data=form_data)
        return response.text

    def parse_table_and_download_pdfs(self, date: str):
        page_html = self.submit_view_cl_form(date)
        soup = BeautifulSoup(page_html, "html.parser")

        rows = soup.select("table#tables11 tr")
        pdf_links = {}

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
                    pdf_url = urljoin(self.base_url, pdf_url)  # Make it an absolute URL
                    pdf_name = f"{date}__{list_type}__{main_sup}"
                    pdf_links[pdf_name] = pdf_url

        return pdf_links
