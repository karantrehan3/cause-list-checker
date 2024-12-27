from fastapi import APIRouter
from app.routes.search import router as search_router

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


router.include_router(search_router, prefix="/search")
