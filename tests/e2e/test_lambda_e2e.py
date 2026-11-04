"""Lambda handler end to end (EventBridge and Function URL events), fully offline."""

import json

import lambda_handler
from tests.e2e.conftest import RECIPIENT

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
