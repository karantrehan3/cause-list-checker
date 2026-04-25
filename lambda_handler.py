"""
AWS Lambda handler for Cause List Checker.

Triggered by EventBridge (CloudWatch Events) on a cron schedule.
Each EventBridge rule passes search config via the "detail" field, so one
Lambda function handles multiple search configurations.

Environment variables (set in Lambda configuration):
    CASE_SEARCH_URL, CL_BASE_URL, CL_FORM_ACTION_URL,
    CL_JUDGE_WISE_REGULAR_URL, EMAIL_RECIPIENTS, PHHC_API_BASE_URL,
    SENDER_EMAIL, SENDER_PASSWORD, SENDER_NAME, SMTP_SERVER, SMTP_PORT

EventBridge rule input (JSON) — passed as event["detail"]:
    {
        "search_terms": ["Vishnu Mittar", "CR-2227-2010"],
        "recipient_emails": ["user@example.com"],          // optional, falls back to EMAIL_RECIPIENTS
        "case_details": {"type": "CR", "no": "2227", "year": "2010"}  // optional
    }
"""

import json
import traceback
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.managers.pdf_searcher import PDFSearcher
from app.managers.scraper import Scraper
from app.services.emailer import Emailer
from app.utils.error_handler import ErrorHandler
from app.utils.helpers import get_weekend_dates

IST = timezone(timedelta(hours=5, minutes=30))


def _build_context(
    search_terms, date, existing_pdfs, new_pdfs, results,
    case_details_html, term_found_in_regular_cause_list, case_status_url,
):
    all_pdfs = existing_pdfs + new_pdfs
    return {
        "search_terms": search_terms,
        "date": date,
        "results": results,
        "pdfs": all_pdfs,
        "existing_pdfs": existing_pdfs,
        "new_pdfs": new_pdfs,
        "case_details_html": case_details_html,
        "term_found_in_regular_cause_list": term_found_in_regular_cause_list,
        "urls": {
            "cl_base_url": settings.CL_BASE_URL,
            "case_search_url": settings.CASE_SEARCH_URL,
            "cl_judge_wise_regular_url": settings.CL_JUDGE_WISE_REGULAR_URL,
            "case_status_url": case_status_url or settings.CASE_SEARCH_URL,
        },
    }


def process_date(scraper, searcher, emailer, error_handler, search_terms, date, recipients, case_details):
    try:
        existing_pdfs, new_pdfs = scraper.parse_table_and_download_pdfs(date, search_terms)
        pdfs = existing_pdfs + new_pdfs

        case_result = scraper.get_case_details_and_judge_details(case_details, search_terms, date)
        case_details_html, term_found_in_regular_cause_list, case_status_url = (
            case_result if case_result is not None else (None, "", "")
        )

        if not pdfs:
            results = []
            print(f"ALERT! No Cause Lists found for {date}")
        else:
            print(f"PROGRESS! {len(pdfs)} Cause List(s) found for {date}")
            results = searcher.search_pdf(pdfs)
            print(f"PROGRESS! Search complete for {date}: {len(results)} result(s)")

        context = _build_context(
            search_terms, date, existing_pdfs, new_pdfs, results,
            case_details_html, term_found_in_regular_cause_list, case_status_url,
        )
        emailer.send_email(
            recipients=recipients,
            subject=f"Cause List Search Results for {search_terms} on {date}",
            template_name="cause_list_template.html",
            context=context,
        )
        print(f"SUCCESS! Email sent for {date}")
        return True

    except Exception as e:
        error_handler.handle_exception(e, {"search_terms": search_terms, "date": date})
        print(f"ERROR! Failed for {date}: {e}")
        traceback.print_exc()
        return False


def handler(event, context):
    """AWS Lambda entry point. Config comes from EventBridge event detail."""
    detail = event.get("detail", event)

    search_terms = detail.get("search_terms", [])
    if not search_terms:
        return {"statusCode": 400, "body": "search_terms is required"}

    case_details = detail.get("case_details")
    recipients = detail.get("recipient_emails") or settings.EMAIL_RECIPIENTS.split(",")

    tomorrow_ist = (datetime.now(IST) + timedelta(days=1)).strftime("%d/%m/%Y")
    dates_to_process = get_weekend_dates(tomorrow_ist)

    print(f"Search terms: {search_terms}")
    print(f"Case details: {case_details}")
    print(f"Recipients: {recipients}")
    print(f"Dates to process: {dates_to_process}")

    scraper = Scraper()
    searcher = PDFSearcher(search_terms=search_terms)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, recipients)

    results_summary = []
    for date in dates_to_process:
        success = process_date(
            scraper, searcher, emailer, error_handler,
            search_terms, date, recipients, case_details,
        )
        results_summary.append({"date": date, "success": success})

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Processed {len(dates_to_process)} date(s)",
            "results": results_summary,
        }),
    }
