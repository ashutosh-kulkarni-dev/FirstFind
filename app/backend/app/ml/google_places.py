"""Thin client for the Google Places API (New) — https://places.googleapis.com/v1

Shared by the weekly review fetch (ingest_reviews.py) and the candidate-store
verifier (verify_candidates.py). Enable "Places API (New)" for the key in
Google Cloud; the older "Places API" endpoints are not used.

Cost control is built in, because these calls are billed:
  * every request names exactly the fields it wants (X-Goog-FieldMask) — the
    price tier is set by the most expensive field requested;
  * PlacesClient refuses to make more than `max_calls` requests per run;
  * requests are spaced by `min_interval_s`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from ..config import GOOGLE_PLACES_API_KEY, INGEST_MAX_CALLS, INGEST_MIN_INTERVAL_MS

log = logging.getLogger(__name__)

BASE = "https://places.googleapis.com/v1"


class PlacesBudgetExceeded(RuntimeError):
    """Raised when a run has used its allowed number of API calls."""


class PlacesClient:
    def __init__(self, api_key: str = GOOGLE_PLACES_API_KEY,
                 max_calls: int = INGEST_MAX_CALLS,
                 min_interval_s: float = INGEST_MIN_INTERVAL_MS / 1000,
                 http: httpx.Client | None = None):
        if not api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY is not set")
        self._key = api_key
        self._http = http or httpx.Client(timeout=15)
        self.max_calls = max_calls
        self.calls = 0
        self._interval = min_interval_s
        self._last = 0.0

    def _request(self, method: str, url: str, fields: str, json: dict | None = None) -> dict:
        if self.calls >= self.max_calls:
            raise PlacesBudgetExceeded(f"call cap of {self.max_calls} reached")
        wait = self._interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        self._last = time.monotonic()
        resp = self._http.request(
            method, url, json=json,
            headers={"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": fields})
        if resp.status_code >= 400:
            # Surface Google's own message (bad field mask, API not enabled,
            # billing off...) instead of a bare status code.
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:300])
            except ValueError:
                detail = resp.text[:300]
            raise httpx.HTTPStatusError(
                f"Places API {resp.status_code}: {detail}", request=resp.request, response=resp)
        return resp.json()

    def search_text(self, query: str, lat: float, lng: float, fields: str,
                    radius_m: float = 500, page_size: int = 5) -> list[dict]:
        """Text Search biased to a circle. `fields` use the `places.` prefix."""
        data = self._request("POST", f"{BASE}/places:searchText", fields, json={
            "textQuery": query,
            "pageSize": page_size,
            "locationBias": {"circle": {
                "center": {"latitude": lat, "longitude": lng}, "radius": radius_m}},
        })
        return data.get("places", [])

    def details(self, place_id: str, fields: str) -> dict:
        """Place Details. `fields` are bare names (no `places.` prefix)."""
        return self._request("GET", f"{BASE}/places/{place_id}", fields)


def parse_reviews(place: dict) -> list[dict]:
    """Normalise a place's `reviews` to {author, rating, text, created_at}."""
    out = []
    for r in place.get("reviews") or []:
        text = ((r.get("originalText") or {}).get("text")
                or (r.get("text") or {}).get("text") or "")
        created = None
        stamp = r.get("publishTime")
        if stamp:
            try:
                created = datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                created = None
        try:
            rating = max(1, min(5, int(r.get("rating", 3))))
        except (TypeError, ValueError):
            rating = 3
        out.append({
            "author": (r.get("authorAttribution") or {}).get("displayName", ""),
            "rating": rating,
            "text": text,
            "created_at": created,
        })
    return out
