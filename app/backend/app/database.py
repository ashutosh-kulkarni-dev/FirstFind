import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
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
        ("is_admin", "BOOLEAN DEFAULT FALSE"),
    ],
    "stores": [
        ("google_place_id", "VARCHAR(120)"),
        ("reviews_fetched_at", "TIMESTAMP NULL"),
        ("store_type", "VARCHAR(20) DEFAULT 'thrift'"),
        ("address", "VARCHAR(300)"),
        ("description", "TEXT"),
        ("description_source", "VARCHAR(10)"),
        ("tags", "VARCHAR(200)"),
        ("tags_source", "VARCHAR(10)"),
        ("google_rating", "FLOAT"),
        ("google_review_count", "INTEGER"),
        ("price_estimated", "BOOLEAN DEFAULT FALSE"),
        ("is_active", "BOOLEAN DEFAULT TRUE"),
        ("created_via", "VARCHAR(10)"),
        ("admin_edited_at", "TIMESTAMP NULL"),
        ("google_status", "VARCHAR(12)"),
    ],
    "reviews": [
        ("source", "VARCHAR(20) DEFAULT 'app'"),
        ("external_id", "VARCHAR(128)"),
        ("author_name", "VARCHAR(120)"),
        ("sentiment_engine", "VARCHAR(12)"),
        ("is_hidden", "BOOLEAN DEFAULT FALSE"),
    ],
}


def ensure_schema() -> None:
    """Idempotently add post-initial-schema columns to existing tables.

    Only issues ALTER TABLE for columns that are actually missing. An ALTER
    takes an exclusive lock on the table even when it is a no-op ("ADD COLUMN
    IF NOT EXISTS" on an existing column), and running those on every boot
    deadlocked the web app against the daily data job. Checking first means a
    normal boot takes no table locks at all.
    """
    dialect = engine.dialect.name  # "postgresql" | "mysql" | "sqlite"
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = []
    for table, columns in _ADDED_COLUMNS.items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        missing += [(table, col, coltype) for col, coltype in columns if col not in have]
    if not missing:
        return
    for table, col, coltype in missing:
        # One short transaction per column: a failure or lock wait on one
        # never holds locks on the others.
        try:
            with engine.begin() as conn:
                if dialect == "postgresql":
                    conn.execute(text("SET LOCAL lock_timeout = '10s'"))
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
            log.info("ensure_schema: added %s.%s", table, col)
        except SQLAlchemyError as e:  # raced with another process / lock timeout
            log.warning("ensure_schema: could not add %s.%s (%s)", table, col, e)
