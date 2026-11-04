"""Case status + judge-wise cause list checks for one case on one date.

Every check reports one of: found / not found / unavailable (with a reason),
so a failed request can never be mistaken for "not listed".
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.managers import case_html
from app.managers.court_http import CourtSiteError
from app.managers.judge_cause_list import (
    judge_code_for_bench,
    match_judge_code,
    search_entries,
    unwrap_records,
)
from app.managers.phhc_api import PhhcApi, to_api_date

FOUND, NOT_FOUND, UNAVAILABLE = "found", "not_found", "unavailable"


@dataclass
class JudgeListOutcome:
    html: Optional[str] = None  # table of matching entries
    error: Optional[str] = None  # why the list could not be checked
    entries_checked: int = 0
    bench_name: str = ""

    @property
    def status(self) -> str:
        if self.error:
            return UNAVAILABLE
        return FOUND if self.html else NOT_FOUND


@dataclass
class CaseLookupResult:
    case_id: str
    case_status_url: str
    case_details_html: Optional[str] = None
    daily: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    regular: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    issues: List[str] = field(default_factory=list)


class CaseLookup:
    def __init__(self, api: PhhcApi):
        self.api = api

    def run(
        self, case_details: Dict[str, str], search_terms: List[str], date: str
    ) -> CaseLookupResult:
        case_type, case_no, case_year = (
            case_details["type"],
            case_details["no"],
            case_details["year"],
        )
        result = CaseLookupResult(
            case_id=f"{case_type}-{case_no}-{case_year}",
            case_status_url=case_html.case_status_url(case_type, case_no, case_year),
        )

        try:
            case_data = self.api.case_info(case_type, case_no, case_year)
        except CourtSiteError as e:
            self._fail_all(result, f"case status unavailable ({e.reason})")
            return result
        print(f"PROGRESS! Case info fetched for {result.case_id}", flush=True)

        args = (case_type, case_no, case_year)
        listing_history = self._optional(
            result, "Case listing history", self.api.listing_history, args, []
        )
        result.case_details_html = case_html.build_case_details_html(
            case_data,
            listing_history=listing_history,
            related_cases=self._optional(
                result, "Related cases", self.api.related_cases, args, []
            ),
            judgments=self._optional(
                result, "Judgment details", self.api.judgments, args, []
            ),
            copy_petition=self._optional(
                result, "Copy petitions", self.api.copy_petitions, args, {}
            ),
            impugned_orders=self._optional(
                result, "Impugned orders", self.api.impugned_orders, args, {}
            ),
        )

        listing_entry = self._listing_for_date(listing_history, date)
        if listing_entry:
            print(
                f"PROGRESS! {result.case_id} is in the listing history for {date}",
                flush=True,
            )

        judge_code, bench_name, judge_error = self._resolve_judge(
            case_data, listing_entry
        )
        if judge_error:
            self._fail_judge_lists(result, judge_error)
            return result

        print(
            f"PROGRESS! Judge-wise lists: bench '{bench_name}' -> judge code {judge_code}",
            flush=True,
        )
        result.daily = self._check_list(
            "Judge-wise cause list",
            self.api.daily_cause_list,
            judge_code,
            bench_name,
            search_terms,
            date,
            result,
        )
        result.regular = self._check_list(
            "Judge-wise regular cause list",
            self.api.regular_cause_list,
            judge_code,
            bench_name,
            search_terms,
            date,
            result,
        )
        if (
            result.regular.status == NOT_FOUND
            and not result.regular.entries_checked
            and listing_entry
        ):
            # No regular list published for the bench, but the case's own history says it's listed.
            result.regular.html = case_html.build_listing_found_html(
                listing_entry, bench_name, date
            )
        return result

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _optional(
        result: CaseLookupResult, label: str, fetch: Callable, args: Tuple, default: Any
    ) -> Any:
        try:
            return fetch(*args)
        except CourtSiteError as e:
            result.issues.append(f"{label} for {result.case_id}: {e.reason}")
            return default

    @staticmethod
    def _listing_for_date(listing_history: List[Dict], date: str) -> Optional[Dict]:
        target = to_api_date(date)
        return next(
            (
                e
                for e in listing_history
                if str(e.get("cl_date", "")).startswith(target)
            ),
            None,
        )

    def _resolve_judge(
        self, case_data: Dict, listing_entry: Optional[Dict]
    ) -> Tuple[Optional[int], str, Optional[str]]:
        """(judge_code, bench_name, error). Prefers the bench the case is listed before on the date."""
        try:
            judges = self.api.active_judges()
        except CourtSiteError as e:
            return None, "", f"judge list unavailable ({e.reason})"

        if listing_entry:  # the bench the case is actually listed before on this date
            details = listing_entry.get("benchDetails") or {}
            bench_name = details.get("bench_name") or case_data.get("bench_name", "")
            code = judge_code_for_bench(listing_entry.get("bench_code"), judges)
            code = code or match_judge_code(bench_name, judges)
            if code:
                return code, bench_name, None

        bench_name = case_data.get("bench_name", "")
        if not bench_name:
            return None, "", "case has no bench assigned"
        code = match_judge_code(bench_name, judges)
        if not code:
            return (
                None,
                bench_name,
                f"could not match bench '{bench_name}' to an active judge",
            )
        return code, bench_name, None

    @staticmethod
    def _check_list(
        label: str,
        fetch: Callable[[int, str], Any],
        judge_code: int,
        bench_name: str,
        search_terms: List[str],
        date: str,
        result: CaseLookupResult,
    ) -> JudgeListOutcome:
        try:
            entries = unwrap_records(fetch(judge_code, date))
        except CourtSiteError as e:
            result.issues.append(f"{label} for {bench_name}: {e.reason}")
            return JudgeListOutcome(error=e.reason, bench_name=bench_name)
        matches = search_entries(entries, search_terms)
        return JudgeListOutcome(
            html=case_html.build_judge_cause_list_html(matches, bench_name, date),
            entries_checked=len(entries),
            bench_name=bench_name,
        )

    @staticmethod
    def _fail_judge_lists(result: CaseLookupResult, reason: str) -> None:
        result.daily = JudgeListOutcome(error=reason)
        result.regular = JudgeListOutcome(error=reason)
        result.issues.append(f"Judge-wise cause lists for {result.case_id}: {reason}")

    @classmethod
    def _fail_all(cls, result: CaseLookupResult, reason: str) -> None:
        result.issues.append(f"Case status for {result.case_id}: {reason}")
        result.daily = JudgeListOutcome(error=reason)
        result.regular = JudgeListOutcome(error=reason)
