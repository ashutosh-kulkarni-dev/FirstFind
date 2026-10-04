# Reviews & Ratings (Contribute) — Privilege 4

> Part of the [Accounts & Logged-In Privileges](ACCOUNTS_FEATURES_INDEX.md) work.
> **Depends on** [ACCOUNTS_AND_AUTH_PLAN.md](ACCOUNTS_AND_AUTH_PLAN.md).
> Smallest of the four — most of the backend already exists. Good candidate to ship
> first after the auth foundation, to prove the gating + continuity patterns.

## Requirement

Logged-in users can **contribute** by commenting on stores and rating them, with
this validation rule:

- If they give a **comment**, a **rating is mandatory**.
- If they give a **rating only** (no comment), that's **fine**.
- (Implied: a comment with no rating is **not** allowed; an empty submission is not
  allowed.)

Guests cannot contribute (already the case) but should be smoothly funnelled
through login and have their in-progress review preserved (continuity, File 1).

## Current state vs. the rule

- **Backend already matches the desired rule.** `ReviewIn` requires
  `rating` (`ge=1, le=5`) and defaults `text=""`
  ([schemas.py:31-33](app/backend/app/schemas.py#L31-L33)); `POST
  /api/stores/{id}/reviews` requires auth via `get_current_user`
  ([stores.py:173-190](app/backend/app/routers/stores.py#L173-L190)). So
  rating-mandatory + comment-optional is already enforced server-side. **No backend
  change is strictly required** for the core rule.
- **Frontend contradicts the rule.** The composer in
  [StoreDetail.jsx](app/frontend/src/pages/StoreDetail.jsx#L42-L52) blocks submit
  unless **both** a comment *and* a rating are present
  (`if (!draft.trim() || !rating) return`, and the button `disabled={... ||
  !draft.trim() || !rating}`). This wrongly **forces a comment** and must change to:
  **rating always required, comment optional.**

So this privilege is mostly a **frontend fix + gating polish**, with small optional
backend hardening.

## Frontend changes

In [StoreDetail.jsx](app/frontend/src/pages/StoreDetail.jsx):

1. **Fix the validation** to the real rule:
   - Submit allowed iff `rating >= 1` (comment optional).
   - `submitReview`: `if (!rating) return` (drop the `!draft.trim()` requirement).
   - Button `disabled={submitting || !rating}`.
   - Because the rule "comment ⇒ rating" is automatically satisfied when rating is
     always required, no extra branch is needed — but show a clear helper:
     when `draft.trim()` and `!rating`, render an inline hint
     "Please add a star rating to post your comment."
2. **Use the auth context, not `getUser()`** (File 1): the composer currently
   branches on `getUser()` at render time — a value that can be stale (the P3 bug).
   Switch to `useAuth()` so the composer flips to the logged-in form the instant the
   user logs in without a reload.
3. **Gating via `requireAuth` + continuity (File 1 D1):** for guests, instead of
   only the static "Log in to post a review" text, let them **compose** (pick stars,
   type) and on "Post review" call `requireAuth` with a pending action
   `{ type: 'post_review', storeId, rating, text }`. After login they're returned to
   the store page and the review is submitted automatically. This directly satisfies
   "the task they were doing before logging in is still there."
4. **Empty-comment UX:** when posting a rating with no text, keep the button label
   "Post rating" (vs "Post review" when text is present) so the rating-only path
   feels intentional, not broken.

## Backend (optional hardening)

The rule already holds, but consider:

- **One review per user per store** (dedupe): today a user can post unlimited
  reviews for one store, inflating the sentiment set. Add a uniqueness rule —
  either `unique(user_id, store_id)` on `Review` with an "update your review"
  path, or reject a second review with 409. *Recommended*, since ratings feed
  `experience_score`. (Decide in Open Questions — it changes the model.)
- **Trim/normalise text**; treat whitespace-only `text` as empty so it stores `""`
  (keeps the "rating only" path clean and avoids a blank "comment").
- Existing behaviour to keep: sentiment scoring runs off the request path via a
  background task ([stores.py:189](app/backend/app/routers/stores.py#L189)); a
  rating-only review has empty text → sentiment will be neutral/None, which is
  correct (nothing to analyse). Verify `score_review` handles empty text without
  error.

## Data-model note

No change required for the core rule. If adopting "one review per user per store,"
add `UniqueConstraint("user_id", "store_id")` to `Review`
([models.py:53-65](app/backend/app/models.py#L53-L65)) — subject to the migration
caveat in File 1.

## Testing / acceptance

- Rating only, no comment → posts successfully; appears with stars and no body.
- Comment + rating → posts; sentiment badge appears after the background score.
- Comment typed, no rating → submit blocked with the "add a rating" hint.
- Empty (no rating, no comment) → submit disabled.
- Guest composes a review → clicks Post → prompted to log in → after login the
  review posts to the correct store and they land back on it (pending-action).
- (If dedupe adopted) second review by same user on same store → 409 or updates the
  existing one, per chosen policy.
- Backend unit: `ReviewIn` rejects `rating=0`/missing (422) and accepts empty
  `text`.

## Open questions

1. **One review per user per store?** (Recommended yes, with edit.) Affects the
   model and the "already reviewed" UI state.
2. **Editing / deleting** your own review — in scope now, or later? (Pairs with the
   dedupe decision.)
3. Should a **rating-only** contribution still count toward the visible "N reviews"
   count, or be surfaced separately as "N ratings · M written reviews"? Affects the
   `sentiment_summary` display copy, not the data.
