import asyncio

from dotenv import load_dotenv
from fastapi import FastAPI

from app.managers.queue import queue_manager
from app.routes import router

# Load environment variables from .env
load_dotenv()

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event():
    """Start the queue processor on application startup."""
    await queue_manager.start_processor()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the queue processor on application shutdown."""
    await queue_manager.stop_processor()


app.include_router(router)
