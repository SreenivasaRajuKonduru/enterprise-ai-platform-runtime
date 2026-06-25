from fastapi import FastAPI
import socket
import os
from backend.app.db.session import (
    check_database_connection,
    check_redis_connection,
)
from backend.app.api.routes.auth import router as auth_router
from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.db.models.user import User


app = FastAPI(
    title="Enterprise AI Platform Runtime",
    description="Production-grade AI Platform",
    version="0.1.0",
)
app.include_router(auth_router)
# Base.metadata.create_all(bind=engine)


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
        "status": "healthy"
    }
    
@app.get("/node")
def node():
    return {
        "container_id": socket.gethostname(),
        "service": os.getenv("SERVICE_NAME", "api")
    }
    
@app.get("/ready")
def readiness_check():
    db_ok = check_database_connection()
    redis_ok = check_redis_connection()

    overall = db_ok and redis_ok

    return {
        "status": "ready" if overall else "not_ready",
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
    }