"""Cause list PDFs from both court sites.

- old: highcourtchd.gov.in (complete set of lists)
- new: new.phhc.gov.in daily-causelist-pdf API (partial while the court migrates)

Both are searched in full and shown separately in the email.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.clients.court_http import CourtHttpClient, CourtSiteError
from app.clients.phhc_api import PhhcApi
from app.config import settings
from app.managers.pdf_tracker import pdf_tracker

OLD_SOURCE = "highcourtchd.gov.in"
NEW_SOURCE = "new.phhc.gov.in"
MAIN_SUPPL_NAMES = {"M": "Main List", "S": "Supplementary List"}
# pdf_list_type() values the email treats specially.
REGULAR_LIST = "regular"
COMPLETE_LIST = "complete list"  # repeats the entries of the other lists

Pdf = Dict[str, str]


def pdf_list_type(pdf_name: str) -> str:
    """'Regular | Supplementary List' -> 'regular' (pdf_name is "<type> | <main/sup>")."""
    return pdf_name.split(" | ")[0].strip().lower()


def cause_list_sources() -> List[Dict[str, str]]:
    """Cause list sources in the order the email shows them."""
    return [
        {"name": OLD_SOURCE, "url": settings.CL_BASE_URL},
        {"name": NEW_SOURCE, "url": settings.CL_DAILY_URL},
    ]


@dataclass
class CauseListResult:
    existing_pdfs: List[Pdf] = field(default_factory=list)
    new_pdfs: List[Pdf] = field(default_factory=list)
    source_errors: Dict[str, str] = field(default_factory=dict)  # source -> reason

    @property
    def pdfs(self) -> List[Pdf]:
        return self.existing_pdfs + self.new_pdfs


class CauseListManager:
    def __init__(
        self,
        client: Optional[CourtHttpClient] = None,
        api: Optional[PhhcApi] = None,
    ):
        self.client = client or CourtHttpClient()
        self.api = api or PhhcApi(self.client)

    def fetch(self, date: str, search_terms: List[str]) -> CauseListResult:
        """
        Collect cause list PDFs from both sites.

        Raises:
            CourtSiteError: only if BOTH sources fail.
        """
        sources: Dict[str, Callable[[str], List[Pdf]]] = {
            OLD_SOURCE: self.fetch_old_site,
            NEW_SOURCE: self.fetch_new_site,
        }
        pdfs: List[Pdf] = []
        errors: Dict[str, str] = {}
        for source, fetch in sources.items():
            try:
                pdfs.extend(fetch(date))
            except CourtSiteError as e:
                print(
                    f"Cause list source {source} failed for {date}: {e.reason}",
                    flush=True,
                )
                errors[source] = e.reason

        if len(errors) == len(sources):
            raise CourtSiteError(
                "all cause list sources failed: "
                + "; ".join(f"{s}: {r}" for s, r in errors.items())
            )

        counts = ", ".join(
            f"{s}={sum(p['source'] == s for p in pdfs)}" for s in sources
        )
        print(f"PROGRESS! Cause lists for {date}: {counts}", flush=True)

        existing, new = pdf_tracker.separate_existing_and_new_pdfs(pdfs, search_terms)
        return CauseListResult(existing, new, errors)

    def fetch_old_site(self, date: str) -> List[Pdf]:
        """Scrape PDF links from the highcourtchd.gov.in cause list table."""
        response = self.client.request(
            "POST",
            settings.CL_FORM_ACTION_URL,
            data={"t_f_date": date, "urg_ord": "1", "action": "show_causeList"},
        )
        soup = BeautifulSoup(response.text, "html.parser")
        pdfs = []
        for row in soup.select("table#tables11 tr")[2:]:
            cells = row.find_all("td")
            if len(cells) != 3:
                continue
            link = cells[0].find("a", href=True)
            if not link or not link.get("onclick"):
                continue
            list_type = cells[1].text.strip()
            main_sup = cells[2].text.strip()
            pdfs.append(
                {
                    "pdf_name": f"{list_type} | {main_sup}",
                    "pdf_url": urljoin(
                        settings.CL_BASE_URL, link["onclick"].split("'")[1]
                    ),
                    "source": OLD_SOURCE,
                }
            )
        return pdfs

    def fetch_new_site(self, date: str) -> List[Pdf]:
        """List cause list PDFs from the new.phhc.gov.in daily-causelist-pdf API."""
        entries = self.api.daily_pdf_list(date)
        try:
            types = self.api.daily_pdf_list_types()
        except CourtSiteError:
            types = []  # names fall back to the raw list code
        type_names = {
            str(t.get("code", "")).upper(): t.get("description", "") for t in types
        }

        pdfs = []
        for entry in entries:
            code = str(entry.get("list_type", "")).upper()
            suppl = str(entry.get("main_suppl", "")).upper()
            if not code or suppl not in MAIN_SUPPL_NAMES:
                continue
            list_type = (type_names.get(code) or code).title()
            pdfs.append(
                {
                    "pdf_name": f"{list_type} | {MAIN_SUPPL_NAMES[suppl]}",
                    "pdf_url": self.api.daily_pdf_url(date, code, suppl),
                    "source": NEW_SOURCE,
                }
            )
        return pdfs
