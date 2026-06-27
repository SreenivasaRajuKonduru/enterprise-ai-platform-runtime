from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.security import generate_api_key, hash_api_key, get_api_key_prefix
from backend.app.db.session import get_db
from backend.app.repositories.api_key_repository import ApiKeyRepository


router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreateRequest(BaseModel):
    name: str


@router.post("")
def create_api_key(
    request: ApiKeyCreateRequest,
    current_user=Depends(require_roles(["admin"])),
    db: Session = Depends(get_db),
):
    raw_key = generate_api_key()

    saved_key = ApiKeyRepository(db).create(
        owner_user_id=current_user.id,
        name=request.name,
        key_hash=hash_api_key(raw_key),
        prefix=get_api_key_prefix(raw_key),
    )

    return {
        "id": saved_key.id,
        "name": saved_key.name,
        "prefix": saved_key.prefix,
        "api_key": raw_key,
        "message": "Save this API key now. It will not be shown again.",
    }
