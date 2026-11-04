import socket
from unittest.mock import AsyncMock, patch

import pytest
import requests

from app.managers.pdf_tracker import pdf_tracker
from tests.e2e.fake_world import FakeWorld, block_sockets

RECIPIENT = "test-recipient@example.com"


@pytest.fixture
def world():
    """Offline court sites + SMTP capture. No real network, no real email."""
    world = FakeWorld()
    pdf_tracker.clear_existing_pdfs()
    with (
        patch.object(
            requests.Session, "request", autospec=True, side_effect=world.handle
        ),
        patch("app.services.emailer.smtplib.SMTP", world.smtp_factory()),
        patch.object(socket.socket, "connect", block_sockets),
        patch("app.managers.pdf_searcher.time.sleep"),
        patch("app.clients.court_http.time.sleep"),
    ):
        yield world
    pdf_tracker.clear_existing_pdfs()


@pytest.fixture
def api_client(world):
    """FastAPI client whose queue runs each search immediately (no background loop)."""
    from fastapi.testclient import TestClient

    from app.managers.queue import queue_manager
    from app.server import app

    async def run_now(method, *args, max_attempts=3, task_id=None, **kwargs):
        await method(*args, **kwargs)

    with (
        patch.object(queue_manager, "start_processor", AsyncMock()),
        patch.object(queue_manager, "add_task", side_effect=run_now),
    ):
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    from app.config import settings

    return {"Authorization": settings.AUTH_TOKEN}
