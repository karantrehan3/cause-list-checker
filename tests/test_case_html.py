import pytest

from app.managers import case_html
from tests.fakes import ENTRY


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-01-14T00:00:00", "14-Jan-2026"),
        ("2026-01-14T00:00:00+05:30", "14-Jan-2026"),
        ("2026-01-14", "14-Jan-2026"),
        ("03-SEP-2013", "03-SEP-2013"),  # unparseable: returned as-is
        (None, ""),
        ("", ""),
    ],
)
def test_format_api_date(raw, expected):
    assert case_html.format_api_date(raw) == expected


def test_case_link_points_to_case_status():
    assert case_html.case_link("CR", "1", "2020") == (
        '<a href="https://new.phhc.gov.in/case-status/case-no?case_no=1&case_type=CR&case_year=2020">CR-1-2020</a>'
    )


FULL_CASE = {
    "case_type": "CR",
    "case_no": "2227",
    "case_year": 2010,
    "status": {"status_desc": "PENDING"},
    "t_status_date": "2025-08-06T00:00:00",
    "bench_name": "HON'BLE MR. JUSTICE VIKAS SURI",
    "reg_date": "2010-04-01",
    "case_diary_no": 488500,
    "category": "30.32",
    "cat_desc": "MISC. MATTERS",
    "pet_name": "HARYANA WAKF BOARD ",
    "res_name": "VISHNU MITTAR",
    "pet_adv_name": "JAI BHAGWAN",
    "pet_adv_enrollment_year": "P-57-1998",
    "res_adv_name": "",
    "res_adv_enrollment_year": "",
    "district": {"name": "AMBALA"},
    "list_type": "R",
    "final_order_date_uploaded_on": "2010-11-09",
    "order": "/orders/final.pdf",
    "main_case_filling_no": "CR,4388,2003",
    "listing_or_proposal_date": "2026-07-01",
}


def test_case_details_html_has_all_sections():
    html = case_html.build_case_details_html(
        FULL_CASE,
        listing_history=[
            {
                "cl_date": "2026-07-01",
                "cl_type": "REGULAR",
                "sr_no": 583,
                "benchDetails": {"bench_name": "HON'BLE MR. JUSTICE VIKAS SURI"},
            }
        ],
        related_cases=[
            {
                "case_documents": {
                    "case_type": "CM",
                    "case_no": "21710-CII",
                    "case_year": 2018,
                },
                "order_details": [{"order": "/o/1.pdf", "orderdate": "2019-01-18"}],
            }
        ],
        judgments=[
            {
                "orderdate": "2020-03-02",
                "order_type": "I",
                "bench_name": "X",
                "order": "/o/2.pdf",
            }
        ],
        copy_petition={
            "items": [
                {
                    "pet_code": "Ordinary",
                    "petrf_no": "262018",
                    "pet_date": "03-SEP-2013",
                    "pet_type": "Public",
                    "applname": "SANTOSH",
                    "pet_status": "Delivered",
                }
            ]
        },
        impugned_orders={
            "authority": "WAKF TRIBUNAL",
            "order_date": "2010-01-22",
            "order_type": "I",
            "district": "AMBALA",
        },
    )

    for expected in [
        "Case Details For Case CR-2227-2010",
        "PENDING on 06-Aug-2025 by HON'BLE MR. JUSTICE VIKAS SURI",
        "(O&M) HARYANA WAKF BOARD Vs VISHNU MITTAR",
        "JAI BHAGWAN (P-57-1998)",
        "REGULAR",
        "AMBALA",
        "View Judgement Final Order (Dated 09-Nov-2010)",
        "CR-4388-2003",
        "Related Cases/Miscellaneous Applications",
        "View Order Dated 18-Jan-2019",
        "Case Listing Details",
        "REGULAR:583",
        "Details of Copy Petition Applied in CR-2227-2010",
        "Ordinary:262018",
        "Judgment Details For Case: CR-2227-2010",
        "Interim Order",
        "Impugned Orders",
        "WAKF TRIBUNAL",
    ]:
        assert expected in html, expected


def test_case_details_html_minimal_case_skips_optional_sections():
    html = case_html.build_case_details_html(
        {"case_type": "CR", "case_no": "1", "case_year": 2020}
    )

    assert "Case Details For Case CR-1-2020" in html
    for section in [
        "Related Cases",
        "Case Listing Details",
        "Copy Petition",
        "Judgment Details",
        "Impugned Orders",
    ]:
        assert section not in html


def test_judge_cause_list_html():
    assert case_html.build_judge_cause_list_html([], "JUDGE", "05/11/2026") is None

    html = case_html.build_judge_cause_list_html([ENTRY], "JUDGE", "05/11/2026")
    assert "CAUSE LIST FOR JUDGE ON 05/11/2026" in html
    assert "<td>583</td><td>CR-2227-2010</td>" in html


def test_listing_found_html_uses_listing_bench():
    html = case_html.build_listing_found_html(
        {"cl_type": "REGULAR", "sr_no": 583, "benchDetails": {"bench_name": "BENCH A"}},
        "FALLBACK",
        "01/07/2026",
    )

    assert "REGULAR CAUSE LIST — BENCH A — 01/07/2026" in html
    assert "<td>583</td>" in html
