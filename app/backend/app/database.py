import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DATABASE_URL

log = logging.getLogger(__name__)

# SQLite needs check_same_thread=False; MySQL/Postgres want connection pooling
# with pre-ping so stale connections are recycled instead of erroring mid-request.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the initial schema. create_all() only creates missing
# tables — it never ALTERs an existing one — so newly-added columns on tables that
# already exist in a deployed DB (Supabase/MySQL) must be added explicitly.
# Kept idempotent so it is safe to run on every boot; this is a lightweight stand-in
# for Alembic until the first real post-launch migration.
_ADDED_COLUMNS = {
    "users": [
        ("auth_provider", "VARCHAR(20) DEFAULT 'local'"),
        ("google_sub", "VARCHAR(64)"),
        ("avatar_url", "VARCHAR(300)"),
    ],
    "stores": [
        ("google_place_id", "VARCHAR(120)"),
    ],
    "reviews": [
        ("source", "VARCHAR(20) DEFAULT 'app'"),
        ("external_id", "VARCHAR(128)"),
    ],
}


def ensure_schema() -> None:
    """Idempotently add post-initial-schema columns to existing tables."""
    dialect = engine.dialect.name  # "postgresql" | "mysql" | "sqlite"
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            for col, coltype in columns:
                try:
                    if dialect == "postgresql":
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"))
                    else:
                        # MySQL/SQLite lack ADD COLUMN IF NOT EXISTS on older versions;
                        # attempt and swallow the "duplicate column" error on reruns.
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                except Exception as e:  # already exists / not applicable
                    log.debug("ensure_schema: skip %s.%s (%s)", table, col, e)
