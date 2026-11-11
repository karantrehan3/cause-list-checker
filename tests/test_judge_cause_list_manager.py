import pytest

from app.managers.judge_cause_list_manager import (
    entry_search_text,
    judge_code_for_bench,
    match_judge_code,
    normalize_judge_name,
    search_entries,
    unwrap_records,
)
from tests.fakes import ENTRY, JUDGES, OTHER, wrapped

CONNECTED_MAIN = {
    **OTHER,
    "connected_cases": [
        {
            "pcase_type": "CR",
            "pcase_no": "1",
            "pcase_year": 2026,
            "scase_type": "CM",
            "scase_no": "5213-CII",
            "scase_year": 2026,
            "pet_name": "RAVINDER RAI",
            "res_name": "GURINDER SINGH",
            "pet_adv_name": "DIVANSHU JAIN",
            "res_adv_name": None,
        },
        {
            "pcase_type": "CR",
            "pcase_no": "2227",
            "pcase_year": 2010,
            "party": None,
            "adv": "TAGGED ADVOCATE",
        },
        "not-a-dict",
    ],
}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("HON'BLE MR. JUSTICE VIKAS SURI", "MR. JUSTICE VIKAS SURI"),
        ("hon'ble  MR.  JUSTICE  X (Court Room No. 29)", "MR. JUSTICE X"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_judge_name(raw, expected):
    assert normalize_judge_name(raw) == expected


def test_match_judge_code_exact():
    assert match_judge_code("HON'BLE MR. JUSTICE VIKAS SURI", JUDGES) == 650


def test_match_judge_code_substring_fallback():
    assert match_judge_code("HON'BLE MR. JUSTICE VIKAS SURI AND ANOTHER", JUDGES) == 650


@pytest.mark.parametrize("name", ["", "HON'BLE MS. JUSTICE NOBODY"])
def test_match_judge_code_none(name):
    assert match_judge_code(name, JUDGES) is None


@pytest.mark.parametrize(
    "bench_code, expected",
    [(4485, 650), ("4485", 650), (1, None), (None, None), ("", None)],
)
def test_judge_code_for_bench(bench_code, expected):
    assert judge_code_for_bench(bench_code, JUDGES) == expected


def test_unwrap_records_flattens_blocks_and_keeps_flat_lists():
    assert unwrap_records(wrapped(OTHER) + wrapped(ENTRY)) == [OTHER, ENTRY]
    assert unwrap_records([OTHER, ENTRY]) == [OTHER, ENTRY]


@pytest.mark.parametrize("data", [None, {}, "x", []])
def test_unwrap_records_non_lists_are_empty(data):
    assert unwrap_records(data) == []


def test_entry_search_text_includes_case_id_parties_and_connected_cases():
    text = entry_search_text(CONNECTED_MAIN)

    for expected in [
        "cr-1-2026",
        "state of punjab",
        "cm-5213-cii-2026",
        "ravinder rai",
        "divanshu jain",
        "cr-2227-2010",
        "tagged advocate",
    ]:
        assert expected in text


@pytest.mark.parametrize(
    "term", ["CR-2227-2010", "cr-2227-2010", "Vishnu Mittar", "jai bhagwan"]
)
def test_search_matches_main_entry_fields(term):
    assert search_entries([OTHER, ENTRY], [term]) == [ENTRY]


@pytest.mark.parametrize(
    "term", ["CM-5213-CII-2026", "Gurinder Singh", "Tagged Advocate"]
)
def test_search_matches_connected_cases(term):
    assert search_entries([ENTRY, CONNECTED_MAIN], [term]) == [CONNECTED_MAIN]


def test_search_no_match_and_blank_terms():
    assert search_entries([OTHER, ENTRY], ["CR-9999-2000"]) == []
    assert search_entries([OTHER, ENTRY], ["", None]) == []


def test_search_names_match_whole_words_like_the_pdf_search():
    chander = {**ENTRY, "pet_name": "KRISHAN CHANDER (DECEASED) THRU LRS"}
    chand = {**ENTRY, "pet_name": "KRISHAN CHAND V/S TARSEM CHAND"}

    assert search_entries([chander, chand], ["Krishan Chand"]) == [chand]


def test_manager_unavailable_reports_one_issue_per_case():
    from app.managers.judge_cause_list_manager import JudgeCauseListManager

    result = JudgeCauseListManager.unavailable(
        "judge list unavailable (timed out)",
        {"case_type": "CR", "case_no": "2227", "case_year": 2010},
    )

    assert result.daily.status == result.regular.status == "unavailable"
    assert result.issues == [
        "Judge-wise cause lists for CR-2227-2010: judge list unavailable (timed out)"
    ]
