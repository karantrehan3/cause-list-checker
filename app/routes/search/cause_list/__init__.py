from fastapi import APIRouter
from typing import Dict, Any, Optional
from app.routes.search.cause_list.controllers import scrape_search_and_notify
from app.routes.search.cause_list.validators import validate_search_term, validate_date

router = APIRouter()


@router.post("/")
async def search_cause_list(
    search_term: str, date: Optional[str] = None
) -> Dict[str, Any]:
    validate_search_term(search_term)
    validate_date(date)
    return await scrape_search_and_notify(search_term, date)
