"""Groq LLM integration for the chatbot (Phase 6).

The rule-based engine (chatbot.py) still owns intent detection, DB retrieval and
store cards — exact, free, and offline-safe. When GROQ_API_KEY is set, Groq
rephrases the draft reply conversationally, grounded strictly in the stores we
actually retrieved (it is told never to invent stores). Any failure — no key,
timeout, HTTP error — falls back to the rule-based draft, so chat never breaks.
"""
import logging

import httpx

from ..config import GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_SYSTEM = (
    "You are FirstFind, a friendly guide to clothes shopping in Bengaluru. Rewrite "
    "the assistant's draft reply in at most two short sentences (under 40 words), "
    "warm and plain, like a friend who knows the city. The app shows the stores as "
    "cards right under your reply, so don't list them — mention one or two only "
    "when a detail answers what the user asked (open now, price, a standout "
    "review). Never invent stores, prices, hours or facts that aren't in the data. "
    "Keep any numbers from the draft. No headings, no bullet points, at most one emoji."
)


def phrase_reply(user_msg: str, base_reply: str, stores: list, intent: str,
                 timeout: float = 8.0) -> str:
    """Return a Groq-rephrased reply, or base_reply on any failure.

    `stores` is the rich per-store context built by the retriever
    (chatbot._build_context) — the ONLY stores/facts the model may use.
    """
    if not GROQ_API_KEY or not base_reply:
        return base_reply
    context = (stores or [])[:6]
    user = (f"User asked: {user_msg}\n"
            f"Intent: {intent}\n"
            f"Draft reply: {base_reply}\n"
            f"Stores with full details (JSON, the ONLY stores you may mention): {context}\n"
            "Rewrite the draft reply naturally, grounded only in these stores and "
            "their details.")
    try:
        r = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": GROQ_MODEL, "temperature": 0.5,
                  "messages": [{"role": "system", "content": _SYSTEM},
                               {"role": "user", "content": user}]},
            timeout=timeout,
        )
        r.raise_for_status()
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        return text or base_reply
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
        log.warning("Groq phrasing failed (%s); using rule-based reply", e)
        return base_reply
