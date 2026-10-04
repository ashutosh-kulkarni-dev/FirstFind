# Accounts & Logged-In Privileges — Plan Index

This is the umbrella for a set of related features: fixing the login bug, adding
account creation (email + Google), and unlocking four privileges for logged-in
users while keeping guests able to browse. It is split into four plan files,
grouped by how similar the underlying work is.

| # | Plan file | Covers | Requirement(s) |
|---|-----------|--------|----------------|
| 1 | [ACCOUNTS_AND_AUTH_PLAN.md](ACCOUNTS_AND_AUTH_PLAN.md) | **Foundation** — fix the login/auth bug, email + Google account creation, a real frontend auth context, the gating pattern for privileged features, and guest→login continuity ("keep what you were doing"). | "Fix login", "make an account (normal / Google)", "features not available until logged in", "task before login is still there after login" |
| 2 | [PERSONALIZATION_AND_CHAT_HISTORY_PLAN.md](PERSONALIZATION_AND_CHAT_HISTORY_PLAN.md) | Activating personalization as a login privilege, and persisting/viewing past chatbot conversations. Grouped because both are *per-user server-side history* layered on features that already exist. | Privilege 1 (personalization), Privilege 2 (stored conversations) |
| 3 | [SAVED_LISTS_PLAN.md](SAVED_LISTS_PLAN.md) | Saving named lists of shops from a zone/cluster, and viewing saved lists. New CRUD domain. | Privilege 3 (named saved lists in the zonal feature) |
| 4 | [REVIEWS_AND_RATINGS_PLAN.md](REVIEWS_AND_RATINGS_PLAN.md) | Logged-in users commenting + rating stores, with "rating mandatory when a comment is given; rating-only is fine". | Privilege 4 (contribute reviews/ratings) |

## Why this split

- **File 1 is the backbone.** Everything else depends on a trustworthy
  "is this a logged-in user, and who are they?" answer and on the gating +
  continuity primitives it defines. Build it first.
- **File 2 groups personalization + chat history** because both are the same
  shape of problem: take something the app already computes per session/guest
  and start persisting it per *user* in the DB, then expose a "your history"
  read path. Same models pattern, same migration-on-login concern.
- **Files 3 and 4 are distinct product domains** (list management; user-generated
  content moderation/validation) that each deserve their own model tables and
  endpoints, so they get their own files.

## Recommended build order

1. **File 1 — Auth foundation** (unblocks all gating + the `user` object).
2. **File 4 — Reviews/ratings** (smallest; backend endpoint already exists, mostly
   validation + UI gating — good first privilege to ship and prove the gating
   pattern end-to-end).
3. **File 3 — Saved lists** (self-contained new CRUD).
4. **File 2 — Personalization + chat history** (personalization is mostly gating
   an existing feature; chat history is the largest net-new persistence layer).

## Cross-cutting decisions (settled once, referenced everywhere)

These are defined in detail in File 1 and reused by 2–4:

- **Auth source of truth:** JWT in an `AuthContext` (React), token in
  `localStorage` (persists across tabs/refresh), `user` object hydrated from the
  token / `/api/auth/me`.
- **Gating pattern:** a `requireAuth(action)` helper + `<RequireAuth>` wrapper.
  Guests see the feature but are prompted to log in at the moment of the
  privileged action; the intended action resumes after login.
- **Continuity pattern:** localStorage/guest state (saved hearts, draft list,
  pending review, guest chat transcript) is migrated to the server on first
  successful login via a one-shot `claim`/`migrate` step, plus a "pending action"
  queue so an in-progress task completes right after auth.
