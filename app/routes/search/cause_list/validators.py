from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional
from datetime import datetime


class SearchRequest(BaseModel):
    search_term: str
    date: Optional[str]
    recipient_emails: Optional[List[EmailStr]]

    @validator("search_term")
    def validate_search_term(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Search term is required.")
        return value

    @validator("date")
    def validate_date(cls, value):
        if value:
            value = value.strip()
            try:
                datetime.strptime(value, "%d/%m/%Y")
            except ValueError:
                raise ValueError("Invalid date format. Use DD/MM/YYYY.")
        return value
