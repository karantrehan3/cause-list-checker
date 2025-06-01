from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="Authorization")


async def authenticate_request(api_key: str = Security(api_key_header)) -> None:
    if api_key != settings.AUTH_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Authentication Failed",
        )
