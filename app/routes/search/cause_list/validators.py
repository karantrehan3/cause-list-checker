from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional
from datetime import datetime


class SearchRequest(BaseModel):
    search_terms: List[str]
    date: Optional[str]
    recipient_emails: Optional[List[EmailStr]]

    @validator("search_terms")
    def validate_search_terms(cls, values):
        if not values:
            raise ValueError("At least one search term is required.")
        return [value.strip() for value in values if value.strip()]

    @validator("date")
    def validate_date(cls, value):
        if value:
            value = value.strip()
            try:
                datetime.strptime(value, "%d/%m/%Y")
            except ValueError:
                raise ValueError("Invalid date format. Use DD/MM/YYYY.")
        return value
