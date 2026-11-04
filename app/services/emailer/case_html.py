"""HTML fragments for the email: case status tables and judge-wise listings.

Styled inline to match new.phhc.gov.in (email clients ignore most <style> rules).
"""

from datetime import datetime
from typing import Dict, List, Optional

from app.config import settings


def format_api_date(date_str: Optional[str], fmt: str = "%d-%b-%Y") -> str:
    """Convert API datetime string like '2026-01-14T00:00:00' to display format."""
    if not date_str:
        return ""
    try:
        # Handle both date-only strings and datetime strings
        clean = str(date_str).replace("+05:30", "").split("T")[0]
        dt = datetime.strptime(clean, "%Y-%m-%d")
        return dt.strftime(fmt)
    except (ValueError, AttributeError):
        return str(date_str)


def case_status_url(case_type: str, case_no: str, case_year) -> str:
    """Build a link to the case status page on the new PHHC site."""
    return f"https://new.phhc.gov.in/case-status/case-no?case_no={case_no}&case_type={case_type}&case_year={case_year}"


def case_link(case_type: str, case_no: str, case_year) -> str:
    """Build an <a> tag linking to the case status page."""
    label = f"{case_type}-{case_no}-{case_year}"
    url = case_status_url(case_type, case_no, case_year)
    return f'<a href="{url}">{label}</a>'


def build_case_details_html(
    case_data: Dict,
    listing_history: Optional[List[Dict]] = None,
    related_cases: Optional[List[Dict]] = None,
    judgments: Optional[List[Dict]] = None,
    copy_petition: Optional[Dict] = None,
    impugned_orders: Optional[Dict] = None,
) -> str:
    """
    Generate HTML for case details matching the new.phhc.gov.in layout.

    Sections:
    1. Case Details
    2. Related Cases/Miscellaneous Applications
    3. Case Listing Details
    4. Copy Petition Details
    5. Judgment Details
    6. Impugned Orders
    """
    # Style constants matching the dark navy theme from the site
    hdr = 'style="background-color: #1a2a4a; color: white; padding: 8px; text-align: center;"'
    sub_hdr = 'style="background-color: #2a3a5a; color: white; padding: 6px; text-align: center; font-weight: bold;"'
    lbl = 'style="font-weight: bold; padding: 8px; text-align: left; width: 22%;"'
    val = 'style="padding: 8px; text-align: left;"'
    tbl = 'border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 900px; border: 1px solid #ddd;"'
    hl = 'style="background-color: #ffff00; padding: 8px; text-align: left;"'

    case_type = case_data.get("case_type", "")
    case_no = case_data.get("case_no", "")
    case_year = case_data.get("case_year", "")

    # Build status string: "PENDING on 06-Aug-2025 by HON'BLE MR. JUSTICE ..."
    status_desc = (
        case_data.get("status", {}).get("status_desc", "")
        if isinstance(case_data.get("status"), dict)
        else ""
    )
    status_date = format_api_date(case_data.get("t_status_date"))
    bench_name = case_data.get("bench_name", "")
    status_full = status_desc
    if status_date:
        status_full += f" on {status_date}"
    if bench_name:
        status_full += f" by {bench_name}"

    reg_date = format_api_date(case_data.get("reg_date"))
    diary_no = case_data.get("case_diary_no", "")
    category = case_data.get("category", "")
    cat_desc = case_data.get("cat_desc", "")
    category_full = f"{category} {cat_desc}".strip() if category else cat_desc
    pet_name = case_data.get("pet_name", "").strip()
    res_name = case_data.get("res_name", "").strip()
    party_detail = (
        f"(O&M) {pet_name} Vs {res_name}"
        if pet_name and res_name
        else f"{pet_name} {res_name}".strip()
    )
    pet_adv = case_data.get("pet_adv_name", "") or ""
    pet_adv_enroll = case_data.get("pet_adv_enrollment_year", "") or ""
    if pet_adv and pet_adv_enroll:
        pet_adv = f"{pet_adv} ({pet_adv_enroll})"
    res_adv = case_data.get("res_adv_name", "") or ""
    res_adv_enroll = case_data.get("res_adv_enrollment_year", "") or ""
    if res_adv and res_adv_enroll:
        res_adv = f"{res_adv} ({res_adv_enroll})"
    elif not res_adv and res_adv_enroll:
        res_adv = f"({res_adv_enroll})"
    district = (
        case_data.get("district", {}).get("name", "")
        if isinstance(case_data.get("district"), dict)
        else ""
    )
    list_type = case_data.get("list_type", "")
    list_type_full = {"R": "REGULAR", "O": "ORDINARY", "U": "URGENT"}.get(
        list_type, list_type
    )
    final_order_date = format_api_date(case_data.get("final_order_date_uploaded_on"))

    # Final order link
    final_order_url = case_data.get("order", "")
    if final_order_url and not final_order_url.startswith("http"):
        final_order_url = f"{settings.PHHC_API_BASE_URL}{final_order_url}"

    # Main case detail as a link
    main_case_raw = case_data.get("main_case_filling_no", "")
    main_case_html = ""
    if main_case_raw:
        parts = main_case_raw.split(",")
        if len(parts) == 3:
            main_case_html = case_link(
                parts[0].strip(), parts[1].strip(), parts[2].strip()
            )
        else:
            main_case_html = main_case_raw

    next_date = format_api_date(case_data.get("listing_or_proposal_date"))

    # --- Links at the top ---
    html = "<center>\n"
    if final_order_url and final_order_date:
        html += f'<p><a href="{final_order_url}" style="color: #0066cc; font-weight: bold;">View Judgement Final Order (Dated {final_order_date})</a></p>\n'

    # --- Section 1: Case Details ---
    html += f"""<table {tbl}>
  <tr><td colspan="4" {hdr}>Case Details For Case {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {lbl}>Diary Number</td><td {val}>{diary_no}</td><td {lbl}>Registration Date</td><td {val}>{reg_date}</td></tr>
  <tr><td {lbl}>Category</td><td colspan="3" {val}>{category_full}</td></tr>
  <tr><td {lbl}>Party Detail</td><td colspan="3" {val}>{party_detail}</td></tr>
  <tr><td {lbl}>Advocate Name</td><td {val}>{pet_adv}</td><td {lbl}>District</td><td {val}>{district}</td></tr>
  <tr><td {lbl}>Respondent Advocate Name</td><td {val}>{res_adv}</td><td {lbl}>List Type</td><td {val}>{list_type_full}</td></tr>
  <tr><td {lbl} {hl}>Status</td><td colspan="3" {hl}>{status_full}</td></tr>
  <tr><td {lbl}>Final Order Uploaded On</td><td colspan="3" {val}>{final_order_date}</td></tr>
  <tr><td {lbl}>Main Case Detail</td><td {val}>{main_case_html}</td><td colspan="2"></td></tr>
  <tr><td {lbl} {hl}>Next Date</td><td colspan="3" {hl}>{next_date}</td></tr>
</table>
"""

    # --- Section 2: Related Cases/Miscellaneous Applications ---
    if related_cases:
        html += f"""<br/>
<table {tbl}>
  <tr><td colspan="2" {hdr}>Related Cases/Miscellaneous Applications</td></tr>
"""
        for rc in related_cases:
            doc = rc.get("case_documents", {}) if isinstance(rc, dict) else {}
            rc_type = doc.get("case_type", "")
            rc_no = doc.get("case_no", "")
            rc_year = doc.get("case_year", "")
            rc_link = case_link(rc_type, rc_no, rc_year) if rc_type else ""

            order_details = rc.get("order_details", [])
            order_link_html = ""
            if order_details:
                for od in order_details:
                    od_url = od.get("order", "")
                    if od_url and not od_url.startswith("http"):
                        od_url = f"{settings.PHHC_API_BASE_URL}{od_url}"
                    od_date = format_api_date(od.get("orderdate"))
                    if od_url:
                        date_label = f" Dated {od_date}" if od_date else ""
                        order_link_html += (
                            f' &nbsp;<a href="{od_url}">View Order{date_label}</a>'
                        )

            rc_main = f"IN {case_type}-{case_no}-{case_year}"
            html += f"  <tr><td {val}>{rc_link}{order_link_html}</td><td {val}>{rc_main}</td></tr>\n"
        html += "</table>\n"

    # --- Section 3: Case Listing Details ---
    if listing_history:
        html += f"""<br/>
<table {tbl}>
  <tr><td colspan="3" {hdr}>Case Listing Details</td></tr>
  <tr><td {sub_hdr}>Cause List Date</td><td {sub_hdr}>List Type-Sr. No.</td><td {sub_hdr}>Bench</td></tr>
"""
        for i, entry in enumerate(listing_history):
            cl_date = format_api_date(entry.get("cl_date"))
            cl_type = entry.get("cl_type", "")
            sr_no = entry.get("sr_no", "")
            type_sr = f"{cl_type}:{sr_no}"
            bench = (
                entry.get("benchDetails", {}).get("bench_name", "")
                if isinstance(entry.get("benchDetails"), dict)
                else ""
            )
            row_style = hl if i == 0 else val
            html += f"  <tr><td {row_style}>{cl_date}</td><td {row_style}>{type_sr}</td><td {row_style}>{bench}</td></tr>\n"
        html += "</table>\n"

    # --- Section 4: Copy Petition Details ---
    if copy_petition:
        items = (
            copy_petition.get("items", []) if isinstance(copy_petition, dict) else []
        )
        if items:
            html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Details of Copy Petition Applied in {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {sub_hdr}>Petition Type/No</td><td {sub_hdr}>Petition Date</td><td {sub_hdr}>Applied By</td><td {sub_hdr}>Petition Status</td></tr>
"""
            for item in items:
                pet_code = item.get("pet_code", "")
                petrf_no = item.get("petrf_no", "")
                pet_label = f"{pet_code}:{petrf_no}" if pet_code else str(petrf_no)
                pet_type_no = f'<a href="https://new.phhc.gov.in/copy_petition_search_page?app_no={petrf_no}">{pet_label}</a>'
                pet_date = item.get("pet_date", "")
                pet_type = item.get("pet_type", "")
                applname = item.get("applname", "")
                applied_by = (
                    f"<strong>{pet_type}</strong><br/>{applname}"
                    if pet_type
                    else applname
                )
                pet_status = item.get("pet_status", "")
                html += f"  <tr><td {val}>{pet_type_no}</td><td {val}>{pet_date}</td><td {val}>{applied_by}</td><td {val}>{pet_status}</td></tr>\n"
            html += "</table>\n"

    # --- Section 5: Judgment Details ---
    if judgments:
        html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Judgment Details For Case: {case_type}-{case_no}-{case_year}</td></tr>
  <tr><td {sub_hdr}>Order Date</td><td {sub_hdr}>Order and Case ID</td><td {sub_hdr}>Bench</td><td {sub_hdr}>Judgment Link</td></tr>
"""
        for j in judgments:
            order_date = format_api_date(j.get("orderdate"))
            order_type_code = j.get("order_type", "")
            order_type = {"I": "Interim Order", "F": "Final Order"}.get(
                order_type_code, order_type_code
            )
            j_bench = j.get("bench_name", "")
            order_url = j.get("order", "")
            if order_url and not order_url.startswith("http"):
                order_url = f"{settings.PHHC_API_BASE_URL}{order_url}"
            link_html = f'<a href="{order_url}">View Order</a>' if order_url else ""
            html += f"  <tr><td {val}>{order_date}</td><td {val}>{order_type}</td><td {val}>{j_bench}</td><td {val}>{link_html}</td></tr>\n"
        html += "</table>\n"

    # --- Section 6: Impugned Orders ---
    if (
        impugned_orders
        and isinstance(impugned_orders, dict)
        and impugned_orders.get("authority")
    ):
        imp_date = format_api_date(impugned_orders.get("order_date"))
        if not imp_date or imp_date == "":
            imp_date = "Invalid date"
        imp_type_code = impugned_orders.get("order_type", "")
        imp_type = {"I": "Interim", "F": "Final"}.get(imp_type_code, imp_type_code)
        imp_authority = impugned_orders.get("authority", "")
        imp_district = impugned_orders.get("district", "")
        html += f"""<br/>
<table {tbl}>
  <tr><td colspan="4" {hdr}>Impugned Orders</td></tr>
  <tr><td {sub_hdr}>Order Date</td><td {sub_hdr}>Order Type</td><td {sub_hdr}>Authority</td><td {sub_hdr}>District</td></tr>
  <tr><td {val}>{imp_date}</td><td {val}>{imp_type}</td><td {val}>{imp_authority}</td><td {val}>{imp_district}</td></tr>
</table>
"""

    html += "</center>"
    return html


def build_judge_cause_list_html(
    matching_entries: List[Dict], judge_name: str, date: str
) -> Optional[str]:
    """
    Generate HTML table for matching cause list entries.

    Args:
        matching_entries: Filtered entries from getRegularCauseList
        judge_name: The judge's name for the header
        date: The cause list date

    Returns:
        HTML string if entries found, None otherwise
    """
    if not matching_entries:
        return None

    html = f"""<center>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 700px;" class="case-listing-details">
  <tr><td colspan="7" style="text-align:center; font-weight:bold; background-color: #f2f2f2;">
CAUSE LIST FOR {judge_name} ON {date}
  </td></tr>
  <tr><th>Sr No</th><th>Case</th><th>Petitioner</th><th>Respondent</th><th>Pet. Advocate</th><th>Res. Advocate</th><th>Hearing</th></tr>
"""
    for entry in matching_entries:
        sr_no = entry.get("sr_no", "")
        case = f"{entry.get('case_type', '')}-{entry.get('case_no', '')}-{entry.get('case_year', '')}"
        pet = entry.get("pet_name", "") or ""
        res = entry.get("res_name", "") or ""
        pet_adv = entry.get("pet_adv_name", "") or ""
        res_adv = entry.get("res_adv_name", "") or ""
        hearing = "Yes" if entry.get("hearing_status") == "Y" else "No"
        html += f"  <tr><td>{sr_no}</td><td>{case}</td><td>{pet}</td><td>{res}</td><td>{pet_adv}</td><td>{res_adv}</td><td>{hearing}</td></tr>\n"

    html += "</table></center>"
    return html


def build_listing_found_html(listing_entry: Dict, judge_name: str, date: str) -> str:
    """
    Build a simple HTML confirmation that the case was found in the regular cause list.
    Used as fallback when the full cause list API times out.

    Args:
        listing_entry: The matching entry from case_listing_detail
        judge_name: The judge's bench name
        date: The cause list date

    Returns:
        HTML string confirming the listing
    """
    cl_type = listing_entry.get("cl_type", "REGULAR")
    sr_no = listing_entry.get("sr_no", "N/A")
    bench = (
        listing_entry.get("benchDetails", {}).get("bench_name", judge_name)
        if isinstance(listing_entry.get("benchDetails"), dict)
        else judge_name
    )

    return f"""<center>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 700px;" class="case-listing-details">
  <tr><td colspan="4" style="text-align:center; font-weight:bold; background-color: #f2f2f2;">
{cl_type} CAUSE LIST — {bench} — {date}
  </td></tr>
  <tr><th>Date</th><th>List Type</th><th>Sr No</th><th>Bench</th></tr>
  <tr style="background-color: #ffff00;">
<td>{date}</td><td>{cl_type}</td><td>{sr_no}</td><td>{bench}</td>
  </tr>
</table></center>"""
