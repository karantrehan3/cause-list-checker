from unittest.mock import MagicMock, patch

import pytest

from app.managers.case_manager import CaseLookupResult
from app.managers.cause_list_manager import OLD_SOURCE, CauseListResult
from tests.fakes import CASE

PDF = {
    "pdf_name": "Ordinary | Main List",
    "pdf_url": "https://old/o",
    "source": OLD_SOURCE,
    "num_pages": 3,
}


@pytest.fixture
def lambda_parts():
    cause_lists = MagicMock()
    cause_lists.fetch.return_value = CauseListResult(new_pdfs=[PDF])
    cases = MagicMock()
    cases.lookup.return_value = CaseLookupResult(
        case_id="CR-2227-2010", case_status_url="u", issues=["Case status: HTTP 403"]
    )
    searcher = MagicMock()
    searcher.search_pdf.return_value = []
    return cause_lists, cases, searcher, MagicMock(), MagicMock()


def test_lambda_process_date_emails_report_with_issue_subject(lambda_parts):
    import lambda_handler

    cause_lists, cases, searcher, emailer, error_handler = lambda_parts
    ok = lambda_handler.process_date(
        cause_lists,
        cases,
        searcher,
        emailer,
        error_handler,
        ["x"],
        "05/11/2026",
        ["a@b.c"],
        CASE,
    )

    assert ok is True
    kwargs = emailer.send_email.call_args.kwargs
    assert kwargs["subject"].startswith("⚠️ INCOMPLETE")
    assert kwargs["context"]["issues"] == ["Case status: HTTP 403"]
    error_handler.handle_exception.assert_not_called()


def test_lambda_process_date_reports_exceptions(lambda_parts):
    import lambda_handler

    cause_lists, cases, searcher, emailer, error_handler = lambda_parts
    cause_lists.fetch.side_effect = RuntimeError("boom")

    assert (
        lambda_handler.process_date(
            cause_lists,
            cases,
            searcher,
            emailer,
            error_handler,
            ["x"],
            "05/11/2026",
            ["a@b.c"],
            CASE,
        )
        is False
    )
    error_handler.handle_exception.assert_called_once()


def test_lambda_handler_requires_search_terms():
    import lambda_handler

    assert lambda_handler.handler({"detail": {}}, None)["statusCode"] == 400


def test_lambda_handler_processes_each_weekend_date():
    import lambda_handler

    with (
        patch.object(lambda_handler, "process_date", return_value=True) as process,
        patch.object(lambda_handler, "CauseListManager"),
        patch.object(lambda_handler, "CaseManager"),
        patch.object(lambda_handler, "Emailer"),
    ):
        response = lambda_handler.handler(
            {"detail": {"search_terms": ["x"], "date": "07/11/2026"}}, None
        )

    assert response["statusCode"] == 200
    assert process.call_count >= 1


def test_api_process_single_search_sends_report():
    import asyncio

    from app.routes.search.cause_list import controllers

    queued = controllers.QueuedSearch(["x"], "05/11/2026", ["a@b.c"], CASE)
    cause_lists = MagicMock()
    cause_lists.fetch.return_value = CauseListResult(new_pdfs=[PDF])
    cases = MagicMock()
    cases.lookup.return_value = None
    emailer = MagicMock()
    with (
        patch.object(controllers, "CauseListManager", return_value=cause_lists),
        patch.object(controllers, "CaseManager", return_value=cases),
        patch.object(controllers, "Emailer", return_value=emailer),
        patch.object(controllers.PDFSearcher, "search_pdf", return_value=[]),
    ):
        assert asyncio.run(controllers.process_single_search(queued)) is True

    assert (
        emailer.send_email.call_args.kwargs["subject"]
        == "Cause List Search Results for ['x'] on 05/11/2026"
    )


def test_api_process_single_search_reports_failures_via_error_handler():
    import asyncio

    from app.routes.search.cause_list import controllers

    queued = controllers.QueuedSearch(["x"], "05/11/2026", ["a@b.c"], None)
    cause_lists = MagicMock()
    cause_lists.fetch.side_effect = RuntimeError("all sources down")
    with (
        patch.object(controllers, "CauseListManager", return_value=cause_lists),
        patch.object(controllers, "CaseManager"),
        patch.object(controllers, "Emailer"),
        patch.object(controllers, "ErrorHandler") as handler,
    ):
        handler.return_value.handle_exception.return_value = (
            "all sources down",
            "trace",
        )
        assert asyncio.run(controllers.process_single_search(queued)) is False

    handler.return_value.handle_exception.assert_called_once()


def test_api_send_report_wraps_email_errors():
    from fastapi import HTTPException

    from app.routes.search.cause_list import controllers

    emailer = MagicMock()
    emailer.send_email.side_effect = OSError("smtp down")
    with pytest.raises(HTTPException):
        controllers.send_report(
            emailer, ["a@b.c"], {"subject": "s", "context": {"issues": ["i"]}}
        )
