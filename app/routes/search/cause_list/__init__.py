from fastapi import APIRouter
from app.routes.search.cause_list.controllers import scrape_search_and_notify
from app.routes.search.cause_list.validators import SearchRequest

router = APIRouter()


@router.post("/")
async def search_cause_list(body: SearchRequest):
    return await scrape_search_and_notify(
        body.search_term, body.date, body.recipient_emails
    )
