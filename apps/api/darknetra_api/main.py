from fastapi import FastAPI

from darknetra_api.routers.health import router as health_router

app = FastAPI(title="DARKNETRA API", version="0.1.0")
app.include_router(health_router, prefix="/api/v1")
