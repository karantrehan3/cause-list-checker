"""Shared test doubles and sample court data."""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from app.managers.court_http import CourtSiteError

CASE = {"type": "CR", "no": "2227", "year": "2010"}
BENCH = "HON'BLE MR. JUSTICE VIKAS SURI"
JUDGES = [
    {"judge_code": 458, "judge_name": "THE CHIEF JUSTICE", "bench_code": 5189},
    {"judge_code": 650, "judge_name": "MR. JUSTICE VIKAS SURI", "bench_code": 4485},
    {"judge_code": 701, "judge_name": "MR. JUSTICE OTHER JUDGE", "bench_code": 9001},
]
CASE_DATA = {
    "case_type": "CR",
    "case_no": "2227",
    "case_year": 2010,
    "bench_name": BENCH,
    "pet_name": "HARYANA WAKF BOARD",
    "res_name": "VISHNU MITTAR",
}
ENTRY = {
    "sr_no": 583,
    "case_type": "CR",
    "case_no": "2227",
    "case_year": 2010,
    "pet_name": "(O&M) HARYANA WAKF BOARD",
    "res_name": "VISHNU MITTAR",
    "pet_adv_name": "JAI BHAGWAN",
    "res_adv_name": None,
}
OTHER = {
    "sr_no": 1,
    "case_type": "CR",
    "case_no": "1",
    "case_year": 2026,
    "pet_name": "STATE OF PUNJAB",
    "res_name": "SOMEONE ELSE",
    "pet_adv_name": "OTHER ADVOCATE",
    "res_adv_name": None,
}


def wrapped(*entries: Dict) -> List[Dict]:
    """getCauseList / getRegularCauseList response shape."""
    return [{"header": {"bench_name": BENCH}, "records": list(entries), "vc_info": {}}]


class FakeApi:
    """Stand-in for PhhcApi: return values or CourtSiteError per method."""

    def __init__(self, **overrides: Any):
        self.calls: List[tuple] = []
        self.values: Dict[str, Any] = {
            "case_info": dict(CASE_DATA),
            "listing_history": [],
            "related_cases": [],
            "judgments": [],
            "copy_petitions": {},
            "impugned_orders": {},
            "active_judges": JUDGES,
            "daily_cause_list": wrapped(OTHER),
            "regular_cause_list": [],
        }
        self.values.update(overrides)

    def __getattr__(self, name: str):
        if name not in self.values:
            raise AttributeError(name)

        def method(*args: Any) -> Any:
            self.calls.append((name, args))
            value = self.values[name]
            if isinstance(value, CourtSiteError):
                raise value
            return value

        return method


def http_response(
    status: int = 200,
    content: bytes = b"",
    headers: Optional[Dict] = None,
    json_data: Any = None,
):
    response = MagicMock()
    response.status_code = status
    response.content = content
    response.text = content.decode("latin-1")
    response.headers = headers or {}
    if json_data is not None:
        response.json.return_value = json_data
    else:
        response.json.side_effect = ValueError("no json")
    return response
