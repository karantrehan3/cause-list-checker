import os

import pytest

# Settings() requires these at import time; dummy values keep unit tests offline-safe.
_REQUIRED_ENV = {
    "AUTH_TOKEN": "test-token",
    "CASE_SEARCH_URL": "https://new.phhc.gov.in/case-status/case-no",
    "CL_BASE_URL": "https://highcourtchd.gov.in/clc.php",
    "CL_FORM_ACTION_URL": "https://highcourtchd.gov.in/view_causeList.php",
    "CL_JUDGE_WISE_REGULAR_URL": "https://new.phhc.gov.in/cause/reg-causelist",
    "EMAIL_RECIPIENTS": "test@example.com",
    "PHHC_API_BASE_URL": "https://livedb9010.phhc.gov.in",
    "SENDER_EMAIL": "sender@example.com",
    "SENDER_PASSWORD": "unused",
    "SENDER_NAME": "Test",
}
for key, value in _REQUIRED_ENV.items():
    os.environ.setdefault(key, value)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: hits the real court websites (run with RUN_LIVE=1)"
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live court-site test; set RUN_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
