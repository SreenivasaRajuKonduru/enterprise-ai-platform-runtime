from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.user import UserCreate, UserLogin
from backend.app.services.auth_service import AuthService
from backend.app.events.producer import publish_event
from backend.app.events.topics import USER_REGISTERED

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register")
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):

    service = AuthService(UserRepository(db))

    new_user = service.register(
        user.email,
        user.password,
        user.role,
    )

    try:
        publish_event(
            USER_REGISTERED,
            {
                "event_type": USER_REGISTERED,
                "user_id": new_user.id,
                "email": new_user.email,
                "role": new_user.role,
            },
        )
    except Exception as e:
        print("KAFKA PUBLISH ERROR:", str(e))

    return {
        "message": "user_registered",
        "id": new_user.id,
        "email": new_user.email,
        "role": new_user.role,
    }


@router.post("/login")
def login(
    user: UserLogin,
    db: Session = Depends(get_db),
):

    service = AuthService(UserRepository(db))

    token = service.login(
        user.email,
        user.password,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }