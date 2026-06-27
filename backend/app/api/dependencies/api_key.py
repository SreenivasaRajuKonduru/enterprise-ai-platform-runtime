from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.security import hash_api_key
from backend.app.db.session import get_db
from backend.app.repositories.api_key_repository import ApiKeyRepository
from backend.app.repositories.user_repository import UserRepository


def get_user_from_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    key_hash = hash_api_key(x_api_key)
    api_key = ApiKeyRepository(db).get_active_by_hash(key_hash)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    user = UserRepository(db).get_by_id(api_key.owner_user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key owner not found",
        )

    return user
