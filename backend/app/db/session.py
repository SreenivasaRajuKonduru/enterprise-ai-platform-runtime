from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis
from opentelemetry import trace

from backend.app.core.config import settings

tracer = trace.get_tracer(__name__)

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
    with tracer.start_as_current_span("postgres.health_check") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", "SELECT")
        span.set_attribute("db.statement", "SELECT 1")

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            span.set_attribute("health.status", "connected")
            return True
        except Exception as exc:
            span.set_attribute("health.status", "disconnected")
            span.record_exception(exc)
            return False
    
redis_client = redis.Redis.from_url(settings.redis_url)

def check_redis_connection() -> bool:
    with tracer.start_as_current_span("redis.health_check") as span:
        span.set_attribute("cache.system", "redis")
        span.set_attribute("cache.operation", "PING")

        try:
            redis_client.ping()
            span.set_attribute("health.status", "connected")
            return True
        except Exception as exc:
            span.set_attribute("health.status", "disconnected")
            span.record_exception(exc)
            return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()