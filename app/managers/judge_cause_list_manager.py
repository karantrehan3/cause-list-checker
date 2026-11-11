"""Judge-wise cause lists (daily + regular) for the bench hearing a case.

Module-level functions are pure helpers (judge matching, unwrapping, search);
JudgeCauseListManager runs the checks against the court API.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.clients.court_http import CourtSiteError
from app.clients.phhc_api import PhhcApi
from app.managers.cause_list_entries import ListedBench
from app.services.emailer import case_html
from app.utils.search_terms import compile_term

FOUND, NOT_FOUND, UNAVAILABLE = "found", "not_found", "unavailable"
LISTING_HISTORY_SOURCE = "case listing history"
ASSIGNED_BENCH_SOURCE = "case's assigned bench"

Entry = Dict[str, Any]

_ENTRY_TEXT_FIELDS = (
    "pet_name",
    "res_name",
    "pet_adv_name",
    "res_adv_name",
    "extra_adv",
)
_CONNECTED_TEXT_FIELDS = (
    "pet_name",
    "res_name",
    "pet_adv_name",
    "res_adv_name",
    "party",
    "adv",
)


def normalize_judge_name(name: str) -> str:
    """Strip HON'BLE prefix, court room suffix, and normalize whitespace."""
    name = re.sub(r"(?i)^HON'BLE\s+", "", name or "")
    name = re.sub(r"\s*\(Court Room No\.\s*\d+\)\s*$", "", name)
    return " ".join(name.split()).strip()


def match_judge_code(bench_name: str, active_judges: List[Dict]) -> Optional[int]:
    """Map a bench name like "HON'BLE MR. JUSTICE X" to a judge_code (exact, then substring)."""
    cleaned = normalize_judge_name(bench_name).lower()
    if not cleaned:
        return None
    for judge in active_judges:
        if cleaned == judge.get("judge_name", "").lower():
            return judge.get("judge_code")
    for judge in active_judges:
        judge_name = judge.get("judge_name", "").lower()
        if judge_name and (cleaned in judge_name or judge_name in cleaned):
            return judge.get("judge_code")
    return None


def judge_code_for_bench(bench_code: Any, active_judges: List[Dict]) -> Optional[int]:
    """Map a bench_code (as in listing history) to a judge_code."""
    if bench_code in (None, ""):
        return None
    for judge in active_judges:
        if str(judge.get("bench_code")) == str(bench_code):
            return judge.get("judge_code")
    return None


def unwrap_records(data: Any) -> List[Entry]:
    """
    Flatten getCauseList / getRegularCauseList into case entries.

    Current shape: [{"header": {...}, "records": [...], "vc_info": {...}}, ...];
    older responses were a flat list of entries. Supports both.
    """
    if not isinstance(data, list):
        return []
    entries: List[Entry] = []
    for block in data:
        if isinstance(block, dict) and isinstance(block.get("records"), list):
            entries.extend(block["records"])
        elif isinstance(block, dict):
            entries.append(block)
    return entries


def _case_id(case_type: Any, case_no: Any, case_year: Any) -> str:
    return f"{case_type or ''}-{case_no or ''}-{case_year or ''}"


def _texts(record: Dict, fields: Iterable[str]) -> List[str]:
    return [str(record.get(f) or "") for f in fields]


def entry_search_text(entry: Entry) -> str:
    """Lower-cased text of an entry and all its connected cases (CMs, tagged cases)."""
    parts = [
        _case_id(entry.get("case_type"), entry.get("case_no"), entry.get("case_year"))
    ]
    parts += _texts(entry, _ENTRY_TEXT_FIELDS)
    connected = entry.get("connected_cases")
    for case in connected if isinstance(connected, list) else []:
        if not isinstance(case, dict):
            continue
        parts.append(
            _case_id(
                case.get("pcase_type"), case.get("pcase_no"), case.get("pcase_year")
            )
        )
        parts.append(
            _case_id(
                case.get("scase_type"), case.get("scase_no"), case.get("scase_year")
            )
        )
        parts += _texts(case, _CONNECTED_TEXT_FIELDS)
    return " ".join(parts).lower()


def search_entries(entries: List[Entry], search_terms: List[str]) -> List[Entry]:
    patterns = [compile_term(t) for t in search_terms if t and t.strip()]
    return [e for e in entries if any(p.search(entry_search_text(e)) for p in patterns)]


# --- Checks against the court API ---------------------------------------------


@dataclass
class JudgeListOutcome:
    html: Optional[str] = None  # table of matching entries
    error: Optional[str] = None  # why the list could not be checked
    entries_checked: int = 0
    bench_name: str = ""
    bench_source: str = ""

    @property
    def status(self) -> str:
        if self.error:
            return UNAVAILABLE
        return FOUND if self.html else NOT_FOUND


@dataclass(frozen=True)
class ResolvedBench:
    judge_code: Optional[int]
    name: str
    source: str = ""
    error: Optional[str] = None


@dataclass
class JudgeListsResult:
    daily: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    regular: JudgeListOutcome = field(default_factory=JudgeListOutcome)
    issues: List[str] = field(default_factory=list)


class JudgeCauseListManager:
    def __init__(self, api: Optional[PhhcApi] = None):
        self.api = api or PhhcApi()

    def check(
        self,
        case_data: Dict,
        listing_entry: Optional[Dict],
        search_terms: List[str],
        date: str,
        listed_bench: Optional[ListedBench] = None,
    ) -> JudgeListsResult:
        """Search the daily and regular lists of the bench hearing the case on `date`."""
        bench = self.resolve_judge(case_data, listing_entry, listed_bench)
        if bench.error:
            return self.unavailable(bench.error, case_data)

        print(
            f"PROGRESS! Judge-wise lists: bench '{bench.name}' -> judge code {bench.judge_code}",
            flush=True,
        )
        result = JudgeListsResult()
        result.daily = self._check_list(
            "Judge-wise cause list",
            self.api.daily_cause_list,
            bench,
            search_terms,
            date,
            result.issues,
        )
        result.regular = self._check_list(
            "Judge-wise regular cause list",
            self.api.regular_cause_list,
            bench,
            search_terms,
            date,
            result.issues,
        )
        regular_list_missing = result.regular.status == UNAVAILABLE or (
            result.regular.status == NOT_FOUND and not result.regular.entries_checked
        )
        if regular_list_missing:
            result.regular = (
                self._listed_elsewhere(listing_entry, listed_bench, bench, date)
                or result.regular
            )
        return result

    @staticmethod
    def _listed_elsewhere(
        listing_entry: Optional[Dict],
        listed_bench: Optional[ListedBench],
        bench: ResolvedBench,
        date: str,
    ) -> Optional[JudgeListOutcome]:
        if listing_entry:
            html = case_html.build_listing_found_html(listing_entry, bench.name, date)
        elif (
            listed_bench
            and listed_bench.is_regular_list
            and bench.source == listed_bench.source
        ):
            html = case_html.build_pdf_listing_html(
                listed_bench.name, listed_bench.source, date
            )
        else:
            return None
        return JudgeListOutcome(
            html=html, bench_name=bench.name, bench_source=bench.source
        )

    def resolve_judge(
        self,
        case_data: Dict,
        listing_entry: Optional[Dict],
        listed_bench: Optional[ListedBench] = None,
    ) -> ResolvedBench:
        try:
            judges = self.api.active_judges()
        except CourtSiteError as e:
            return ResolvedBench(None, "", error=f"judge list unavailable ({e.reason})")

        if listing_entry:  # the bench the case is actually listed before on this date
            details = listing_entry.get("benchDetails") or {}
            name = details.get("bench_name") or case_data.get("bench_name", "")
            code = judge_code_for_bench(listing_entry.get("bench_code"), judges)
            code = code or match_judge_code(name, judges)
            if code:
                return ResolvedBench(code, name, LISTING_HISTORY_SOURCE)

        if listed_bench:
            code = match_judge_code(listed_bench.name, judges)
            if code:
                return ResolvedBench(code, listed_bench.name, listed_bench.source)

        name = case_data.get("bench_name", "")
        if not name:
            return ResolvedBench(None, "", error="case has no bench assigned")
        code = match_judge_code(name, judges)
        if not code:
            return ResolvedBench(
                None, name, error=f"could not match bench '{name}' to an active judge"
            )
        return ResolvedBench(code, name, ASSIGNED_BENCH_SOURCE)

    @staticmethod
    def unavailable(reason: str, case_data: Optional[Dict] = None) -> JudgeListsResult:
        """Both lists marked unavailable for `reason`, with one issue line."""
        case_data = case_data or {}
        case_id = _case_id(
            case_data.get("case_type"),
            case_data.get("case_no"),
            case_data.get("case_year"),
        )
        return JudgeListsResult(
            daily=JudgeListOutcome(error=reason),
            regular=JudgeListOutcome(error=reason),
            issues=[f"Judge-wise cause lists for {case_id}: {reason}"],
        )

    @staticmethod
    def _check_list(
        label: str,
        fetch: Callable[[int, str], Any],
        bench: ResolvedBench,
        search_terms: List[str],
        date: str,
        issues: List[str],
    ) -> JudgeListOutcome:
        try:
            entries = unwrap_records(fetch(bench.judge_code, date))
        except CourtSiteError as e:
            issues.append(f"{label} for {bench.name}: {e.reason}")
            return JudgeListOutcome(
                error=e.reason, bench_name=bench.name, bench_source=bench.source
            )
        matches = search_entries(entries, search_terms)
        return JudgeListOutcome(
            html=case_html.build_judge_cause_list_html(matches, bench.name, date),
            entries_checked=len(entries),
            bench_name=bench.name,
            bench_source=bench.source,
        )
