from fastapi import APIRouter
from app.routes.search.cause_list import router as cause_list_router

router = APIRouter()

router.include_router(cause_list_router, prefix="/cause-list")
