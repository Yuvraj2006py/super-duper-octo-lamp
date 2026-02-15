import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_applications, routes_audit, routes_auth, routes_jobs, routes_pipeline
from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(logging.INFO)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": settings.app_name}


app.include_router(routes_auth.router)
app.include_router(routes_jobs.router)
app.include_router(routes_pipeline.router)
app.include_router(routes_applications.router)
app.include_router(routes_audit.router)
