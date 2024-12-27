from fastapi import HTTPException
from datetime import datetime
from typing import Optional


def validate_search_term(search_term: str) -> None:
    if not search_term:
        raise HTTPException(status_code=400, detail="Search term is required.")


def validate_date(date: Optional[str]) -> None:
    if date:
        try:
            datetime.strptime(date, "%d/%m/%Y")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use DD/MM/YYYY."
            )
