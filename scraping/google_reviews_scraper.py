#!/usr/bin/env python3
"""
Google Maps store + reviews collector for FirstFind (Places API, New).

Fully legal, needs a free API key: https://console.cloud.google.com
Enable "Places API (New)". Free tier covers thousands of calls/month.

HARD LIMIT you must know: the Places API returns at most 5 reviews per place.
There is no official way to get all reviews. For a review-heavy NLP corpus,
combine this with crowd-sourced reviews on your own platform, or use a paid
third-party service (Outscraper, SerpApi).

Install:
    pip install requests

Usage:
    # Search thrift stores in Bengaluru, get details + reviews for each
    python google_reviews_scraper.py --api-key YOUR_KEY --query "thrift store in Bengaluru"

    # A single place by Place ID
    python google_reviews_scraper.py --api-key YOUR_KEY --place-id ChIJxxxxxxxxxxxx

    # More results (paginates, max ~60)
    python google_reviews_scraper.py --api-key YOUR_KEY --query "thrift store in Koramangala" --max-places 40

Output:
    ./output/google/stores.csv, stores.json, reviews.csv
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests not installed. Run: pip install requests")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.location", "places.rating", "places.userRatingCount",
    "places.regularOpeningHours.weekdayDescriptions", "places.priceLevel",
    "places.types", "places.websiteUri", "places.nationalPhoneNumber",
    "places.reviews",
])


def search_places(api_key: str, query: str, max_places: int) -> list:
    """Text search, paginated, returns raw place dicts."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK + ",nextPageToken",
    }
    places, page_token = [], None
    while len(places) < max_places:
        body = {"textQuery": query, "pageSize": min(20, max_places - len(places))}
        if page_token:
            body["pageToken"] = page_token
        r = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if r.status_code != 200:
            sys.exit(f"API error {r.status_code}: {r.text[:500]}")
        data = r.json()
        places.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)  # token needs a moment to become valid
    return places[:max_places]


def get_place(api_key: str, place_id: str) -> dict:
    """Fetch a single place by ID."""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK.replace("places.", ""),
    }
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        sys.exit(f"API error {r.status_code}: {r.text[:500]}")
    return r.json()


def flatten_store(p: dict) -> dict:
    return {
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text"),
        "address": p.get("formattedAddress"),
        "lat": (p.get("location") or {}).get("latitude"),
        "lng": (p.get("location") or {}).get("longitude"),
        "rating": p.get("rating"),
        "rating_count": p.get("userRatingCount"),
        "price_level": p.get("priceLevel"),
        "phone": p.get("nationalPhoneNumber"),
        "website": p.get("websiteUri"),
        "types": "|".join(p.get("types", [])),
        "opening_hours": "; ".join(
            (p.get("regularOpeningHours") or {}).get("weekdayDescriptions", [])
        ),
    }


def flatten_reviews(p: dict) -> list:
    out = []
    for rev in p.get("reviews", []):
        out.append({
            "place_id": p.get("id"),
            "store_name": (p.get("displayName") or {}).get("text"),
            "author": (rev.get("authorAttribution") or {}).get("displayName"),
            "rating": rev.get("rating"),
            "text": ((rev.get("text") or {}).get("text") or "").strip(),
            "publish_time": rev.get("publishTime"),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Google Places store/review collector")
    ap.add_argument("--api-key", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--query", help='e.g. "thrift store in Bengaluru"')
    src.add_argument("--place-id", help="Single Google Place ID")
    ap.add_argument("--max-places", type=int, default=20)
    ap.add_argument("--out", default="output/google")
    args = ap.parse_args()

    if args.place_id:
        raw = [get_place(args.api_key, args.place_id)]
    else:
        raw = search_places(args.api_key, args.query, args.max_places)
        print(f"Found {len(raw)} places for: {args.query}")

    stores = [flatten_store(p) for p in raw]
    reviews = [r for p in raw for r in flatten_reviews(p)]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stores.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(out / "stores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(stores[0].keys()) if stores else [])
        w.writeheader(); w.writerows(stores)

    if reviews:
        with open(out / "reviews.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(reviews[0].keys()))
            w.writeheader(); w.writerows(reviews)

    print(f"Saved {len(stores)} stores, {len(reviews)} reviews -> {out}/")
    print("Note: Google caps reviews at 5 per place. See docstring.")


if __name__ == "__main__":
    main()
