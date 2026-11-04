from unittest.mock import MagicMock, patch

import pytest

from app.managers.health_check_manager import (
    FAILED,
    OK,
    WARNING,
    CheckResult,
    HealthReport,
)
from app.services.emailer import Emailer
from app.services.emailer.health_report import build_health_email, build_health_subject


def report(*statuses):
    return HealthReport(
        checks=[
            CheckResult(f"Check {i}", s, f"detail {i}", 120)
            for i, s in enumerate(statuses)
        ],
        generated_at="2026-11-04 09:00:01 IST",
        egress_ip="13.200.1.1",
        runtime="Python 3.13.7",
        region="ap-south-1",
    )


@pytest.mark.parametrize(
    "statuses, subject",
    [
        ((OK, OK), "✅ Cause List Checker health: all 2 checks OK (2026-11-04)"),
        (
            (OK, WARNING),
            "⚠️ Cause List Checker health: OK with 1 warning(s) (2026-11-04)",
        ),
        (
            (FAILED, WARNING, OK),
            "❌ Cause List Checker health: 1 of 3 checks failed (2026-11-04)",
        ),
    ],
)
def test_subject(statuses, subject):
    assert build_health_subject(report(*statuses)) == subject


def render(health_report):
    email = build_health_email(health_report)
    return (
        Emailer().env.get_template("healthcheck_template.html").render(email["context"])
    )


def test_template_all_ok():
    html = render(report(OK, OK))

    assert "✅ All 2 checks passed." in html
    assert html.count("✅ OK") == 2
    assert "ap-south-1" in html and "13.200.1.1" in html and "Python 3.13.7" in html


def test_template_failures_and_warnings():
    html = render(report(FAILED, WARNING, OK))

    assert "❌ 1 of 3 checks failed." in html
    assert '<tr class="failed">' in html and '<tr class="warning">' in html
    assert "❌ Failed" in html and "⚠️ Warning" in html
    assert "detail 0" in html and "120 ms" in html


def test_template_warnings_only():
    assert "⚠️ Everything reachable, with 1 warning(s)." in render(report(OK, WARNING))


# --- Lambda mode routing ------------------------------------------------------


def test_unknown_mode_is_rejected():
    import lambda_handler

    response = lambda_handler.handler({"detail": {"mode": "nope"}}, None)

    assert response == {"statusCode": 400, "body": "unknown mode: nope"}


def test_healthcheck_mode_sends_report_to_sender_by_default():
    import lambda_handler

    with (
        patch.object(lambda_handler, "HealthCheckManager") as manager,
        patch.object(lambda_handler, "Emailer") as emailer,
    ):
        manager.return_value.run.return_value = report(OK, FAILED)
        response = lambda_handler.handler({"detail": {"mode": "healthcheck"}}, None)

    assert response["statusCode"] == 200
    assert '"healthy": false' in response["body"] and '"Check 1"' in response["body"]
    kwargs = emailer.return_value.send_email.call_args.kwargs
    assert kwargs["recipients"] == [lambda_handler.settings.SENDER_EMAIL]
    assert kwargs["template_name"] == "healthcheck_template.html"
    assert kwargs["subject"].startswith("❌")
    manager.return_value.run.assert_called_once_with(None)


def test_healthcheck_email_failure_returns_500():
    import lambda_handler

    with (
        patch.object(lambda_handler, "HealthCheckManager") as manager,
        patch.object(lambda_handler, "Emailer") as emailer,
    ):
        manager.return_value.run.return_value = report(OK)
        emailer.return_value.send_email.side_effect = OSError("smtp down")
        response = lambda_handler.handler(
            {"detail": {"mode": "healthcheck", "recipient_emails": ["me@example.com"]}},
            None,
        )

    assert response["statusCode"] == 500
