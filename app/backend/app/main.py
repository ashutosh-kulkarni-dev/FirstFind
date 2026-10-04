"""FirstFind API — FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, ENVIRONMENT, GROQ_API_KEY, JWT_SECRET
from .database import Base, SessionLocal, engine, ensure_schema
from .middleware import RateLimitMiddleware, TimingMiddleware
from .ml.tasks import build_recommender
from .models import Store, Zone
from .routers import auth_routes, clusters, conversations, lists, metro, misc, stores

log = logging.getLogger(__name__)


def _startup_checks():
    """Surface insecure/degraded config at boot; hard-fail in production."""
    weak_secret = JWT_SECRET == "dev-secret-change-in-prod" or len(JWT_SECRET) < 32
    if weak_secret:
        msg = ("JWT secret is the default or shorter than 32 chars — set a strong "
               "FIRSTFIND_JWT_SECRET (e.g. `python -c \"import secrets;print(secrets.token_urlsafe(48))\"`).")
        if ENVIRONMENT == "production":
            raise RuntimeError(f"SECURITY: {msg}")
        log.warning("SECURITY: %s", msg)
    log.info("Environment: %s", ENVIRONMENT)
    log.info("Chatbot: %s", "Groq LLM phrasing enabled" if GROQ_API_KEY
             else "rule-based (no GROQ_API_KEY)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is idempotent and safe under concurrent workers. Seeding is
    # NOT done here: seed() drops and recreates every table, so running it from
    # startup races (and can wipe data) when Uvicorn runs >1 worker — each
    # process runs lifespan. Seeding is now an explicit one-shot CLI step
    # (`python -m app.seed`); startup only warns if the DB looks empty.
    Base.metadata.create_all(engine)
    # create_all creates missing tables but never ALTERs an existing one, so
    # columns added after the initial schema are applied here (idempotent).
    ensure_schema()
    if _db_empty():
        log.warning("Database looks empty — run `python -m app.seed` to populate it. "
                    "Skipping auto-seed (unsafe to seed from startup with multiple workers).")
    build_recommender()
    # Sentiment runs via the HuggingFace Inference API (no local model). Nudge the
    # HF model out of a cold start so the first review scored at runtime is faster.
    from .ml import sentiment as sentiment_ml
    from .config import hf_token
    sentiment_ml.warmup()
    log.info("Sentiment engine: %s",
             "HF Inference API" if hf_token else "VADER fallback")
    _startup_checks()
    yield


def _db_empty() -> bool:
    """True if the DB needs (re-)seeding.

    Checks stores AND zones (not just stores) because a seed() run killed
    partway through (crash, OOM, container restart) could leave stores
    populated but zones empty, which looked "seeded" to a stores-only check
    and silently skipped reseeding forever. Reviews are intentionally NOT
    checked: the dataset ships with zero reviews (they accrue at runtime),
    so an empty reviews table is the normal, fully-seeded state.
    """
    db = SessionLocal()
    try:
        if db.query(Store).count() == 0:
            return True
        if db.query(Zone).count() == 0:
            return True
        return False
    finally:
        db.close()


app = FastAPI(title="FirstFind API", version="0.2.0", lifespan=lifespan)

app.add_middleware(TimingMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(stores.router)
app.include_router(misc.router)
app.include_router(clusters.router)
app.include_router(metro.router)
app.include_router(conversations.router)
app.include_router(lists.router)
