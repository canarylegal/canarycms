import os
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _database_url_from_postgres_env() -> str:
    """Same wiring as ``app/docker-entrypoint.sh`` — keeps ``exec alembic`` working without a runtime export."""
    user = _require_env("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    if password is None:
        raise RuntimeError("Missing required environment variable: POSTGRES_PASSWORD")
    dbname = _require_env("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    enc = quote(password, safe="")
    return f"postgresql+psycopg://{user}:{enc}@{host}:{port}/{dbname}"


def _resolve_database_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if raw and raw.strip():
        return raw.strip()
    return _database_url_from_postgres_env()


DATABASE_URL = _resolve_database_url()
_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    pass
else:
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=_int_env("DATABASE_POOL_SIZE", 10),
        max_overflow=_int_env("DATABASE_MAX_OVERFLOW", 20),
        pool_timeout=_int_env("DATABASE_POOL_TIMEOUT", 30),
        pool_recycle=_int_env("DATABASE_POOL_RECYCLE", 1800),
    )
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
