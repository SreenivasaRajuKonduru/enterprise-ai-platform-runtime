import os
import socket

from fastapi import FastAPI
# from opentelemetry import trace

from backend.app.api.routes.ai_runtime import router as ai_runtime_router
from backend.app.api.routes.api_keys import router as api_keys_router
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.ops import router as ops_router
from backend.app.api.routes.protected import router as protected_router
from backend.app.core.logging import configure_logging
from backend.app.core.metrics import metrics_response
from backend.app.db.session import (
    check_database_connection,
    check_redis_connection,
    engine,
)
from backend.app.jobs.router import router as jobs_router
from backend.app.middleware.audit_middleware import AuditMiddleware
from backend.app.middleware.rate_limit_middleware import RateLimitMiddleware
from backend.app.middleware.request_id_middleware import RequestIdMiddleware
from backend.app.observability.tracing import configure_tracing
from backend.app.rag.router import router as rag_router

from backend.app.resilience.router import (
    router as circuit_breaker_router,
)


configure_logging()

app = FastAPI(
    title="Enterprise AI Platform Runtime",
    description="Production-grade AI Platform",
    version="0.1.0",
)


app.add_middleware(AuditMiddleware)

app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=20,
)

app.add_middleware(RequestIdMiddleware)

app.include_router(circuit_breaker_router)
app.include_router(auth_router)
app.include_router(protected_router)
app.include_router(api_keys_router)
app.include_router(ops_router)
app.include_router(ai_runtime_router)
app.include_router(rag_router)
app.include_router(jobs_router)



@app.get("/")
def root():
    return {
        "project": "Enterprise AI Platform Runtime",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.get("/node")
def node():
    return {
        "container_id": socket.gethostname(),
        "service": os.getenv("SERVICE_NAME", "api"),
    }


@app.get("/ready")
def readiness_check():
    database_ok = check_database_connection()
    redis_ok = check_redis_connection()
    overall_ready = database_ok and redis_ok

    return {
        "status": "ready" if overall_ready else "not_ready",
        "database": (
            "connected"
            if database_ok
            else "disconnected"
        ),
        "redis": (
            "connected"
            if redis_ok
            else "disconnected"
        ),
    }


@app.get("/metrics")
def metrics():
    return metrics_response()


# tracer = trace.get_tracer(__name__)


# @app.get("/trace-test")
# def trace_test():
#     with tracer.start_as_current_span("manual.trace_test"):
#         return {
#             "status": "trace created",
#         }


# configure_tracing(app, engine)
configure_tracing(
    app=app,
    engine=engine,
)