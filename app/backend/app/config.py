"""App configuration."""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Some Windows DLP/monitoring agents (e.g. Netskope — the `\\.\nllMonFltProxy`
# device) export SSLKEYLOGFILE pointing at a device/named-pipe path. Python's
# ssl.create_default_context() applies that value via keylog_filename, and
# opening the device path raises PermissionError, which blows up *any* SSL
# context creation (pymysql, HTTPS, etc.). We don't need TLS key logging, so
# drop the var for this process before any SSLContext is built.
if os.environ.get("SSLKEYLOGFILE", "").startswith("\\\\.\\"):
    os.environ.pop("SSLKEYLOGFILE", None)

# Some environments (corporate proxies, or antivirus doing SSL interception on
# Windows) present a custom root CA that certifi doesn't know about, which
# breaks HTTPS to HuggingFace when downloading the sentiment model. Fall back to
# the OS trust store (which does have that CA) via truststore when available.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - optional; any failure means default certificates
    pass

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent  # repo root
DATA_DIR = REPO_ROOT / "data"
# Only read when seeding; override in containers where data/ isn't shipped.
STORES_JSON = Path(os.environ.get("STORES_JSON", DATA_DIR / "stores.json"))

# Load app/backend/.env (you add DB_PASSWORD there — never commit it).
load_dotenv(BACKEND_DIR / ".env")

# "development" locally; set ENVIRONMENT=production on Railway/Render so the
# startup checks enforce (not just warn about) a strong JWT secret.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

# ---- Database ----
# Local dev: MySQL. Production: Supabase (Postgres) via DATABASE_URL — nothing
# else changes because everything runs through the SQLAlchemy ORM. Supabase gives
# you a ready-made connection string, e.g.
#   postgresql+psycopg2://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
# (psycopg2-binary is in requirements). Either set a full DATABASE_URL, or the
# individual DB_* parts below (MySQL dev default).
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "firstfind")
    # quote_plus so special chars in the password (@ : / etc.) don't break URL parsing.
    DATABASE_URL = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

JWT_SECRET = os.environ.get("FIRSTFIND_JWT_SECRET", "dev-secret-change-in-prod")

# Google sign-in. Set GOOGLE_CLIENT_ID (the Web client id from Google Cloud) on
# both Render (backend) and as VITE_GOOGLE_CLIENT_ID on Vercel (frontend).
# Leave empty to disable the feature entirely — the /api/auth/google endpoint
# returns 503 and the frontend hides the button.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# ---- Chatbot LLM (Groq) ----
# When set, the chatbot uses Groq to phrase replies naturally; retrieval stays in
# our DB. Without a key it falls back to the rule-based engine (works offline).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
JWT_ALGO = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

# Allowed browser origins. In production set CORS_ORIGINS to your Vercel domain(s),
# comma-separated (e.g. "https://thriftfind.vercel.app"); it REPLACES the localhost
# defaults used for dev.
_DEFAULT_CORS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
]
_env_cors = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGINS = _env_cors or _DEFAULT_CORS

CITY_CENTER = (12.9716, 77.5946)  # Bengaluru
N_ZONES = 4
SEED = 42

# Zonal feature constants (Phase 1+)
MAX_RADIUS_KM = 10.0        # hard cap on any zone radius
DEFAULT_MAX_SHOPS = 8       # Mode B: cap before suggesting a split

# ---- Chat pillar feature flags ----
# Each flag defaults ON so the best experience is out-of-the-box.
# Set to "false" in .env to disable a pillar and fall back to baseline behaviour.
CHAT_GEO    = os.environ.get("CHAT_GEO",    "true").lower() == "true"
CHAT_STATE  = os.environ.get("CHAT_STATE",  "true").lower() == "true"
CHAT_TRIPS  = os.environ.get("CHAT_TRIPS",  "true").lower() == "true"
CHAT_MAP    = os.environ.get("CHAT_MAP",    "true").lower() == "true"
CHAT_ADVICE = os.environ.get("CHAT_ADVICE", "true").lower() == "true"

# ---- Review ingestion ----
# Google Places API key — used by the daily store verification.
# Without this key the ingester runs in CSV-only mode (loads the local archive).
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
# Hard cap on Places API calls per ingest run (Find Place + Details).
# Prevents a bug from looping into the paid tier. Default fits a 100-calls/day key.
INGEST_MAX_CALLS = int(os.environ.get("INGEST_MAX_CALLS", "90"))
# Minimum milliseconds between successive Places API calls (QPS guard).
INGEST_MIN_INTERVAL_MS = int(os.environ.get("INGEST_MIN_INTERVAL_MS", "150"))

# ---- Sentiment via HuggingFace Inference API ----
# The backend no longer loads a local transformer. It calls HuggingFace over HTTP
# with this token, keeping the image light (no torch/transformers). Without a token
# the app falls back to VADER so it never hard-fails.
hf_token = os.environ.get("HUGGINGFACE_TOKEN")
# One or more hosted sentiment classifiers, comma-separated. Their class
# probabilities are averaged (soft vote) — see ml/sentiment.py. Compare
# candidates with `python -m app.ml.eval_sentiment --models a,b` before changing.
# HF_SENTIMENT_MODEL (singular) is still honoured for older .env files.
# Measured on data/sentiment_eval.csv (106 labelled reviews, Nov 2026):
#   XLM-R alone            75% overall | 93% English | 82% Hindi+Hinglish | 48% South Indian
#   + tabularisai (vote)   68% overall | 90% English | 60% Hindi+Hinglish | 58% South Indian
# Reviews here are mostly English and Hinglish, so the single model is the default.
_DEFAULT_SENTIMENT_MODELS = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
HF_SENTIMENT_MODELS = [m.strip() for m in os.environ.get(
    "HF_SENTIMENT_MODELS",
    os.environ.get("HF_SENTIMENT_MODEL", _DEFAULT_SENTIMENT_MODELS)).split(",") if m.strip()]
# HuggingFace retired the classic api-inference.huggingface.co serverless host in
# favour of the Inference Providers router. hf-inference is the first-party provider.
HF_API_BASE = os.environ.get(
    "HF_API_BASE", "https://router.huggingface.co/hf-inference/models").rstrip("/")
HF_TIMEOUT = float(os.environ.get("HF_TIMEOUT", "10"))
# Run the sentiment models inside this process (needs `torch` + `transformers`
# installed) instead of calling the HF Inference API. The daily GitHub job sets
# this: it has the memory for it and it costs nothing, whereas the hosted API
# needs paid inference credits. The web server leaves it off (no torch there).
SENTIMENT_LOCAL = os.environ.get("SENTIMENT_LOCAL", "false").lower() == "true"
LOCAL_SENTIMENT_MODELS = [m.strip() for m in os.environ.get(
    "LOCAL_SENTIMENT_MODELS", ",".join(HF_SENTIMENT_MODELS)).split(",") if m.strip()]
# Below this top-class probability the model vote is treated as unsure, and the
# review's own star rating is added as a tie-breaking voter.
SENTIMENT_MIN_CONFIDENCE = float(os.environ.get("SENTIMENT_MIN_CONFIDENCE", "0.6"))

# ---- Store descriptions ----
# Stores without a Google description get a two-sentence AI summary written by
# the Groq LLM from their categories and review text (labelled as AI in the UI).
# Needs GROQ_API_KEY; capped per pipeline run to respect the free rate limit.
DESCRIPTION_BATCH = int(os.environ.get("DESCRIPTION_BATCH", "40"))
DESCRIPTION_MIN_REVIEWS = int(os.environ.get("DESCRIPTION_MIN_REVIEWS", "2"))

# ---- Google Places free-tier guard ----
# Review-bearing Place Details calls are in Google's most expensive tier, which
# has the smallest free allowance. The defaults fit a key limited to 100 calls
# per day (10 spare for manual checks): the job runs daily and each run stops
# at INGEST_MAX_CALLS total calls. Raise both if your key allows more.
INGEST_MAX_DETAILS = int(os.environ.get("INGEST_MAX_DETAILS", "90"))

# Data files the running app needs. They live inside the package because the
# deployed image contains only app/ — anything under the repo's data/ folder
# is available to jobs and local tools, never to the live server.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# System account that owns all externally-ingested reviews.
# auth_provider="system" distinguishes it from real users everywhere.
BOT_EMAIL = "reviews-bot@thriftfind.local"
BOT_NAME = "Reviews Bot"
