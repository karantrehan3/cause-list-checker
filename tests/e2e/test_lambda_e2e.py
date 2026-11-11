"""Lambda handler end to end (EventBridge and Function URL events), fully offline."""

import json

import lambda_handler
from tests.e2e.conftest import RECIPIENT
from tests.e2e.fake_world import OLD_PDF_A, PDF_WITH_CASE_ENTRY
from tests.fakes import ENTRY, wrapped

DETAIL = {
    "search_terms": ["CR-2227-2010"],
    "date": "05/11/2026",
    "recipient_emails": [RECIPIENT],
    "case_details": {"type": "CR", "no": "2227", "year": "2010"},
}


def test_eventbridge_event_runs_search_and_emails(world):
    response = lambda_handler.handler({"detail": DETAIL}, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["results"] == [
        {"date": "05/11/2026", "success": True}
    ]
    sent = world.only_email()
    assert sent.recipients == [RECIPIENT]
    assert "✅ Search results found." in sent.html
    assert "✅ Search term found in Judge-Wise Cause List" in sent.html


def test_lambda_email_shows_the_listing_and_checks_the_bench_printed_above_it(world):
    world.route(
        OLD_PDF_A, 200, PDF_WITH_CASE_ENTRY, {"Content-Type": "application/pdf"}
    )

    lambda_handler.handler({"detail": DETAIL}, None)

    html = " ".join(world.only_email().html.split())
    assert (
        "CR-2227-2010 is listed on 05/11/2026: Ordinary · Main List, item 12, "
        "HON&#39;BLE MR. JUSTICE OTHER JUDGE, CR NO 3, p. 1 (from cause-list PDF)"
    ) in html
    assert "<th>Case</th><th>Parties</th><th>Advocates</th>" in html
    assert "HARYANA WAKF BOARD V/S VISHNU MITTAR" in html
    assert world.requested(r"getCauseList\?.*bench_judge_id=701")


def test_function_url_event_body_is_supported(world):
    response = lambda_handler.handler({"body": json.dumps(DETAIL)}, None)

    assert response["statusCode"] == 200
    assert world.only_email().recipients == [RECIPIENT]


def test_lambda_reports_blocked_case_status_in_subject(world):
    world.block("/cis_filing/public/getCase")

    lambda_handler.handler({"detail": DETAIL}, None)

    assert world.only_email().subject.startswith("⚠️ INCOMPLETE – ")


def test_missing_search_terms_is_400_and_sends_nothing(world):
    response = lambda_handler.handler(
        {"detail": {"recipient_emails": [RECIPIENT]}}, None
    )

    assert response["statusCode"] == 400
    assert world.sent_emails == [] and world.requests_seen == []


# --- Daily health check mode -------------------------------------------------------

HEALTH = {
    "mode": "healthcheck",
    "recipient_emails": [RECIPIENT],
    "case_details": {"type": "CR", "no": "2227", "year": "2010"},
}


def test_healthcheck_runs_all_checks_and_emails_report_only(world):
    world.route(
        "/cis_filing/public/getRegularCauseList",
        200,
        wrapped(ENTRY),
        {"Content-Type": "application/json"},
    )

    response = lambda_handler.handler({"detail": HEALTH}, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {
        "healthy": True,
        "failed": [],
        "warnings": [],
    }
    sent = world.only_email()
    assert sent.recipients == [RECIPIENT]
    assert sent.subject.startswith("✅ Cause List Checker health: all 6 checks OK")
    assert "Daily Health Report" in sent.html
    assert sent.html.count("✅ OK") == 6
    # Read-only: it downloads PDFs and queries APIs, but never runs a search email.
    assert world.requested(r"show_cause_list\.php")
    assert world.requested(r"daily-causelist-pdf/\d{4}-\d{2}-\d{2}/O/M")
    assert world.requested(r"getCase\?")


def test_healthcheck_reports_blocked_dependencies(world):
    world.block("show_cause_list.php")
    world.block("/cis_filing/public/getCase")

    response = lambda_handler.handler({"detail": HEALTH}, None)

    body = json.loads(response["body"])
    assert body["healthy"] is False
    assert body["failed"] == ["Cause list PDFs (highcourtchd.gov.in)", "Case status"]
    sent = world.only_email()
    assert sent.subject.startswith("❌ Cause List Checker health: 2 of 6 checks failed")
    assert "HTTP 403 Forbidden" in sent.html


def test_healthcheck_without_recipients_goes_to_sender_only(world):
    from app.config import settings

    lambda_handler.handler({"detail": {"mode": "healthcheck"}}, None)

    assert world.only_email().recipients == [settings.SENDER_EMAIL]


def test_healthcheck_with_no_regular_list_is_a_warning(world):
    response = lambda_handler.handler({"detail": HEALTH}, None)

    assert json.loads(response["body"])["warnings"] == ["Judge-wise regular cause list"]
    assert world.only_email().subject.startswith(
        "⚠️ Cause List Checker health: OK with 1 warning(s)"
    )
