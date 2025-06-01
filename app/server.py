from fastapi import FastAPI
from dotenv import load_dotenv
from app.routes import router
from mangum import Mangum

# Load environment variables from .env
load_dotenv()

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


app.include_router(router)

# Create handler for AWS Lambda
handler = Mangum(app)
