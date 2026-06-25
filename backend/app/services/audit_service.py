from backend.app.repositories.audit_repository import AuditRepository


class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def record_request(
        self,
        request_id: str | None,
        user_email: str | None,
        role: str | None,
        method: str,
        path: str,
        status_code: int,
        client_ip: str | None,
        latency_ms: int,
    ):
        return self.repository.create(
            request_id=request_id,
            user_email=user_email,
            role=role,
            method=method,
            path=path,
            status_code=status_code,
            client_ip=client_ip,
            latency_ms=latency_ms,
        )