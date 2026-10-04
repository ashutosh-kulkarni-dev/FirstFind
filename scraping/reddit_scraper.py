#!/usr/bin/env python3
"""
Reddit scraper for FirstFind — posts + comments from a subreddit, user, or single post.

Uses the OFFICIAL Reddit API via praw. Legal, stable, free.

Setup (5 minutes):
    1. Go to https://www.reddit.com/prefs/apps -> "create another app" -> type "script"
    2. Note the client_id (under the app name) and client_secret
    3. pip install praw

Usage:
    # Search a subreddit (e.g. thrift store mentions in r/bangalore)
    python reddit_scraper.py --client-id ID --client-secret SECRET \
        --subreddit bangalore --search "thrift store" --limit 100

    # Top/new posts from a subreddit
    python reddit_scraper.py --client-id ID --client-secret SECRET \
        --subreddit ThriftStoreHauls --sort new --limit 50

    # All posts by a user
    python reddit_scraper.py --client-id ID --client-secret SECRET --user some_username

    # Single post (with full comment tree)
    python reddit_scraper.py --client-id ID --client-secret SECRET \
        --post https://www.reddit.com/r/bangalore/comments/abc123/... --comments

Output:
    ./output/reddit/posts.csv, posts.json (comments included in JSON with --comments)
"""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    import praw
except ImportError:
    sys.exit("praw not installed. Run: pip install praw")


def submission_to_dict(sub, include_comments: bool = False, comment_limit: int = 200) -> dict:
    data = {
        "id": sub.id,
        "url": f"https://www.reddit.com{sub.permalink}",
        "subreddit": str(sub.subreddit),
        "author": str(sub.author) if sub.author else "[deleted]",
        "created_utc": sub.created_utc,
        "title": sub.title,
        "text": sub.selftext or "",
        "score": sub.score,
        "upvote_ratio": sub.upvote_ratio,
        "num_comments": sub.num_comments,
        "link_url": sub.url,
        "is_video": sub.is_video,
    }
    if include_comments:
        sub.comments.replace_more(limit=0)  # drop "load more" stubs, keep it fast
        comments = []
        for c in sub.comments.list()[:comment_limit]:
            comments.append({
                "id": c.id,
                "author": str(c.author) if c.author else "[deleted]",
                "body": c.body,
                "score": c.score,
                "created_utc": c.created_utc,
                "parent_id": c.parent_id,
            })
        data["comments"] = comments
    return data


def save(rows: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "posts.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["id", "url", "subreddit", "author", "created_utc", "title",
              "text", "score", "upvote_ratio", "num_comments"]
    with open(out_dir / "posts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"Saved {len(rows)} posts -> {out_dir}/posts.csv and posts.json")


def main():
    ap = argparse.ArgumentParser(description="Reddit scraper (official API)")
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--user-agent", default="FirstFind research scraper v1.0")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--subreddit")
    src.add_argument("--user", help="Redditor username")
    src.add_argument("--post", help="Single post URL or ID")
    ap.add_argument("--search", help="Search query within the subreddit")
    ap.add_argument("--sort", default="new", choices=["new", "hot", "top", "relevance"])
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--comments", action="store_true", help="Also fetch comments (slower)")
    ap.add_argument("--out", default="output/reddit")
    args = ap.parse_args()

    reddit = praw.Reddit(
        client_id=args.client_id,
        client_secret=args.client_secret,
        user_agent=args.user_agent,
    )
    reddit.read_only = True

    rows = []
    if args.post:
        if args.post.startswith("http"):
            sub = reddit.submission(url=args.post)
        else:
            sub = reddit.submission(id=args.post)
        rows.append(submission_to_dict(sub, include_comments=True))
    elif args.user:
        for sub in reddit.redditor(args.user).submissions.new(limit=args.limit):
            rows.append(submission_to_dict(sub, include_comments=args.comments))
    else:
        sr = reddit.subreddit(args.subreddit)
        if args.search:
            it = sr.search(args.search, sort=args.sort, limit=args.limit)
        elif args.sort == "new":
            it = sr.new(limit=args.limit)
        elif args.sort == "hot":
            it = sr.hot(limit=args.limit)
        else:
            it = sr.top(limit=args.limit)
        for i, sub in enumerate(it, 1):
            print(f"[{i}] {sub.title[:70]}")
            rows.append(submission_to_dict(sub, include_comments=args.comments))

    save(rows, Path(args.out))


if __name__ == "__main__":
    main()
