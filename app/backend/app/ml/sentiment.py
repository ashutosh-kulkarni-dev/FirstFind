"""Sentiment analysis on reviews — classifier models only, no LLM.

Model: cardiffnlp/twitter-xlm-roberta-base-sentiment — XLM-R tuned on tweets
in 8 languages incl. Hindi and English; good on short, informal text. On our
labelled set it beat every alternative and every two- or three-model vote we
tried (see config._DEFAULT_SENTIMENT_MODELS for the numbers).

More than one model can be listed in config.HF_SENTIMENT_MODELS; their class
probabilities are then mapped to negative / neutral / positive and averaged
(soft vote). Reviews here are often
code-mixed (Hinglish, Kanglish), which no hosted classifier is trained on
specifically, so two safeguards apply:

  * Star-rating tie-break — when the vote is unsure (top probability below
    SENTIMENT_MIN_CONFIDENCE) and the review has a star rating, the rating is
    added as one more voter. The stars are the reviewer's own verdict.
  * VADER fallback — with no token, or if every model call fails.

Where the models run (engine, recorded per review in sentiment_engine):
  local  inside this process via `transformers` — used by the daily GitHub job
         (SENTIMENT_LOCAL=true). Free, and not limited to hosted models.
  hf     the HuggingFace Inference API, one HTTP call per model. Needs a token
         WITH inference credits; a "402 Payment Required" switches it off for
         the rest of the run.
  vader  offline English lexicon — the last resort (and what the web server
         uses for a just-posted review when no credits are available). The
         daily job re-scores those with the real models.

Whether this is good enough per language is a number, not an assumption:
    python -m app.ml.eval_sentiment

Public interface:
    analyze(text, rating=None) -> (label, compound score in [-1, 1])
    analyze_detail(text, rating=None) -> (label, compound, engine)
    best_engine() -> the engine analyze would use right now
    experience_score(reviews, prior_mean=None) -> float | None
"""
import importlib.util
import logging
import re

import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import (HF_API_BASE, HF_SENTIMENT_MODELS, HF_TIMEOUT,
                        LOCAL_SENTIMENT_MODELS, SENTIMENT_LOCAL,
                        SENTIMENT_MIN_CONFIDENCE, hf_token)

log = logging.getLogger(__name__)

CLASSES = ("negative", "neutral", "positive")

_vader = SentimentIntensityAnalyzer()

_client: httpx.Client | None = None
_warned_no_token = False
_hf_disabled = False            # set after a 402: no inference credits on this token
_local_pipes: dict = {}         # model id -> loaded transformers pipeline


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
    if not hf_token or local_available():
        return
    for model in HF_SENTIMENT_MODELS:
        try:
            _hf_probs(model, "ok")
        except (httpx.HTTPError, ValueError) as e:
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


def local_available() -> bool:
    """True when the models can run in this process (flag on + libraries present)."""
    return bool(SENTIMENT_LOCAL
                and importlib.util.find_spec("transformers")
                and importlib.util.find_spec("torch"))


def _local_probs(model: str, text: str) -> dict[str, float]:
    """One model run in-process -> 3-class probabilities. Raises on failure."""
    pipe = _local_pipes.get(model)
    if pipe is None:
        from transformers import pipeline          # heavy import: only when used
        log.info("Sentiment: loading %s locally (first use)", model)
        pipe = _local_pipes[model] = pipeline("text-classification", model=model, device=-1)
    scores = pipe(text[:2000], top_k=None, truncation=True, max_length=256)
    if scores and isinstance(scores[0], list):     # batch-shaped output
        scores = scores[0]
    return to_three_class(scores)


def ensemble_probs(text: str, models: list[str] | None = None,
                   engine: str = "hf") -> dict[str, float] | None:
    """Soft vote of every model that answers; None if none did."""
    global _hf_disabled
    run = _local_probs if engine == "local" else _hf_probs
    default = LOCAL_SENTIMENT_MODELS if engine == "local" else HF_SENTIMENT_MODELS
    votes = []
    for model in (models or default):
        try:
            votes.append(run(model, text))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402 and not _hf_disabled:
                _hf_disabled = True
                log.error("Sentiment: HuggingFace returned 402 Payment Required — this token "
                          "has no inference credits. Hosted models are off for this run.")
            else:
                log.warning("Sentiment: %s failed (%s)", model, e)
            if _hf_disabled:
                break
        except Exception as e:  # noqa: BLE001 - a local model can fail in many ways; fall back to the next engine
            log.warning("Sentiment: %s failed (%s)", model, e)
    return _average(votes) if votes else None


def _decide(probs: dict[str, float]) -> tuple[str, float]:
    label = max(CLASSES, key=lambda c: probs[c])
    # compound in [-1, 1] keeps experience_score()'s math unchanged.
    return label, round(probs["positive"] - probs["negative"], 4)


def best_engine() -> str:
    """The engine analyze_detail() would try first right now."""
    if local_available():
        return "local"
    if hf_token and not _hf_disabled:
        return "hf"
    return "vader"


def analyze_detail(text: str, rating: int | None = None) -> tuple[str, float, str]:
    """Returns (label, compound score in [-1, 1], engine). Never raises.

    `rating` (1-5 stars) is optional; it is only consulted when the models
    are unsure about the text.
    """
    global _warned_no_token
    if not text or not text.strip():
        return "neutral", 0.0, "none"

    for engine in ("local", "hf"):
        if engine == "local" and not local_available():
            continue
        if engine == "hf" and (not hf_token or _hf_disabled):
            continue
        probs = ensemble_probs(text, engine=engine)
        if probs is None:
            continue
        if rating is not None and max(probs.values()) < SENTIMENT_MIN_CONFIDENCE:
            probs = _average([probs, rating_probs(rating)])
        return (*_decide(probs), engine)

    if not _warned_no_token:
        log.warning("Sentiment: no model engine available (no local models, no usable "
                    "HUGGINGFACE_TOKEN); using the English-only VADER fallback")
        _warned_no_token = True
    return (*_vader_analyze(text), "vader")


def analyze(text: str, rating: int | None = None) -> tuple[str, float]:
    """Returns (label, compound score in [-1, 1]). Never raises."""
    label, score, _engine = analyze_detail(text, rating)
    return label, score


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
