"""Entry extraction from cause-list page text (layouts copied from real PHHC lists)."""

import pytest

from app.managers.cause_list_entries import (
    ListedBench,
    compile_term,
    find_entries,
    listed_bench_for_case,
)

REGULAR_P111 = """\
REGULAR SUPPL. S.B. CAUSE LIST FOR THE THURSDAY DATED 12/11/2026      CR NO 12

HON'BLE MR. JUSTICE VIRINDER AGGARWAL
381 ** RSA-592-2011
MOHALI (SAS NAGAR)
[11-Nov-26]
RATTAN SINGH & ANR. V/S GRAM
PANCHAYAT OF VILL. NADIALI, TEH
"""

REGULAR_P113 = """\
403 ** (SOC)

RSA-4203-2011
SANGRUR
[11-Nov-26]
(O&M) VIJAY LUXAMI V/S KARAMJIT
KAUR AND ORS ( LR OF ROOP SINGH)
 NARESH K. JOSHI,

404 ** RSA-4610-2011
SANGRUR
[11-Nov-26]
KRISHAN CHAND V/S TARSEM CHAND
AND ORS.
, ASHISH KASHYAP, GAGAN PREET KAUR,,
BALDEV RAJ MAHAJAN, RAJESH

CM-13421-C-2011

 BALDEV RAJ MAHAJAN,

405 ** RSA-4788-2011
AMRITSAR
[11-Nov-26]
KULWANT SINGH AND ORS V/S
RAJBIR KAUR AND ORS
"""

LOK_ADALAT = """\
LOK ADALAT PETITIONS FOR THE THURSDAY DATED 12/11/2026      CR NO None

HON'BLE LOK ADALAT BENCH - 2

501 ***  HISSAR
[11-Nov-26]
CWP-3600-2008
(GOVT SER HRY)
KRISHAN CHANDER AND
ORS.  V/S STATE OF
HARYANA AND ANR.
502 ***  SANGRUR
"""

TERMS = ["Krishan Chand", "RSA-4610-2011"]


def test_both_terms_on_one_entry_give_one_row_with_full_context():
    found_pages, rows = find_entries([REGULAR_P111, "", REGULAR_P113], TERMS)

    assert found_pages == {"Krishan Chand": [3], "RSA-4610-2011": [3]}
    assert len(rows) == 1
    row = rows[0]
    assert row["terms"] == TERMS
    assert row["item_no"] == "404"
    assert row["case_no"] == "RSA-4610-2011"
    assert row["page"] == 3
    assert row["bench"] == ["HON'BLE MR. JUSTICE VIRINDER AGGARWAL"]
    assert row["court_room"] == "12"
    assert row["is_entry"] is True
    assert row["lines"][0] == "404 ** RSA-4610-2011"
    assert row["lines"][-1] == "BALDEV RAJ MAHAJAN,"
    assert not any("405" in line for line in row["lines"])


def test_bench_title_variants_match_regardless_of_mr_ms_mrs():
    for title in ("MS.", "MRS.", "MR", "DR."):
        page = REGULAR_P111.replace("MR.", title) + REGULAR_P113
        _, rows = find_entries([page], ["RSA-4610-2011"])
        assert rows[0]["bench"] == [f"HON'BLE {title} JUSTICE VIRINDER AGGARWAL"]


def test_division_bench_lists_both_judges():
    header = (
        "CAUSE LIST DATED 12/11/2026 CR NO 1\n"
        "HON'BLE THE CHIEF JUSTICE\n \nHON'BLE MR. JUSTICE SANJIV BERRY\n"
    )
    _, rows = find_entries([header + REGULAR_P113], ["RSA-4610-2011"])

    assert rows[0]["bench"] == [
        "HON'BLE THE CHIEF JUSTICE",
        "HON'BLE MR. JUSTICE SANJIV BERRY",
    ]
    assert rows[0]["court_room"] == "1"


def test_court_room_number_wrapped_onto_next_line():
    header = (
        "DAILY VII D.B. MOTION PETITION FOR THE THURSDAY DATED 12/11/2026      CR NO \n"
        "7 \nHON'BLE MR. JUSTICE JASGURPREET SINGH PURI \n"
    )
    _, rows = find_entries([header + REGULAR_P113], ["RSA-4610-2011"])

    assert rows[0]["court_room"] == "7"


def test_lok_adalat_bench_and_missing_court_room():
    _, rows = find_entries([LOK_ADALAT], ["CWP-3600-2008"])

    assert rows[0]["bench"] == ["HON'BLE LOK ADALAT BENCH - 2"]
    assert rows[0]["court_room"] is None
    assert rows[0]["item_no"] == "501"
    assert rows[0]["lines"][-1] == "HARYANA AND ANR."


def test_names_match_whole_words_only():
    found_pages, rows = find_entries([LOK_ADALAT], ["Krishan Chand"])

    assert found_pages == {"Krishan Chand": []}
    assert rows == []


def test_names_match_across_a_line_break():
    page = "12 ** CWP-1-2020\nPETITION OF KRISHAN\nCHAND V/S STATE\n"
    found_pages, rows = find_entries([page], ["krishan chand"])

    assert found_pages == {"krishan chand": [1]}
    assert rows[0]["item_no"] == "12"


@pytest.mark.parametrize(
    "text",
    [
        "CR-2227-2010",
        "CR-2227-\n2010",
        "CR-\n2227-2010",
        "CR - 2227 - 2010",
        "**CR-2227-2010",
    ],
)
def test_case_number_matches_when_wrapped_or_spaced_at_hyphens(text):
    assert compile_term("CR-2227-2010").search(text)


def test_case_number_does_not_match_a_different_number():
    assert not compile_term("CR-2227-2010").search("CR-2227-2011")
    assert not compile_term("CR-2227-2010").search("CR-22270-2010")


def test_wrapped_case_number_is_found_in_its_entry():
    page = "141 ** AMBALA\n[11-Nov-26]\nFAO-6127-\n2026\nKRISHAN CHAND V/S X\n"
    found_pages, rows = find_entries([page], ["FAO-6127-2026"])

    assert found_pages == {"FAO-6127-2026": [1]}
    assert rows[0]["item_no"] == "141"


def test_case_numbers_stay_substring_matches():
    assert compile_term("RSA-4610").search("**RSA-4610-2011")
    assert not compile_term("Krishan Chand").search("KRISHAN CHANDER")
    assert compile_term("Krishan Chand").search("KRISHAN CHAND,")


def test_roman_and_single_star_entry_markers():
    page = (
        "141 V FARIDKOT  \n[11-Nov-26] \nCRR-1908-2004 \nLAKHWINDER SINGH V/S \n"
        "732 II (ON BAIL) \n \nCRA-S-176-SB-2008 \nDILBAGH SINGH V/S \n"
        "218 *  \nLPA-65-2022 \nARVIND KUMAR SHARMA V/S \n"
    )
    _, rows = find_entries([page], ["Lakhwinder", "Dilbagh", "Arvind"])

    assert [(r["item_no"], r["case_no"]) for r in rows] == [
        ("141", "CRR-1908-2004"),
        ("732", "CRA-S-176-SB-2008"),
        ("218", "LPA-65-2022"),
    ]


def test_tagged_item_is_its_own_entry():
    page = (
        "406 ** RSA-4836-2011 \nTHAKUR SINGH V/S SADHU \n"
        "406.1 WITH RSA-4837-2011  THAKUR SINGH ETC V/S SADHU \n GAURAV CHOPRA,\n"
    )
    _, rows = find_entries([page], ["RSA-4837-2011"])

    assert rows[0]["item_no"] == "406.1"
    assert rows[0]["lines"] == [
        "406.1 WITH RSA-4837-2011 THAKUR SINGH ETC V/S SADHU",
        "GAURAV CHOPRA,",
    ]


def test_entry_spanning_a_page_break_reports_both_pages():
    first, second = REGULAR_P113.split("CM-13421-C-2011")
    _, rows = find_entries([first, "CM-13421-C-2011" + second], ["RSA-4610-2011"])

    assert rows[0]["page"] == 1
    assert rows[0]["last_page"] == 2
    assert "CM-13421-C-2011" in rows[0]["lines"]


def test_wrapped_case_number_is_rejoined():
    page = "1102.1 WITH CRM-W-1130-\n2026 \nSOME PARTY V/S STATE\n"
    _, rows = find_entries([page], ["SOME PARTY"])

    assert rows[0]["case_no"] == "CRM-W-1130-2026"


def test_hit_outside_any_entry_falls_back_to_three_lines_around():
    page = "\n".join(f"note line {i}" for i in range(10)) + "\nKRISHAN CHAND notice\n"
    page += "\n".join(f"tail {i}" for i in range(10))
    _, rows = find_entries([page], ["Krishan Chand"])

    row = rows[0]
    assert row["is_entry"] is False
    assert row["item_no"] is None
    assert row["lines"] == [
        "note line 7",
        "note line 8",
        "note line 9",
        "KRISHAN CHAND notice",
        "tail 0",
        "tail 1",
        "tail 2",
    ]


def test_hit_in_bench_header_is_not_attributed_to_previous_entry():
    page = REGULAR_P113 + "HON'BLE MR. JUSTICE KRISHAN CHAND SHARMA\n12 ** CWP-1-2020\n"
    _, rows = find_entries([page], ["Krishan Chand"])

    assert [r["is_entry"] for r in rows] == [True, False]
    assert rows[0]["item_no"] == "404"


def test_rows_with_more_terms_come_first_then_document_order():
    page = REGULAR_P113.replace("KULWANT SINGH", "KRISHAN CHAND")
    _, rows = find_entries([page], TERMS)

    assert [r["item_no"] for r in rows] == ["404", "405"]
    assert rows[1]["terms"] == ["Krishan Chand"]


def test_long_entry_is_truncated():
    page = "1 ** CWP-1-2020\nKRISHAN CHAND V/S X\n" + "".join(
        f"CM-{i}-C-2020\n" for i in range(100)
    )
    _, rows = find_entries([page], ["Krishan Chand"])

    assert rows[0]["truncated"] is True
    assert len(rows[0]["lines"]) == 30


# (x, text) per line in PDF reading order, copied from the real 12/11/2026 lists.
REGULAR_404_POSITIONED = [
    (28, "404 ** RSA-4610-2011"),
    (57, "SANGRUR"),
    (57, "[11-Nov-26]"),
    (168, "KRISHAN CHAND V/S TARSEM CHAND"),
    (168, "AND ORS."),
    (362, ", ASHISH KASHYAP, GAGAN PREET KAUR,,"),
    (362, "BALDEV RAJ MAHAJAN, RAJESH"),
    (362, "GAUR, MANAV BAJAJ,"),
    (57, "CM-13421-C-2011"),
    (362, "BALDEV RAJ MAHAJAN,"),
    (28, "405 ** RSA-4788-2011"),
]

ORDINARY_296_POSITIONED = [
    (28, "296 **"),
    (73, "SRI MUKTSAR"),
    (73, "SAHIB"),
    (73, "[04-Nov-26]"),
    (167, "CWP-17712-2026"),
    (167, "(HUIDPB)"),
    (306, "MS SETH BUDHA MAL"),
    (306, "KRISHAN CHAND, V/S"),
    (306, "PUNJAB STATE"),
    (445, "AKSHAY KUMAR GOEL ,"),
    (445, "DEEPALI PURI"),
]


def test_entry_is_split_into_case_parties_advocates_as_printed():
    _, rows = find_entries([REGULAR_404_POSITIONED], ["RSA-4610-2011"])

    assert rows[0]["columns"] == {
        "case": ["404 ** RSA-4610-2011", "SANGRUR", "[11-Nov-26]", "CM-13421-C-2011"],
        "parties": ["KRISHAN CHAND V/S TARSEM CHAND", "AND ORS."],
        "advocates": [
            ", ASHISH KASHYAP, GAGAN PREET KAUR,,",
            "BALDEV RAJ MAHAJAN, RAJESH",
            "GAUR, MANAV BAJAJ,",
            "BALDEV RAJ MAHAJAN,",
        ],
    }


def test_five_column_layout_folds_left_columns_into_case():
    _, rows = find_entries([ORDINARY_296_POSITIONED], ["Krishan Chand"])

    columns = rows[0]["columns"]
    assert columns["case"] == [
        "296 **",
        "SRI MUKTSAR",
        "SAHIB",
        "[04-Nov-26]",
        "CWP-17712-2026",
        "(HUIDPB)",
    ]
    assert columns["parties"] == [
        "MS SETH BUDHA MAL",
        "KRISHAN CHAND, V/S",
        "PUNJAB STATE",
    ]
    assert columns["advocates"] == ["AKSHAY KUMAR GOEL ,", "DEEPALI PURI"]


def test_entry_spanning_pages_keeps_columns_from_both_pages():
    first, second = REGULAR_404_POSITIONED[:7], REGULAR_404_POSITIONED[7:]
    _, rows = find_entries([first, second], ["RSA-4610-2011"])

    assert rows[0]["columns"]["case"][-1] == "CM-13421-C-2011"
    assert rows[0]["columns"]["advocates"][-1] == "BALDEV RAJ MAHAJAN,"


def test_no_columns_without_positions_or_with_fewer_than_three():
    _, plain = find_entries([REGULAR_P113], ["RSA-4610-2011"])
    two_cols = [(28, "1 ** CWP-1-2020"), (200, "KRISHAN CHAND V/S STATE")]
    _, narrow = find_entries([two_cols], ["Krishan Chand"])

    assert plain[0]["columns"] is None
    assert narrow[0]["columns"] is None


def test_context_rows_have_no_columns():
    page = [(28, "note"), (200, "KRISHAN CHAND notice"), (400, "x")]
    _, rows = find_entries([page], ["Krishan Chand"])

    assert rows[0]["is_entry"] is False
    assert rows[0]["columns"] is None


def _result(name, rows):
    return {"pdf_name": name, "matches": rows}


def test_listed_bench_taken_from_entry_with_the_case_number():
    _, rows = find_entries([REGULAR_P111 + REGULAR_P113], TERMS)

    bench = listed_bench_for_case(
        [_result("Regular | Supplementary List", rows)], "rsa-4610-2011"
    )

    assert bench == ListedBench(
        name="HON'BLE MR. JUSTICE VIRINDER AGGARWAL",
        source="Regular | Supplementary List, item 404, p. 1",
        is_regular_list=True,
    )


def test_listed_bench_none_when_case_not_in_any_entry():
    _, rows = find_entries([REGULAR_P111 + REGULAR_P113], ["Krishan Chand"])
    other = [{**rows[0], "case_no": "RSA-1-2011"}]

    assert listed_bench_for_case([_result("X", other)], "RSA-4610-2011") is None
    assert listed_bench_for_case([], "RSA-4610-2011") is None
