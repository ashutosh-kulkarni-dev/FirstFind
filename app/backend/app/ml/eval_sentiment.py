"""Measure sentiment accuracy per language on a labelled test set.

Makes "is the model working for Hinglish / Indian languages?" a number instead
of an assumption, and lets you choose models by evidence. Run it before
changing HF_SENTIMENT_MODELS.

Test set: data/sentiment_eval.csv  (text,label,lang) — hand-written reviews in
English, Hinglish, Hindi, Kannada, Tamil, Telugu and their romanised forms.

Columns in the report:
  vader      offline English lexicon (the no-token fallback)
  <model>    each hosted HuggingFace model on its own   (needs HUGGINGFACE_TOKEN)
  ensemble   what production uses: the soft vote of HF_SENTIMENT_MODELS

Run from app/backend:
    python -m app.ml.eval_sentiment
    python -m app.ml.eval_sentiment --show-errors
    # try other hosted models before adopting them:
    python -m app.ml.eval_sentiment --models cardiffnlp/twitter-xlm-roberta-base-sentiment,lxyuan/distilbert-base-multilingual-cased-sentiments-student
"""
from __future__ import annotations

import argparse
import csv
import time
from collections import defaultdict
from pathlib import Path

from ..config import HF_SENTIMENT_MODELS, REPO_ROOT, hf_token
from . import sentiment as S

EVAL_CSV = REPO_ROOT / "data" / "sentiment_eval.csv"


def _label(probs: dict) -> str:
    return max(S.CLASSES, key=lambda c: probs[c])


def build_engines(models: list[str]) -> dict:
    eng = {"vader": lambda t: S._vader_analyze(t)[0]}
    if hf_token:
        for m in models:
            eng[m.split("/")[-1][:28]] = lambda t, m=m: _label(S._hf_probs(m, t))
        if len(models) > 1:
            def vote(t):
                probs = S.ensemble_probs(t, models)
                if probs is None:
                    raise RuntimeError("all models failed")
                return _label(probs)
            eng["ensemble"] = vote
    return eng


def evaluate(predict, rows: list[dict], pause: float = 0.0) -> tuple[dict, list]:
    """Return ({lang: (correct, total)}, [misclassified rows])."""
    stats: dict = defaultdict(lambda: [0, 0])
    errors = []
    for row in rows:
        try:
            got = predict(row["text"])
        except Exception as e:      # an engine outage is a miss, not a crash
            got = f"error: {e}"
        ok = got == row["label"]
        for key in (row["lang"], "ALL"):
            stats[key][0] += ok
            stats[key][1] += 1
        if not ok:
            errors.append({**row, "got": got})
        if pause:
            time.sleep(pause)
    return {k: tuple(v) for k, v in stats.items()}, errors


def load_rows(path: Path = EVAL_CSV) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("text")]


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-language sentiment accuracy")
    ap.add_argument("--models", default=",".join(HF_SENTIMENT_MODELS),
                    help="comma-separated HF model ids to compare (default: the configured ones)")
    ap.add_argument("--csv", type=Path, default=EVAL_CSV)
    ap.add_argument("--show-errors", action="store_true")
    ap.add_argument("--pause", type=float, default=0.0,
                    help="seconds between calls (use ~0.5 if the API rate-limits you)")
    args = ap.parse_args()

    rows = load_rows(args.csv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    engines = build_engines(models)
    langs = sorted({r["lang"] for r in rows}) + ["ALL"]
    print(f"{len(rows)} labelled reviews")
    if not hf_token:
        print("HUGGINGFACE_TOKEN is not set — only the offline VADER fallback can be measured.")

    results = {name: evaluate(fn, rows, 0.0 if name == "vader" else args.pause)
               for name, fn in engines.items()}

    width = max(14, max(len(n) for n in results) + 2)
    print("\n" + "lang".ljust(10) + "".join(n.rjust(width) for n in results))
    for lang in langs:
        line = lang.ljust(10)
        for stats, _ in results.values():
            c, t = stats.get(lang, (0, 0))
            line += (f"{c}/{t} ({100 * c / t:.0f}%)" if t else "-").rjust(width)
        print(line)

    if args.show_errors:
        for name, (_, errors) in results.items():
            print(f"\n[{name}] {len(errors)} misclassified:")
            for e in errors:
                print(f"  {e['lang']:9} want={e['label']:8} got={e['got']:8} | {e['text']}")


if __name__ == "__main__":
    main()
