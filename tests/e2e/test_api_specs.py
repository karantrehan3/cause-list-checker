"""API specs: the FastAPI app end to end against an offline court + SMTP capture."""

import pytest

from app.managers.cause_list_sources import NEW_SOURCE, OLD_SOURCE
from tests.e2e.conftest import RECIPIENT

SEARCH_URL = "/search/cause-list/"
CASE_BODY = {
    "search_terms": ["CR-2227-2010", "Vishnu Mittar"],
    "date": "05/11/2026",  # Thursday: a single date, no weekend expansion
    "recipient_emails": [RECIPIENT],
    "case_details": {"type": "CR", "no": "2227", "year": "2010"},
}


# --- Contract: health, auth, validation, queue status ----------------------------


def test_health_needs_no_auth(api_client):
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_without_token_is_rejected(api_client, world):
    response = api_client.post(SEARCH_URL, json=CASE_BODY)

    assert response.status_code == 403
    assert world.requests_seen == [] and world.sent_emails == []


def test_search_with_wrong_token_is_rejected(api_client, world):
    response = api_client.post(
        SEARCH_URL, json=CASE_BODY, headers={"Authorization": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication Failed"}
    assert world.sent_emails == []


@pytest.mark.parametrize(
    "body",
    [
        {**CASE_BODY, "search_terms": []},
        {**CASE_BODY, "date": "2026-11-05"},
        {**CASE_BODY, "recipient_emails": ["not-an-email"]},
        {**CASE_BODY, "case_details": {"type": "CR"}},
        {"date": "05/11/2026"},
    ],
)
def test_invalid_search_body_is_422_and_does_nothing(
    api_client, world, auth_headers, body
):
    response = api_client.post(SEARCH_URL, json=body, headers=auth_headers)

    assert response.status_code == 422
    assert world.requests_seen == [] and world.sent_emails == []


def test_queue_status_requires_auth_and_reports_size(api_client, auth_headers):
    assert api_client.get(f"{SEARCH_URL}queue-status").status_code == 403

    response = api_client.get(f"{SEARCH_URL}queue-status", headers=auth_headers)

    assert response.status_code == 200
    assert "queue_size" in response.json()


# --- End to end: request -> court sites -> PDF search -> email --------------------


def test_full_search_finds_case_everywhere_and_emails_only_the_recipient(
    api_client, world, auth_headers
):
    response = api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["dates"] == ["05/11/2026"]

    sent = world.only_email()
    assert sent.recipients == [RECIPIENT]
    assert (
        sent.subject
        == "Cause List Search Results for ['CR-2227-2010', 'Vishnu Mittar'] on 05/11/2026"
    )
    html = sent.html
    assert "✅ Search results found." in html
    assert html.count("Cause Lists Searched &mdash;") == 2
    assert OLD_SOURCE in html and NEW_SOURCE in html
    assert "2 pages" in html
    assert 'issues-banner"' not in html  # no issues -> no banner
    assert "✅ Search term found in Judge-Wise Cause List" in html
    assert "❌ Search term not found in Judge-Wise Regular Cause List" in html
    assert "Case Details For Case CR-2227-2010" in html

    # Both sites' PDFs were actually downloaded and the court APIs called.
    assert world.requested(r"show_cause_list\.php")
    assert world.requested(r"daily-causelist-pdf/2026-11-05/O/M")
    assert world.requested(
        r"getCauseList\?bench_judge_id=650&cause_list_date=2026-11-05"
    )


def test_name_only_search_skips_case_checks(api_client, world, auth_headers):
    body = {key: value for key, value in CASE_BODY.items() if key != "case_details"}

    api_client.post(SEARCH_URL, json=body, headers=auth_headers)

    html = world.only_email().html
    assert "Case Status Details" not in html
    assert not world.requested(r"getCase|getCauseList")


def test_friday_search_also_covers_weekend_and_monday(api_client, world, auth_headers):
    response = api_client.post(
        SEARCH_URL, json={**CASE_BODY, "date": "06/11/2026"}, headers=auth_headers
    )

    assert response.json()["dates"] == [
        "06/11/2026",
        "07/11/2026",
        "08/11/2026",
        "09/11/2026",
    ]
    assert len(world.sent_emails) == 4


# --- Failures are loud --------------------------------------------------------------


def test_blocked_pdfs_on_one_site_mark_email_incomplete(
    api_client, world, auth_headers
):
    world.block("/public/daily-causelist-pdf/2026")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    sent = world.only_email()
    assert sent.subject.startswith("⚠️ INCOMPLETE – ")
    assert "⚠️ Some checks could not be completed" in sent.html
    assert f"Ordinary | Main List ({NEW_SOURCE}): HTTP 403" in sent.html
    assert "❌ Not read (HTTP 403)" in sent.html
    assert "✅ Search results found." in sent.html  # the old site still found it


def test_every_pdf_blocked_is_search_failed(api_client, world, auth_headers):
    world.block("show_cause_list.php")
    world.block("/public/daily-causelist-pdf/2026")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    sent = world.only_email()
    assert sent.subject.startswith("❌ SEARCH FAILED – ")
    assert "❌ SEARCH FAILED: no cause list could be read." in sent.html


def test_case_status_blocked_is_reported_not_hidden(api_client, world, auth_headers):
    world.block("/cis_filing/public/getCase")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    sent = world.only_email()
    assert sent.subject.startswith("⚠️ INCOMPLETE – ")
    assert (
        "Case status for CR-2227-2010: case status unavailable (HTTP 403 Forbidden)"
        in sent.html
    )
    assert "⚠️ Could not check Judge-Wise Cause List" in sent.html
    assert "⚠️ Case status for CR-2227-2010 could not be loaded" in sent.html


def test_judge_list_rate_limited_is_unavailable_not_not_found(
    api_client, world, auth_headers
):
    world.route("/cis_filing/public/getCauseList", 429, "slow down")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    html = world.only_email().html
    assert "⚠️ Could not check Judge-Wise Cause List: HTTP 429 Too Many Requests" in html
    assert "❌ Search term not found in Judge-Wise Cause List" not in html


def test_one_site_down_still_searches_the_other(api_client, world, auth_headers):
    world.route("view_causeList.php", 500, "error")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    sent = world.only_email()
    assert sent.subject.startswith("⚠️ INCOMPLETE – ")
    assert (
        f"Could not get cause lists from {OLD_SOURCE}: HTTP 500 Internal Server Error"
        in sent.html
    )
    assert "✅ Search results found." in sent.html


def test_both_sites_down_sends_error_notification(api_client, world, auth_headers):
    world.route("view_causeList.php", 500, "error")
    world.route("/public/daily-causelist-pdf/list", 500, "error")

    api_client.post(SEARCH_URL, json=CASE_BODY, headers=auth_headers)

    sent = world.only_email()
    assert sent.subject == "Cause List Search Error Notification"
    assert "all cause list sources failed" in sent.html
