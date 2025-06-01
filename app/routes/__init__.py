from fastapi import APIRouter, Depends

from app.routes.auth import authenticate_request
from app.routes.search import router as search_router

router = APIRouter(
    dependencies=[Depends(authenticate_request)],
)


router.include_router(search_router, prefix="/search")
