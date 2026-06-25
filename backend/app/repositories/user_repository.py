from sqlalchemy.orm import Session

from backend.app.db.models.user import User


class UserRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str):
        return self.db.query(User).filter(User.email == email).first()

    def create_user(self, email: str, hashed_password: str, role: str):

        user = User(
            email=email,
            hashed_password=hashed_password,
            role=role,
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user