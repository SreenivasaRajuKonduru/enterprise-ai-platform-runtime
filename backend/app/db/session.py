from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis

from backend.app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def check_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    
redis_client = redis.Redis.from_url(settings.redis_url)

def check_redis_connection() -> bool:
    try:
        redis_client.ping()
        return True
    except Exception:
        return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()