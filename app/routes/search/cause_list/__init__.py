from fastapi import APIRouter

from app.managers.queue import queue_manager
from app.routes.search.cause_list.controllers import scrape_search_and_notify
from app.routes.search.cause_list.validators import SearchRequest

router = APIRouter()


@router.post("/")
async def search_cause_list(body: SearchRequest):
    return await scrape_search_and_notify(
        body.search_terms, body.date, body.recipient_emails, body.case_details
    )


@router.get("/queue-status")
async def get_queue_status():
    """Get the current status of the search queue."""
    return queue_manager.get_queue_status()
