#!/usr/bin/env python3
"""
Instagram scraper for ThriftFind — scrape posts from a profile or a single post URL.

Uses instaloader (no API key needed). Anonymous by default.

WARNING:
- Scraping Instagram violates Meta's ToS. Use for research/academic purposes only.
- Anonymous scraping gets rate-limited after ~50-100 requests. Go slow.
- Fetching COMMENTS requires login. Use a throwaway account, never your personal one.
- If you get 401/429 errors, stop and wait a few hours.

Install:
    pip install instaloader

Usage:
    # Scrape 60 posts in batches of 10 (safest)
    python instagram_scraper.py --profile bangalore_thrift_store --max-posts 60

    # Custom batch size and delays
    python instagram_scraper.py --profile some_store --max-posts 100 --batch-size 15 --batch-delay 60

    # Download images/videos too
    python instagram_scraper.py --profile some_store --max-posts 30 --media

    # Single post by URL or shortcode
    python instagram_scraper.py --post https://www.instagram.com/p/Cxyz123AbCd/

    # Include comments (requires login with a throwaway account)
    python instagram_scraper.py --profile some_store --comments --login your_throwaway_user

Output:
    ./output/<profile>/posts.csv and posts.json
    ./output/<profile>/media/  (if --media)

Batch behaviour:
    Posts are fetched in groups of --batch-size (default 10).
    Between each post:  2–6 s random sleep
    Between each batch: --batch-delay ± 30 % random jitter (default 45 s)
    On a 429/rate-limit error: waits --retry-wait seconds then retries (up to 3 times).
    Results are saved after every batch so partial runs aren't lost.
"""

import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path

try:
    import instaloader
except ImportError:
    sys.exit("instaloader not installed. Run: pip install instaloader")

# ── tuneable defaults ──────────────────────────────────────────────────────────
POST_SLEEP_MIN = 2       # seconds between individual posts (lower bound)
POST_SLEEP_MAX = 6       # seconds between individual posts (upper bound)
DEFAULT_BATCH_SIZE = 10  # posts per batch
DEFAULT_BATCH_DELAY = 45 # seconds to pause between batches
DEFAULT_RETRY_WAIT = 120 # seconds to wait after a rate-limit hit
MAX_RETRIES = 3
# ──────────────────────────────────────────────────────────────────────────────


def jitter(base: float, pct: float = 0.30) -> float:
    """Return base ± pct random jitter, always positive."""
    delta = base * pct
    return max(1.0, base + random.uniform(-delta, delta))


def shortcode_from_url(url: str) -> str:
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else url


def post_to_dict(post, include_comments: bool = False) -> dict:
    data = {
        "shortcode": post.shortcode,
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "owner": post.owner_username,
        "date_utc": post.date_utc.isoformat(),
        "caption": post.caption or "",
        "hashtags": list(post.caption_hashtags),
        "mentions": list(post.caption_mentions),
        "likes": post.likes,
        "comment_count": post.comments,
        "is_video": post.is_video,
        "video_url": post.video_url if post.is_video else None,
        "image_url": post.url,
        "location": post.location.name if post.location else None,
    }
    if include_comments:
        comments = []
        try:
            for c in post.get_comments():
                comments.append({
                    "user": c.owner.username,
                    "text": c.text,
                    "date_utc": c.created_at_utc.isoformat(),
                    "likes": c.likes_count,
                })
        except Exception as e:
            print(f"  ! could not fetch comments for {post.shortcode}: {e}")
        data["comments"] = comments
    return data


def download_media(loader, post, media_dir: Path):
    try:
        loader.download_post(post, target=str(media_dir))
    except Exception as e:
        print(f"  ! media download failed for {post.shortcode}: {e}")


def save_outputs(rows: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "posts.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    csv_fields = ["shortcode", "url", "owner", "date_utc", "caption", "hashtags",
                  "likes", "comment_count", "is_video", "location"]
    with open(out_dir / "posts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            row["hashtags"] = " ".join(row.get("hashtags", []))
            w.writerow(row)


def fetch_post_with_retry(loader, post, include_comments, media, media_dir,
                          retry_wait, max_retries) -> dict | None:
    """Fetch one post's data, retrying up to max_retries times on rate-limit."""
    for attempt in range(1, max_retries + 1):
        try:
            data = post_to_dict(post, include_comments=include_comments)
            if media:
                download_media(loader, post, media_dir)
            return data
        except instaloader.exceptions.TooManyRequestsException:
            wait = jitter(retry_wait)
            print(f"  ! Rate limited (attempt {attempt}/{max_retries}). "
                  f"Sleeping {wait:.0f}s …")
            time.sleep(wait)
        except Exception as e:
            print(f"  ! Unexpected error on {post.shortcode}: {e}")
            return None
    print(f"  ! Gave up on {post.shortcode} after {max_retries} retries.")
    return None


def scrape_profile(loader, profile_name, max_posts, batch_size, batch_delay,
                   retry_wait, include_comments, media, out_dir):
    try:
        profile = instaloader.Profile.from_username(loader.context, profile_name)
    except Exception as e:
        sys.exit(f"Could not load profile '{profile_name}': {e}")

    total_available = profile.mediacount
    target = min(max_posts, total_available)
    print(f"Scraping @{profile.username}  ({total_available} posts on profile, "
          f"targeting {target})")
    print(f"Batch size: {batch_size}  |  Batch delay: ~{batch_delay}s  |  "
          f"Post delay: {POST_SLEEP_MIN}–{POST_SLEEP_MAX}s\n")

    rows = []
    batch_num = 0
    post_iter = profile.get_posts()

    for i in range(1, target + 1):
        # ── advance iterator ───────────────────────────────────────────────
        try:
            post = next(post_iter)
        except StopIteration:
            print("No more posts available.")
            break

        print(f"[{i}/{target}] {post.shortcode}  ({post.date_utc.date()})")

        data = fetch_post_with_retry(
            loader, post, include_comments, media,
            out_dir / "media", retry_wait, MAX_RETRIES
        )
        if data:
            rows.append(data)

        # ── inter-post sleep ───────────────────────────────────────────────
        if i < target:
            sleep = random.uniform(POST_SLEEP_MIN, POST_SLEEP_MAX)
            time.sleep(sleep)

        # ── end-of-batch: save + longer pause ─────────────────────────────
        if i % batch_size == 0 and i < target:
            batch_num += 1
            save_outputs(rows, out_dir)
            wait = jitter(batch_delay)
            print(f"\n── Batch {batch_num} done ({i}/{target} posts). "
                  f"Pausing {wait:.0f}s before next batch …\n")
            time.sleep(wait)

    save_outputs(rows, out_dir)
    print(f"\nDone. Saved {len(rows)} posts to {out_dir / 'posts.csv'} "
          f"and posts.json")


def main():
    ap = argparse.ArgumentParser(description="Scrape Instagram posts (ThriftFind)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--profile", help="Username of the account to scrape")
    src.add_argument("--post",    help="Single post URL or shortcode")

    ap.add_argument("--max-posts",   type=int, default=50,
                    help="Total posts to scrape from a profile (default 50)")
    ap.add_argument("--batch-size",  type=int, default=DEFAULT_BATCH_SIZE,
                    help=f"Posts per batch before a longer pause (default {DEFAULT_BATCH_SIZE})")
    ap.add_argument("--batch-delay", type=float, default=DEFAULT_BATCH_DELAY,
                    help=f"Seconds to pause between batches (default {DEFAULT_BATCH_DELAY})")
    ap.add_argument("--retry-wait",  type=float, default=DEFAULT_RETRY_WAIT,
                    help=f"Seconds to wait after a rate-limit error (default {DEFAULT_RETRY_WAIT})")

    ap.add_argument("--comments", action="store_true",
                    help="Also fetch comments (requires --login)")
    ap.add_argument("--media",    action="store_true",
                    help="Download images/videos too")
    ap.add_argument("--login",    help="Instagram username to log in as "
                                       "(use a throwaway; prompts for password)")
    ap.add_argument("--out",      default="output", help="Output directory root")
    args = ap.parse_args()

    if args.comments and not args.login:
        sys.exit("--comments requires --login (Instagram blocks anonymous comment access)")

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    if args.login:
        import getpass
        pw = getpass.getpass(f"Password for {args.login}: ")
        try:
            loader.login(args.login, pw)
            print("Logged in.")
        except Exception as e:
            sys.exit(f"Login failed: {e}")

    if args.post:
        shortcode = shortcode_from_url(args.post)
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        out_dir = Path(args.out) / post.owner_username
        out_dir.mkdir(parents=True, exist_ok=True)
        data = fetch_post_with_retry(
            loader, post, args.comments, args.media,
            out_dir / "media", args.retry_wait, MAX_RETRIES
        )
        if data:
            save_outputs([data], out_dir)
            print(f"Saved 1 post to {out_dir}")
    else:
        out_dir = Path(args.out) / args.profile
        scrape_profile(
            loader=loader,
            profile_name=args.profile,
            max_posts=args.max_posts,
            batch_size=args.batch_size,
            batch_delay=args.batch_delay,
            retry_wait=args.retry_wait,
            include_comments=args.comments,
            media=args.media,
            out_dir=out_dir,
        )


if __name__ == "__main__":
    main()
