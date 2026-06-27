from sqlalchemy.orm import Session

from backend.app.db.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, owner_user_id: int, name: str, key_hash: str, prefix: str) -> ApiKey:
        api_key = ApiKey(
            owner_user_id=owner_user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
        )
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

    def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        return (
            self.db.query(ApiKey)
            .filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
            .first()
        )
