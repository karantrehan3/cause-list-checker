"""Everything we check for one case on one date: case status + judge-wise lists.

Every check reports one of: found / not found / unavailable (with a reason),
so a failed request can never be mistaken for "not listed".
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.clients.court_http import CourtSiteError
from app.clients.phhc_api import PhhcApi, to_api_date
from app.managers.cause_list_entries import ListedBench, listed_bench_for_case
from app.managers.judge_cause_list_manager import (
    JudgeCauseListManager,
    JudgeListOutcome,
)
from app.services.emailer import case_html


@dataclass
class CaseLookupResult:
    case_id: str
    case_status_url: str
    case_details_html: Optional[str] = None
    daily: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    regular: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    issues: List[str] = field(default_factory=list)
    listing_entry: Optional[Dict] = None


def case_id_for(case_details: Dict[str, str]) -> str:
    return f"{case_details['type']}-{case_details['no']}-{case_details['year']}"


def listed_bench_from(
    results: List[Dict[str, Any]], case_details: Optional[Dict[str, str]]
) -> Optional[ListedBench]:
    if not case_details:
        return None
    return listed_bench_for_case(results, case_id_for(case_details))


class CaseManager:
    def __init__(
        self,
        api: Optional[PhhcApi] = None,
        judge_lists: Optional[JudgeCauseListManager] = None,
    ):
        self.api = api or PhhcApi()
        self.judge_lists = judge_lists or JudgeCauseListManager(self.api)

    def lookup(
        self,
        case_details: Optional[Dict[str, str]],
        search_terms: List[str],
        date: str,
        listed_bench: Optional[ListedBench] = None,
    ) -> Optional[CaseLookupResult]:
        """Case status + judge-wise lists; None when no case number was given."""
        if not case_details:
            return None
        case_type, case_no, case_year = (
            case_details["type"],
            case_details["no"],
            case_details["year"],
        )
        result = CaseLookupResult(
            case_id=case_id_for(case_details),
            case_status_url=case_html.case_status_url(case_type, case_no, case_year),
        )

        try:
            case_data = self.api.case_info(case_type, case_no, case_year)
        except CourtSiteError as e:
            reason = f"case status unavailable ({e.reason})"
            result.issues.append(f"Case status for {result.case_id}: {reason}")
            unavailable = JudgeCauseListManager.unavailable(reason)
            result.daily, result.regular = unavailable.daily, unavailable.regular
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
        result.listing_entry = listing_entry
        if listing_entry:
            print(
                f"PROGRESS! {result.case_id} is in the listing history for {date}",
                flush=True,
            )

        judge_lists = self.judge_lists.check(
            case_data, listing_entry, search_terms, date, listed_bench
        )
        result.daily, result.regular = judge_lists.daily, judge_lists.regular
        result.issues += judge_lists.issues
        return result

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
