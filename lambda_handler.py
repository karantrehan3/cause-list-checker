"""
AWS Lambda handler for Cause List Checker.

Triggered by EventBridge (CloudWatch Events) on a cron schedule.
Each EventBridge rule passes search config via the "detail" field, so one
Lambda function handles multiple search configurations.

Environment variables (set in Lambda configuration):
    CASE_SEARCH_URL, CL_BASE_URL, CL_FORM_ACTION_URL,
    CL_JUDGE_WISE_REGULAR_URL, EMAIL_RECIPIENTS, PHHC_API_BASE_URL,
    SENDER_EMAIL, SENDER_PASSWORD, SENDER_NAME, SMTP_SERVER, SMTP_PORT

EventBridge rule input (JSON) — passed as event["detail"]. Two modes:

    Search (default; "mode" omitted or "search"):
    {
        "search_terms": ["<search term 1>", "<search term 2>"],
        "recipient_emails": ["user@example.com"],          // optional, falls back to EMAIL_RECIPIENTS
        "case_details": {"type": "<type>", "no": "<no>", "year": "<year>"}  // optional
    }

    Daily health check (live read-only checks of every court dependency, emailed as a report):
    {
        "mode": "healthcheck",
        "recipient_emails": ["you@example.com"],           // optional, falls back to SENDER_EMAIL
        "case_details": {"type": "<type>", "no": "<no>", "year": "<year>"}  // optional, enables case checks
    }
"""

import json
import re
import traceback
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.managers.case_manager import CaseManager, listed_bench_from
from app.managers.cause_list_manager import CauseListManager
from app.managers.health_check_manager import HealthCheckManager
from app.managers.pdf_searcher import PDFSearcher
from app.services.emailer import Emailer
from app.services.emailer.health_report import build_health_email
from app.services.emailer.report import build_report
from app.utils.error_handler import ErrorHandler
from app.utils.helpers import get_weekend_dates

IST = timezone(timedelta(hours=5, minutes=30))
SEARCH_MODE, HEALTHCHECK_MODE = "search", "healthcheck"


def _redact_email(email: str) -> str:
    """Redact email: 'john.doe@gmail.com' -> 'jo*****e@gm***com'"""
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    local = parts[0]
    domain = parts[1]
    local_redacted = (
        local[:2] + "*" * max(len(local) - 3, 1) + local[-1]
        if len(local) > 3
        else local[0] + "***"
    )
    domain_redacted = (
        domain[:2] + "***" + domain[-3:] if len(domain) > 5 else domain[0] + "***"
    )
    return f"{local_redacted}@{domain_redacted}"


def process_date(
    cause_list_manager,
    case_manager,
    searcher,
    emailer,
    error_handler,
    search_terms,
    date,
    recipients,
    case_details,
):
    try:
        cause_lists = cause_list_manager.fetch(date, search_terms)

        pdfs = cause_lists.pdfs
        if not pdfs:
            results = []
            print(f"ALERT! No Cause Lists found for {date}")
        else:
            print(f"PROGRESS! {len(pdfs)} Cause List(s) found for {date}")
            results = searcher.search_pdf(pdfs)
            print(f"PROGRESS! Search complete for {date}: {len(results)} result(s)")

        # After the PDF search, which supplies the bench for judge-wise lists.
        case_lookup = case_manager.lookup(
            case_details,
            search_terms,
            date,
            listed_bench=listed_bench_from(results, case_details),
        )

        report = build_report(search_terms, date, cause_lists, results, case_lookup)
        for issue in report["context"]["issues"]:
            print(f"ISSUE! {date}: {issue}")
        emailer.send_email(
            recipients=recipients,
            subject=report["subject"],
            template_name="cause_list_template.html",
            context=report["context"],
        )
        print(f"SUCCESS! Email sent for {date}")
        return True

    except Exception as e:
        error_handler.handle_exception(e, {"search_terms": search_terms, "date": date})
        print(f"ERROR! Failed for {date}: {e}")
        traceback.print_exc()
        return False


def run_health_check(detail):
    """Live checks of every court dependency from AWS, emailed as a daily report.

    Recipients: event "recipient_emails", else the sender address, so the report
    never goes to the search recipients by default.
    """
    recipients = detail.get("recipient_emails") or [settings.SENDER_EMAIL]
    print(f"Health check for: {[_redact_email(e) for e in recipients]}")

    report = HealthCheckManager().run(detail.get("case_details"))
    email = build_health_email(report)
    try:
        Emailer().send_email(
            recipients=recipients,
            subject=email["subject"],
            template_name="healthcheck_template.html",
            context=email["context"],
        )
    except Exception as e:
        print(f"ERROR! Health report email failed: {e}")
        traceback.print_exc()
        return {"statusCode": 500, "body": f"health report email failed: {e}"}

    print(f"SUCCESS! Health report sent: {email['subject']}")
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "healthy": report.healthy,
                "failed": [c.name for c in report.failed],
                "warnings": [c.name for c in report.warnings],
            }
        ),
    }


def handler(event, context):
    """AWS Lambda entry point. Accepts EventBridge events and Function URL requests."""
    if "body" in event:
        detail = json.loads(event["body"])
    else:
        detail = event.get("detail", event)

    mode = detail.get("mode", SEARCH_MODE)
    if mode == HEALTHCHECK_MODE:
        return run_health_check(detail)
    if mode != SEARCH_MODE:
        return {"statusCode": 400, "body": f"unknown mode: {mode}"}

    search_terms = detail.get("search_terms", [])
    if not search_terms:
        return {"statusCode": 400, "body": "search_terms is required"}

    case_details = detail.get("case_details")
    recipients = detail.get("recipient_emails") or settings.EMAIL_RECIPIENTS.split(",")

    target_date = detail.get("date") or (
        datetime.now(IST) + timedelta(days=1)
    ).strftime("%d/%m/%Y")
    dates_to_process = get_weekend_dates(target_date)

    print(f"Search terms: {search_terms}")
    print(f"Case details: {case_details}")
    print(f"Recipients: {[_redact_email(e) for e in recipients]}")
    print(f"Dates to process: {dates_to_process}")

    cause_list_manager = CauseListManager()
    case_manager = CaseManager(cause_list_manager.api)
    searcher = PDFSearcher(search_terms=search_terms)
    emailer = Emailer()
    error_handler = ErrorHandler(emailer, recipients)

    results_summary = []
    for date in dates_to_process:
        success = process_date(
            cause_list_manager,
            case_manager,
            searcher,
            emailer,
            error_handler,
            search_terms,
            date,
            recipients,
            case_details,
        )
        results_summary.append({"date": date, "success": success})

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": f"Processed {len(dates_to_process)} date(s)",
                "results": results_summary,
            }
        ),
    }
