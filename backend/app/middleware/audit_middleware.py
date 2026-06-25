import logging
import time

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.security import ALGORITHM, SECRET_KEY
from backend.app.db.session import SessionLocal
from backend.app.repositories.audit_repository import AuditRepository
from backend.app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()

        user_email = None
        role = None

        authorization = request.headers.get("authorization")

        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1]

            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                user_email = payload.get("sub")
                role = payload.get("role")
            except JWTError:
                user_email = None
                role = None

        response = await call_next(request)

        latency_ms = int((time.time() - start_time) * 1000)
        client_ip = request.client.host if request.client else None
        request_id = getattr(request.state, "request_id", None)

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )

        db = SessionLocal()

        try:
            service = AuditService(AuditRepository(db))
            service.record_request(
                request_id=request_id,
                user_email=user_email,
                role=role,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                client_ip=client_ip,
                latency_ms=latency_ms,
            )
        finally:
            db.close()

        return response