"""Pure helpers for judge-wise cause lists: judge matching, unwrapping, searching."""

import re
from typing import Any, Dict, Iterable, List, Optional

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
    """Entries where any search term appears (case-insensitive), incl. connected cases."""
    terms = [t.lower() for t in search_terms if t]
    return [e for e in entries if any(t in entry_search_text(e) for t in terms)]
