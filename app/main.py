from fastapi import FastAPI
from app.api.v1.routers import api_router

app = FastAPI(title="Seoul Meari API")

app.include_router(api_router)