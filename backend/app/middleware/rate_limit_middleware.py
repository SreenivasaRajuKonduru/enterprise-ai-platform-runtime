import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.app.db.session import redis_client


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/ready", "/metrics"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_ip}:{int(time.time() // self.window_seconds)}"

        current_count = redis_client.incr(key)

        if current_count == 1:
            redis_client.expire(key, self.window_seconds)

        if current_count > self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": self.requests_per_minute,
                    "window_seconds": self.window_seconds,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.requests_per_minute - current_count)
        )
        return response
