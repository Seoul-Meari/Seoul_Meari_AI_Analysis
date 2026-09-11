from fastapi import FastAPI
from app.api.v1.routers import api_router
from app.infra.scheduler import scheduler, init_jobs

app = FastAPI(title="Seoul Meari API")

app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    init_jobs()
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()