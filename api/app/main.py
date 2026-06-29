from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import check_database, get_connection, init_db
from app.metrics_service import render_prometheus_metrics
from app.rate_limit import RateLimitMiddleware
from app.routers import admin, auth, automation, dashboard
from app.schemas import HealthOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MTA-Lab API",
    description="Market Test Agent Lab — strategy, logging, and dashboard backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)

app.include_router(auth.router)
app.include_router(automation.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/health", response_model=HealthOut)
def health(response: Response) -> HealthOut:
    db_ok, _ = check_database()
    if not db_ok:
        response.status_code = 503
        return HealthOut(status="error", service="mta-lab-api", database="error")
    return HealthOut(status="ok", service="mta-lab-api", database="ok")


@app.get("/metrics")
def metrics() -> Response:
    conn = get_connection()
    try:
        body = render_prometheus_metrics(conn)
        return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
    finally:
        conn.close()
