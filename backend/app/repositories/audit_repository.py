from sqlalchemy.orm import Session

from backend.app.db.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        request_id: str | None,
        user_email: str | None,
        role: str | None,
        method: str,
        path: str,
        status_code: int,
        client_ip: str | None,
        latency_ms: int,
    ) -> AuditLog:
        audit_log = AuditLog(
            request_id=request_id,
            user_email=user_email,
            role=role,
            method=method,
            path=path,
            status_code=status_code,
            client_ip=client_ip,
            latency_ms=latency_ms,
        )

        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        

        return audit_log