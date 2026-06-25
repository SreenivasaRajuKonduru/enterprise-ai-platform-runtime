from fastapi import HTTPException

from backend.app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)

from backend.app.repositories.user_repository import UserRepository


class AuthService:

    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, email: str, password: str, role: str):

        existing = self.repository.get_by_email(email)

        if existing:
            raise HTTPException(
                status_code=400,
                detail="User already exists"
            )

        user = self.repository.create_user(
            email=email,
            hashed_password=hash_password(password),
            role=role,
        )

        return user

    def login(self, email: str, password: str):

        user = self.repository.get_by_email(email)

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials"
            )

        if not verify_password(
            password,
            user.hashed_password,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials"
            )

        token = create_access_token(
            {
                "sub": user.email,
                "role": user.role,
            }
        )

        return token