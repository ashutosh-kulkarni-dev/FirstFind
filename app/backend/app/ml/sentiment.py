"""Sentiment analysis on reviews.

Primary engine: the HuggingFace **Inference API** running
``cardiffnlp/twitter-xlm-roberta-base-sentiment`` — it understands the
Hinglish / Indian-English vocabulary of real thrift reviews ("bakwaas",
"mast", "paisa vasool", "sasta") that VADER's English lexicon is blind to.

The model is NOT loaded into this process: we call HuggingFace over HTTP with
``HUGGINGFACE_TOKEN``. This keeps the backend light (no torch/transformers) and
easy to host. If the API is unreachable or no token is set, we fall back to
VADER so the app never hard-fails.

Public interface is unchanged so callers (experience_score, the batch pipeline,
the review background task) don't care how inference happens:
    analyze(text) -> (label, compound score in [-1, 1])
    experience_score(reviews) -> float | None
"""
import logging

import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import HF_API_URL, HF_TIMEOUT, hf_token

log = logging.getLogger(__name__)

_LABELS = {"positive", "neutral", "negative"}
# some checkpoints emit generic label_N ids instead of names
_ID_FALLBACK = {"label_0": "negative", "label_1": "neutral", "label_2": "positive"}

_vader = SentimentIntensityAnalyzer()

_client: httpx.Client | None = None
_warned_no_token = False


def _get_client() -> httpx.Client:
    """Reused HTTP client for the HF Inference API (connection pooling)."""
    global _client
    if _client is None:
        headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
        _client = httpx.Client(timeout=HF_TIMEOUT, headers=headers)
    return _client


def warmup() -> None:
    """Best-effort: nudge the HF model out of a cold start at boot.

    Sends one tiny request (wait_for_model) so the first real review isn't slow.
    Any failure is ignored — this is purely an optimization.
    """
    if not hf_token:
        return
    try:
        _hf_analyze("ok")
    except Exception as e:
        log.info("Sentiment: HF warmup ping failed (%s); will retry on demand", e)


def _vader_analyze(text: str) -> tuple[str, float]:
    compound = _vader.polarity_scores(text)["compound"]
    if compound >= 0.05:
        return "positive", compound
    if compound <= -0.05:
        return "negative", compound
    return "neutral", compound


def _hf_analyze(text: str) -> tuple[str, float]:
    """Call the HuggingFace Inference API. Raises on any failure so analyze() can fall back."""
    # top_k=None returns scores for ALL labels (needed for the pos - neg compound);
    # without it the provider may return only the top label.
    resp = _get_client().post(
        HF_API_URL,
        json={"inputs": text, "parameters": {"top_k": None}},
    )
    resp.raise_for_status()
    data = resp.json()
    # top_k=None style response: [[{'label':..,'score':..}, ...]]. Some shapes
    # return a flat [{...}]; handle both.
    scores = data[0] if data and isinstance(data[0], list) else data
    by = {d["label"].lower(): d["score"] for d in scores}
    label = max(by, key=by.get)
    if label not in _LABELS:
        label = _ID_FALLBACK.get(label, "neutral")
    # compound in [-1, 1] keeps experience_score()'s math identical to before.
    compound = round(by.get("positive", 0.0) - by.get("negative", 0.0), 4)
    return label, compound


def analyze(text: str) -> tuple[str, float]:
    """Returns (label, compound score in [-1, 1]).

    Calls the HF Inference API; falls back to VADER if there's no token or the
    call fails. Runs off the request path (background task / batch pipeline), so
    a network round-trip here is fine.
    """
    global _warned_no_token
    if not text or not text.strip():
        return "neutral", 0.0
    if not hf_token:
        if not _warned_no_token:
            log.warning("Sentiment: no HUGGINGFACE_TOKEN set; using VADER fallback")
            _warned_no_token = True
        return _vader_analyze(text)
    try:
        return _hf_analyze(text)
    except Exception as e:
        log.warning("Sentiment: HF Inference API failed (%s); VADER fallback", e)
        return _vader_analyze(text)


def experience_score(reviews: list) -> float | None:
    """Blend star ratings (70%) with sentiment (30%) over non-flagged reviews.

    reviews: list of (rating:int, sentiment_score:float) tuples.
    """
    if not reviews:
        return None
    avg_rating = sum(r for r, _ in reviews) / len(reviews)
    avg_sent = sum(s for _, s in reviews) / len(reviews)  # [-1, 1]
    sent_as_stars = (avg_sent + 1) / 2 * 4 + 1            # -> [1, 5]
    return round(0.7 * avg_rating + 0.3 * sent_as_stars, 2)
