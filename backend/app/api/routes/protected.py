from fastapi import APIRouter, Depends

from backend.app.api.dependencies.auth import get_current_user, require_roles

router = APIRouter(prefix="/protected", tags=["protected"])


@router.get("/me")
def read_current_user(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }


@router.get("/admin")
def admin_only(current_user=Depends(require_roles(["admin"]))):
    return {
        "message": "admin_access_granted",
        "email": current_user.email,
        "role": current_user.role,
    }