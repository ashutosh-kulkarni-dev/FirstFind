"""Sentiment analysis on reviews — classifier models only, no LLM.

Engine: a small ENSEMBLE of multilingual sentiment classifiers called through
the HuggingFace Inference API (models listed in config.HF_SENTIMENT_MODELS):

  * cardiffnlp/twitter-xlm-roberta-base-sentiment — XLM-R tuned on tweets in 8
    languages incl. Hindi and English; good on short, informal text.
  * tabularisai/multilingual-sentiment-analysis — 23 languages incl. Hindi,
    Bengali and Telugu.

Each model returns class probabilities; they are mapped to
negative / neutral / positive and averaged (soft vote). Reviews here are often
code-mixed (Hinglish, Kanglish), which no hosted classifier is trained on
specifically, so two safeguards apply:

  * Star-rating tie-break — when the vote is unsure (top probability below
    SENTIMENT_MIN_CONFIDENCE) and the review has a star rating, the rating is
    added as one more voter. The stars are the reviewer's own verdict.
  * VADER fallback — with no token, or if every model call fails.

The models are NOT loaded into this process (no torch on the server): one
HTTP call per model per review, off the request path.

Whether this is good enough per language is a number, not an assumption:
    python -m app.ml.eval_sentiment

Public interface:
    analyze(text, rating=None) -> (label, compound score in [-1, 1])
    experience_score(reviews, prior_mean=None) -> float | None
"""
import logging
import re

import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import (HF_API_BASE, HF_SENTIMENT_MODELS, HF_TIMEOUT,
                        SENTIMENT_MIN_CONFIDENCE, hf_token)

log = logging.getLogger(__name__)

CLASSES = ("negative", "neutral", "positive")

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
    """Best-effort: nudge the HF models out of a cold start at boot.

    Any failure is ignored — this is purely an optimization.
    """
    if not hf_token:
        return
    for model in HF_SENTIMENT_MODELS:
        try:
            _hf_probs(model, "ok")
        except Exception as e:
            log.info("Sentiment: warmup ping for %s failed (%s); will retry on demand", model, e)


def _vader_analyze(text: str) -> tuple[str, float]:
    compound = _vader.polarity_scores(text)["compound"]
    if compound >= 0.05:
        return "positive", compound
    if compound <= -0.05:
        return "negative", compound
    return "neutral", compound


# ---------------------------------------------------------------------------
# Hosted classifiers
# ---------------------------------------------------------------------------

_STARS_RE = re.compile(r"^([1-5])\s*stars?$")


def to_three_class(scores: list[dict]) -> dict[str, float]:
    """Map any sentiment model's labels onto negative / neutral / positive.

    Handles 3-class names, generic LABEL_0..2, 5-class "Very Negative" ..
    "Very Positive", and star-rating models ("1 star" .. "5 stars").
    Returns probabilities that sum to 1.
    """
    out = dict.fromkeys(CLASSES, 0.0)
    for item in scores:
        label, p = str(item["label"]).strip().lower(), float(item["score"])
        stars = _STARS_RE.match(label)
        if stars:
            n = int(stars.group(1))
            out["negative" if n <= 2 else "neutral" if n == 3 else "positive"] += p
        elif "neg" in label or label == "label_0":
            out["negative"] += p
        elif "pos" in label or label == "label_2":
            out["positive"] += p
        elif "neu" in label or label == "label_1":
            out["neutral"] += p
    total = sum(out.values())
    if total <= 0:
        raise ValueError(f"no recognisable sentiment labels in {scores!r}")
    return {k: v / total for k, v in out.items()}


def _hf_probs(model: str, text: str) -> dict[str, float]:
    """One model via the HF Inference API -> 3-class probabilities. Raises on failure."""
    # top_k=None returns scores for ALL labels; without it the provider may
    # return only the top one.
    resp = _get_client().post(
        f"{HF_API_BASE}/{model}",
        json={"inputs": text[:2000], "parameters": {"top_k": None}},
    )
    resp.raise_for_status()
    data = resp.json()
    # [[{'label':..,'score':..}, ...]] or a flat [{...}] — handle both.
    scores = data[0] if data and isinstance(data[0], list) else data
    return to_three_class(scores)


def rating_probs(rating: int) -> dict[str, float]:
    """A star rating expressed as a (soft) vote over the three classes."""
    if rating >= 4:
        return {"negative": 0.05, "neutral": 0.15, "positive": 0.80}
    if rating <= 2:
        return {"negative": 0.80, "neutral": 0.15, "positive": 0.05}
    return {"negative": 0.20, "neutral": 0.60, "positive": 0.20}


def _average(votes: list[dict[str, float]]) -> dict[str, float]:
    return {c: sum(v[c] for v in votes) / len(votes) for c in CLASSES}


def ensemble_probs(text: str, models: list[str] | None = None) -> dict[str, float] | None:
    """Soft vote of every model that answers; None if none did."""
    votes = []
    for model in (models or HF_SENTIMENT_MODELS):
        try:
            votes.append(_hf_probs(model, text))
        except Exception as e:
            log.warning("Sentiment: %s failed (%s)", model, e)
    return _average(votes) if votes else None


def _decide(probs: dict[str, float]) -> tuple[str, float]:
    label = max(CLASSES, key=lambda c: probs[c])
    # compound in [-1, 1] keeps experience_score()'s math unchanged.
    return label, round(probs["positive"] - probs["negative"], 4)


def analyze(text: str, rating: int | None = None) -> tuple[str, float]:
    """Returns (label, compound score in [-1, 1]). Never raises.

    `rating` (1-5 stars) is optional; it is only consulted when the models
    are unsure about the text.
    """
    global _warned_no_token
    if not text or not text.strip():
        return "neutral", 0.0
    if not hf_token:
        if not _warned_no_token:
            log.warning("Sentiment: no HUGGINGFACE_TOKEN set; using VADER fallback")
            _warned_no_token = True
        return _vader_analyze(text)

    probs = ensemble_probs(text)
    if probs is None:
        log.warning("Sentiment: every HF model failed; VADER fallback")
        return _vader_analyze(text)
    if rating is not None and max(probs.values()) < SENTIMENT_MIN_CONFIDENCE:
        probs = _average([probs, rating_probs(rating)])
    return _decide(probs)


# ---------------------------------------------------------------------------
# Store-level AI score
# ---------------------------------------------------------------------------

# A store's score is pulled toward a prior until it has enough reviews, so one
# 5-star review does not produce a 5.0. PRIOR_WEIGHT is "how many reviews the
# prior is worth"; the prior is the store's Google rating when known.
PRIOR_WEIGHT = 5
DEFAULT_PRIOR = 4.0


def experience_score(reviews: list, prior_mean: float | None = None,
                     prior_weight: int = PRIOR_WEIGHT) -> float | None:
    """AI score in [1, 5]: star ratings (70%) blended with sentiment (30%),
    then shrunk toward a prior according to how few reviews there are.

    reviews: list of (rating:int, sentiment_score:float | None) tuples. Pass
    None as the sentiment for a review with no text (or not yet scored) so it
    counts toward the rating average but does not drag sentiment to neutral.
    """
    if not reviews:
        return None
    n = len(reviews)
    avg_rating = sum(r for r, _ in reviews) / n
    sents = [s for _, s in reviews if s is not None]
    if sents:
        avg_sent = sum(sents) / len(sents)                 # [-1, 1]
        sent_as_stars = (avg_sent + 1) / 2 * 4 + 1         # -> [1, 5]
        raw = 0.7 * avg_rating + 0.3 * sent_as_stars
    else:
        raw = avg_rating
    prior = prior_mean if prior_mean else DEFAULT_PRIOR
    return round((prior_weight * prior + n * raw) / (prior_weight + n), 2)


# A Google rating only counts as a prior once enough people stand behind it.
MIN_GOOGLE_REVIEWS_FOR_PRIOR = 20


def score_prior(store) -> float | None:
    """Prior mean for a store's AI score: its Google rating when that rating
    rests on enough reviews, else None (-> DEFAULT_PRIOR)."""
    if store.google_rating and (store.google_review_count or 0) >= MIN_GOOGLE_REVIEWS_FOR_PRIOR:
        return store.google_rating
    return None


def review_tuple(review) -> tuple[int, float | None]:
    """(rating, sentiment) for experience_score — sentiment only if there is text."""
    has_text = bool((review.text or "").strip())
    return review.rating, (review.sentiment_score if has_text else None)
