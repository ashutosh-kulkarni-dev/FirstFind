# FirstFind data scrapers

Three scripts, one per source. Install deps once: `pip install -r requirements.txt`

## 1. instagram_scraper.py — thrift store accounts
No API key. Anonymous by default.

```
python instagram_scraper.py --profile store_username --max-posts 30
python instagram_scraper.py --post https://www.instagram.com/p/SHORTCODE/
python instagram_scraper.py --profile store_username --media            # + images/videos
python instagram_scraper.py --profile store_username --comments --login throwaway_user
```

Rules of survival: keep `--max-posts` ≤ 50 per run, wait hours between runs,
never log in with your personal account. Comments require login. If you see
401/429 errors, stop for the day. This violates Meta ToS — research use only.

## 2. google_reviews_scraper.py — store details + reviews (legal, stable)
Needs a free API key (console.cloud.google.com → enable "Places API (New)").

```
python google_reviews_scraper.py --api-key KEY --query "thrift store in Bengaluru" --max-places 40
python google_reviews_scraper.py --api-key KEY --place-id ChIJxxxx
```

Hard limit: Google returns max **5 reviews per place**. For a bigger review
corpus, crowd-source on your own platform or pay Outscraper/SerpApi.

## 3. reddit_scraper.py — official API, most reliable
Free credentials: reddit.com/prefs/apps → create "script" app.

```
python reddit_scraper.py --client-id ID --client-secret SECRET --subreddit bangalore --search "thrift store" --limit 100
python reddit_scraper.py --client-id ID --client-secret SECRET --post POST_URL --comments
```

## Output
Each script writes CSV (flat, for pandas) + JSON (full, incl. comments) into `./output/`.
