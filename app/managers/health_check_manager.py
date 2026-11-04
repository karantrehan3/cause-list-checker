"""Daily live health check of every court dependency, run from the Lambda.

Runs on the same network and runtime as real searches, so a failure here is
exactly what a search would hit. Each check reports ok / warning / failed.
"""

import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import fitz

from app.clients.court_http import CourtHttpClient, CourtSiteError
from app.clients.phhc_api import PhhcApi
from app.managers.cause_list_manager import NEW_SOURCE, OLD_SOURCE, CauseListManager
from app.managers.judge_cause_list_manager import match_judge_code, unwrap_records
from app.utils.http_debug import get_egress_ip

IST = timezone(timedelta(hours=5, minutes=30))
OK, WARNING, FAILED = "ok", "warning", "failed"
LOOKAHEAD_DAYS = 7  # court days to scan for published cause lists
MAX_REGULAR_LIST_JUDGES = (
    3  # judges to try for the regular list (avoid hammering the API)
)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    duration_ms: int = 0


@dataclass
class HealthReport:
    checks: List[CheckResult]
    generated_at: str
    egress_ip: str
    runtime: str
    region: str

    @property
    def failed(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == FAILED]

    @property
    def warnings(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == WARNING]

    @property
    def healthy(self) -> bool:
        return not self.failed


class CheckWarning(Exception):
    """Not broken, but worth knowing (e.g. no lists published yet)."""


@dataclass
class _Context:
    """Values discovered by earlier checks and reused by later ones."""

    case_data: Dict = field(default_factory=dict)
    judges: List[Dict] = field(default_factory=list)


class HealthCheckManager:
    def __init__(
        self,
        client: Optional[CourtHttpClient] = None,
        api: Optional[PhhcApi] = None,
        cause_lists: Optional[CauseListManager] = None,
        today: Optional[datetime] = None,
    ):
        self.client = client or CourtHttpClient()
        self.api = api or PhhcApi(self.client)
        self.cause_lists = cause_lists or CauseListManager(self.client, self.api)
        self.today = today or datetime.now(IST)

    def run(self, case_details: Optional[Dict[str, str]] = None) -> HealthReport:
        context = _Context()
        checks: List[Tuple[str, Callable[[], str]]] = [
            (f"Cause list PDFs ({OLD_SOURCE})", lambda: self._check_source(OLD_SOURCE)),
            (f"Cause list PDFs ({NEW_SOURCE})", lambda: self._check_source(NEW_SOURCE)),
            ("Active judges list", lambda: self._check_judges(context)),
            ("Case status", lambda: self._check_case_status(case_details, context)),
            ("Judge-wise cause list (daily)", lambda: self._check_daily_list(context)),
            (
                "Judge-wise regular cause list",
                lambda: self._check_regular_list(context),
            ),
        ]
        results = [self._timed(name, check) for name, check in checks]
        for result in results:
            print(
                f"HEALTH {result.status.upper()}: {result.name}: {result.detail}",
                flush=True,
            )
        return HealthReport(
            checks=results,
            generated_at=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            egress_ip=get_egress_ip(),
            runtime=f"Python {platform.python_version()}",
            region=os.environ.get("AWS_REGION", "local"),
        )

    # --- individual checks (return a detail string, or raise) -----------------

    def _check_source(self, source: str) -> str:
        fetch = {
            OLD_SOURCE: self.cause_lists.fetch_old_site,
            NEW_SOURCE: self.cause_lists.fetch_new_site,
        }[source]
        for date in self._upcoming_dates():
            pdfs = fetch(date)
            if pdfs:
                pages, text_pages, size = self._download_pdf(pdfs[0]["pdf_url"])
                return (
                    f"{len(pdfs)} list(s) for {date}; downloaded '{pdfs[0]['pdf_name']}': "
                    f"{size / 1e6:.2f} MB, {pages} pages, {text_pages} with text"
                )
        raise CheckWarning(
            f"no cause lists published for the next {LOOKAHEAD_DAYS} days"
        )

    def _check_judges(self, context: _Context) -> str:
        context.judges = self.api.active_judges()
        if not context.judges:
            raise CourtSiteError("active judges list is empty")
        return f"{len(context.judges)} active judges"

    def _check_case_status(
        self, case_details: Optional[Dict[str, str]], context: _Context
    ) -> str:
        if not case_details:
            raise CheckWarning("skipped: no case_details in the health check event")
        case_type, case_no, case_year = (
            case_details["type"],
            case_details["no"],
            case_details["year"],
        )
        context.case_data = self.api.case_info(case_type, case_no, case_year)
        bench = context.case_data.get("bench_name") or "no bench"
        return f"{case_type}-{case_no}-{case_year} found ({bench})"

    def _check_daily_list(self, context: _Context) -> str:
        bench = context.case_data.get("bench_name")
        if not bench or not context.judges:
            raise CheckWarning("skipped: needs case status and judges list")
        judge_code = match_judge_code(bench, context.judges)
        if not judge_code:
            raise CourtSiteError(f"could not match bench '{bench}' to an active judge")
        for date in self._upcoming_dates():
            entries = unwrap_records(self.api.daily_cause_list(judge_code, date))
            if entries:
                self._assert_entry_shape(entries)
                return f"{len(entries)} entries for {bench} on {date}"
        raise CheckWarning(
            f"no daily list for {bench} in the next {LOOKAHEAD_DAYS} days"
        )

    def _check_regular_list(self, context: _Context) -> str:
        date = self.api.latest_regular_list_date()
        judges = context.judges or self.api.active_judges()
        case_judge = match_judge_code(context.case_data.get("bench_name", ""), judges)
        judges = sorted(judges, key=lambda j: j.get("judge_code") != case_judge)
        for judge in judges[:MAX_REGULAR_LIST_JUDGES]:
            entries = unwrap_records(
                self.api.regular_cause_list(judge["judge_code"], date)
            )
            if entries:
                self._assert_entry_shape(entries)
                return f"latest list {date}: {len(entries)} entries for {judge.get('judge_name')}"
        raise CheckWarning(
            f"latest regular list ({date}) has no entries for the first "
            f"{MAX_REGULAR_LIST_JUDGES} judges checked"
        )

    # --- helpers -----------------------------------------------------------------

    def _upcoming_dates(self) -> List[str]:
        return [
            (self.today + timedelta(days=offset)).strftime("%d/%m/%Y")
            for offset in range(1, LOOKAHEAD_DAYS + 1)
        ]

    def _download_pdf(self, url: str) -> Tuple[int, int, int]:
        """(pages, pages with text, bytes). Raises CourtSiteError if it isn't a usable PDF."""
        content = self.client.request("GET", url, timeout=(10, 90)).content
        if content[:5] != b"%PDF-":
            raise CourtSiteError("downloaded file is not a PDF")
        with fitz.open(stream=content, filetype="pdf") as document:
            pages = len(document)
            text_pages = sum(1 for page in document if page.get_text().strip())
        if not text_pages:
            raise CourtSiteError(f"PDF has no searchable text ({pages} pages)")
        return pages, text_pages, len(content)

    @staticmethod
    def _assert_entry_shape(entries: List[Dict]) -> None:
        missing = [
            key
            for key in ("case_type", "case_no", "case_year")
            if key not in entries[0]
        ]
        if missing:
            raise CourtSiteError(f"response shape changed: entries missing {missing}")

    @staticmethod
    def _timed(name: str, check: Callable[[], str]) -> CheckResult:
        start = time.monotonic()
        try:
            status, detail = OK, check()
        except CheckWarning as e:
            status, detail = WARNING, str(e)
        except CourtSiteError as e:
            status, detail = FAILED, e.reason
        except Exception as e:  # a bug in a check must not stop the report
            status, detail = FAILED, f"unexpected error: {e.__class__.__name__}: {e}"
        return CheckResult(name, status, detail, int((time.monotonic() - start) * 1000))
