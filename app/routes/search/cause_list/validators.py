from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, validator


class SearchRequest(BaseModel):
    search_terms: List[str]
    date: Optional[str]
    recipient_emails: Optional[List[EmailStr]]
    case_details: Optional[Dict[str, str]]

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

    @validator("case_details")
    def validate_case_details(cls, value):
        if value:
            required_keys = {"no", "type", "year"}
            if not isinstance(value, dict) or not required_keys.issubset(value.keys()):
                raise ValueError(
                    "case_details must be a dictionary containing 'no', 'type', and 'year' as strings."
                )
            if not all(isinstance(v, str) for v in value.values()):
                raise ValueError("All values in case_details must be strings.")
        return value
