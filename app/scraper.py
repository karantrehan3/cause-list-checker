import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class Scraper:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_pdf_links(self) -> list[dict]:
        response = requests.get(self.base_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        table = soup.find("table", {"id": "tables11"})
        links = []
        if table:
            rows = table.find_all("tr")[2:]  # Skip header rows
            for row in rows:
                date_cell = row.find("a")
                type_cell = row.find_all("td")[1].get_text(strip=True)
                main_sup_cell = row.find_all("td")[2].get_text(strip=True)

                if date_cell and date_cell.get("onclick"):
                    filename = date_cell["onclick"].split("filename=")[-1].strip("')\"")
                    links.append(
                        {
                            "url": urljoin(
                                self.base_url,
                                f"./show_cause_list.php?filename={filename}",
                            ),
                            "date": date_cell.get_text(strip=True),
                            "type": type_cell,
                            "main_sup": main_sup_cell,
                        }
                    )
        return links
