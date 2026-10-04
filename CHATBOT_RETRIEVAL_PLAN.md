# Chatbot Retrieval Pipeline — Execution Plan

**Status:** proposed (awaiting approval). No code changes until approved.

## Objective

Give the conversational chatbot a **token-free retrieval pipeline** that feeds a
**rich, grounded context** to the LLM, which keeps doing the one thing it's good
at — natural phrasing. Retrieval (understanding + fetching + context assembly)
spends **zero tokens**; tokens are spent **only** in the final phrasing step.

## Principles (locked in from discussion)

1. **Token-free retrieval.** No LLM and no embeddings in understanding or
   fetching. Structured data + SQL only.
2. **LLM for output only.** Groq phrases the answer, grounded strictly in
   retrieved rows. It never selects or invents stores.
3. **Hard-filter-then-rank.** Stated constraints (area, open-now, price ceiling,
   explicit category) are *hard filters* that bound the eligible set absolutely.
   Score/similarity only *orders* what's already inside that set.
4. **No silent substitution.** If a hard-filtered set is empty, say so honestly;
   never pad results with stores that violate the user's constraint.
5. **Grounding is free.** Candidates are exact DB rows, so phrasing can be
   fluent without hallucinating stores.

---

## Target architecture

```
message ─▶ [1] Understand ─▶ [2] Retrieve ─▶ [3] Assemble context ─▶ [4] Generate
            regex+fuzzy        SQL filters      build rich payload      Groq phrasing
            0 tokens           0 tokens         0 tokens                tokens (only here)
                                                                        rule draft = offline fallback
```

Retrieval is refactored into a single, testable function
`retrieve(message, db, user) -> RetrievalResult` covering stages 1–3. Stage 4
stays in the existing LLM layer. The rule-based draft remains the offline
fallback when no API key is set or the LLM call fails.

---

## Stage specs

### Stage 1 — Understand (token-free)
Turn the raw message into a structured query object:

```
Query {
  intent: str                      # one of the existing 10 intents
  area: str | None                 # canonical area name (resolved)
  category: str | None
  price_max: int | None
  open_now: bool
  min_quality: float | None
  store_names: list[str]           # for review/compare/best-time intents
}
```

Robustness upgrades (all token-free), to fix regex brittleness:
- **Normalize** first: lowercase, strip punctuation, collapse repeated chars.
- **Fuzzy intent match**: tokenize + `difflib`/token-overlap against each
  intent's keyword set, instead of strict regex only (regex stays as the fast
  path; fuzzy is the fallback before `general_assistance`).
- **Keep fuzzy entity extraction** for area/store names; **expand**
  `CATEGORY_SYNONYMS`; optional small hand-built misspelling map for common
  area/thrift terms.
- Accepted limit: heuristic-grade robustness (handles real typos), not
  LLM-grade — the price of zero-token understanding.

### Stage 2 — Retrieve (token-free): hard filters → soft rank
- **Hard filters** (applied as SQL `WHERE`, never relaxed silently):
  `area == Query.area`, `is_open_now` (when `open_now`), `price_min <= price_max`,
  `categories contains Query.category`. Plus the existing visibility rule
  (`STORE_HAS_COORDS`).
- **Soft ranking** (order the eligible set): `experience_score`, category-match
  strength, price closeness, review volume / content similarity. Rank, *then*
  apply a display cap (e.g. 6) — the cap is a display limit on a ranked list,
  **not** the selection rule.
- **Empty eligible set** → return empty + honest message; optionally offer to
  broaden **explicitly** ("want me to check nearby areas?"), never auto-substitute.
- **Remove the leak**: delete the `if not stores: stores = _top_rated(...)`
  city-wide fallbacks in `find_by_area` / `find_by_category` / `find_by_price` /
  `open_now` that currently answer an area query with out-of-area stores.

### Stage 3 — Assemble context (token-free)
Build one compact JSON payload per retrieved candidate with everything the bot
may mention (this is the piece that's too thin today — only 4 fields):

```
StoreContext {
  name, area, price_min, price_max,
  open_time, close_time, is_open_now, closed_days,
  phone, instagram, notes,
  experience_score, review_count, zone_label,
  sentiment_summary: {positive, neutral, negative, total},
  review_snippets: [up to 2 short review texts]
}
```
Pure DB reads. For review/compare intents include the sentiment summary +
snippets; for others they can be omitted to keep the payload lean.

### Stage 4 — Generate (LLM — the only token cost)
- Feed the Stage-3 payload to Groq with the existing "use only these facts,
  never invent stores" instruction; keep the ~8s timeout.
- On no key / any failure → return the rule-based draft (offline fallback).
- Cost stays small: ≤6 stores × ~150 tokens ≈ under 1k tokens per reply.

---

## File-by-file change list (proposed)

| File | Change |
|---|---|
| `app/ml/chatbot.py` | Split into `retrieve()` (stages 1–3) + response assembly. Add normalization + fuzzy intent matching. Enforce hard-filter-then-rank. Remove city-wide fallbacks; add honest empty-set messaging. Build `StoreContext` payloads. |
| `app/ml/llm.py` | `phrase_reply` accepts the richer `StoreContext` list instead of the 4-field slice; prompt unchanged in spirit (grounded, no invention). |
| `app/ml/__init__.py` / small helper | Optional: a `retrieval.py` module if `chatbot.py` gets large, housing `Query`, `RetrievalResult`, `retrieve()`. |
| (data) `CATEGORY_SYNONYMS` | Expand; optional misspelling map. |

No DB schema changes. No new dependencies. No embeddings/vector store.

---

## Execution phases

1. **Refactor retrieval seam** — extract `retrieve()` returning
   `RetrievalResult { query, stores, base_reply, context }`. Behaviour-preserving.
2. **Hard-filter-then-rank + remove leaks** — enforce constraints, delete
   city-wide fallbacks, add honest empty messaging.
3. **Understanding robustness** — normalization + fuzzy intent + synonym/mispell
   expansion.
4. **Rich context payload** — build `StoreContext`, wire into `phrase_reply`.
5. **Verify** (below), then done.

Each phase is independently verifiable; we execute and check one at a time.

---

## Verification plan (extends the existing `_verify.py` harness)

Token-free, SQLite, no model download. Assertions:
- **Area is hard:** query "stores in <area>" → every returned store has
  `area == <area>`; zero out-of-area leakage.
- **Empty honesty:** query a real area with no stores → empty store list +
  message that does **not** present other-area stores as answers.
- **Rank, not cap:** eligible set is ordered by score/relevance; a small
  eligible set returns all of it (not padded).
- **Typo tolerance:** a misspelled area/intent ("koramanagla", "opn now")
  resolves to the right area/intent.
- **Context richness:** payload for a review-insight query includes sentiment
  summary + ≥1 review snippet; hours/price present where set.
- **Zero-token retrieval:** `retrieve()` runs with no network / no API key.
- **LLM optional:** with `GROQ_API_KEY` unset, replies still return (rule draft);
  with it set, phrasing uses only payload facts.

---

## Out of scope (explicitly not doing)

- RAG / embeddings / vector store (wrong tool for small structured data).
- LLM-based query parsing (would spend tokens in retrieval).
- DB schema or dependency changes.
- Per-store indexes.

A **local** embedding fallback for open-ended semantic queries is noted only as a
*future* option, behind the SQL path, if real usage ever demands it.
