# Auth & Logged-In Features — Phased Implementation (Render + Vercel)

> Concrete build order for: **normal auth fix**, **Google auth (prod)**,
> **personalization (industry-standard redesign)**, **chat history save**, and
> **list save**. Deployment target: **Vercel** (frontend) + **Render** (FastAPI,
> Docker) + **Supabase Postgres**. See design detail in
> [ACCOUNTS_FEATURES_INDEX.md](ACCOUNTS_FEATURES_INDEX.md) and its sub-plans.

## Deployment ground rules (apply to every phase)

- **New columns on existing tables** (only `User` gains columns) are added via an
  idempotent `ensure_schema()` at startup using Postgres `ALTER TABLE ... ADD
  COLUMN IF NOT EXISTS` (MySQL dev: guarded try/except). **New tables** come from
  the existing `Base.metadata.create_all`. Net effect: **no destructive reseed
  needed** to ship any phase. Alembic remains the post-launch upgrade path.
- **Backend env (Render):** add `GOOGLE_CLIENT_ID` (Phase 2). Existing:
  `ENVIRONMENT=production`, `FIRSTFIND_JWT_SECRET`, `DATABASE_URL`, `CORS_ORIGINS`,
  `HUGGINGFACE_TOKEN`, `GROQ_API_KEY`.
- **Frontend env (Vercel):** add `VITE_GOOGLE_CLIENT_ID` (Phase 2). Existing:
  `VITE_API_BASE`.
- **CORS** already env-driven; the Vercel origin must be in `CORS_ORIGINS`.
- Token persistence moves to `localStorage` so login survives tab close (Render
  cold-starts / redeploys don't affect JWTs — they're stateless).

---

## Phase 1 — Normal auth fix + foundation  *(build first)*

Fixes the real login bug (stale auth UI + non-persistent token) and lays the
gating/continuity primitives every later phase reuses. Google-ready but not yet
wired.

**Backend**
- `User` model: `password_hash` → nullable; add `auth_provider` (`"local"`
  default), `google_sub` (unique, nullable), `avatar_url` (nullable).
- `ensure_schema()` in `database.py`, called from the `main.py` lifespan, adds
  those columns idempotently.
- `GET /api/auth/me` (requires auth) → `{ id, name, email, avatar_url, created_at }`.
- `register`/`login`: lowercase-normalise email; `TokenOut` includes `id` and
  `avatar_url`; login against a Google-only account returns a clear "use Google"
  message.

**Frontend**
- `auth/AuthContext.jsx` — React source of truth (`user`, `token`, `loading`);
  `login()`, `logout()`; hydrates via `/api/auth/me` on load; drives `api.js`.
- `api.js` — `localStorage` for token; 401 interceptor → auto-logout event;
  add `me()`.
- `auth/pendingAction.js` + `<RequireAuth>` + `requireAuth()` gating helper.
- `main.jsx` wraps `<App/>` in `<AuthProvider>`; `Navbar`, `Auth`, `StoreDetail`
  switch from `getUser()` to `useAuth()` (kills the stale-state bug).

**Acceptance:** login/logout updates navbar instantly; refresh keeps session;
expired token auto-logs-out cleanly. **Recommended changes folded in:** email
normalise, localStorage persistence, provider columns pre-added.

---

## Phase 2 — Google auth  *(for prod launch)*

**Backend** *(no new dependency)*
- `GOOGLE_CLIENT_ID` in `config.py`. Verify the Google ID token by calling
  Google's `https://oauth2.googleapis.com/tokeninfo?id_token=...` over TLS with the
  **already-present `httpx`** — no `google-auth` dependency. Validate
  `aud == GOOGLE_CLIENT_ID`, `iss ∈ {accounts.google.com, https://accounts.google.com}`,
  and `email_verified`. (Trade-off: one network round-trip per Google login — fine
  at this scale; can swap to local signature verification later without touching
  callers.)
- Keep it in a **separable** `auth_google.py` helper (`verify_google_token(credential)
  -> GoogleIdentity | None`); the route just consumes it.
- `POST /api/auth/google { credential }` — verify, then find-by-`google_sub` →
  else link-by-email → else create (`auth_provider="google"`, `password_hash=NULL`);
  return the same app `TokenOut`. Provider-agnostic downstream.
- **Feature-flag off cleanly:** empty `GOOGLE_CLIENT_ID` → the endpoint returns 503
  "Google sign-in not configured" and the frontend hides the button. No hard
  coupling; the feature is fully removable.
- Note: on an already-deployed DB, also drop the `NOT NULL` on `users.password_hash`
  (add to `ensure_schema`) so Google-only accounts can be created.

**Frontend**
- Load Google Identity Services; "Continue with Google" button on `Auth.jsx` (login
  + register). Callback → `api.google(credential)` → `auth.login(...)` →
  resume pending action / `next`.
- `VITE_GOOGLE_CLIENT_ID` in `.env.example`.

**Setup (one-time):** Google Cloud → OAuth Web client; Authorized JS origins =
Vercel domain + `http://localhost:5173`. Put client id in both env stores.

**Acceptance:** new Google user is created; a Google login matching an existing
local email links (no duplicate); both paths land logged-in with a working JWT.

---

## Phase 3 — Personalization (verify + surface; NO redesign)

**Verified against the code: the recommender is already industry-standard.**
[recommender.py](app/backend/app/ml/recommender.py) is a **hybrid** — item-item
cosine CF **blended with a content model** built from store attributes
(`sim = α·CF + (1-α)·content`, `ALPHA=0.6`). It handles cold-start via the content
term, refits on interaction, and serves from the `UserRecommendation` /
`StoreSimilarity` tables (stateless → correct on Render's single instance). The old
BUGS.md "pure CF, never refits, cold-starts dead" concern is **already resolved**.
So this phase is **not a rewrite** — no new deps, no model swap.

**What Phase 3 actually is:**
1. **Verify end-to-end** for a *fresh* account: register → save/view 2–3 stores →
   `refit` fires → `/api/recommendations` returns `personalized:true` with
   non-empty picks. (`recommend_for_user` returns `[]` only if the user has no
   weighted interactions yet; confirm the save path lands the user in the matrix.)
2. **Surface it in the UI, gated:** a "Picked for you" rail for logged-in users
   (`personalized:true`), "Top rated" for guests, driven by the boolean the API
   already returns. Pure presentation — no backend change.
3. **Continuity tie-in:** confirm the guest→login save-migration triggers one
   `refit_recommender(force=True)` so first logged-in picks reflect guest hearts.
4. *(Optional, only if picks look weak in testing)* tune `ALPHA` or the interaction
   `WEIGHTS` — a one-line change, not a redesign.

**Future headroom (not for launch):** implicit-feedback matrix factorisation (ALS)
when interaction volume grows. Noted only; do not build now.

**Acceptance:** brand-new user who saves 2–3 stores immediately gets sensible,
non-empty personalized picks; guest sees top-rated with a login nudge.

---

## Phase 4 — Chat history save

**Backend** *(engine stays untouched — persistence is a separable add-on)*
- New tables `Conversation`, `ChatMessage` (per-user transcript + optional `meta`
  JSON for cards).
- New module `chat/history.py` with a single `record_turn(db, user, session_id,
  user_msg, result)` and the claim logic. **`chat/engine.py::respond` is NOT
  edited** — the `/api/chat` route (`misc.py`) calls `record_turn` *after* it has
  the result dict, only when `user` is present (guests stay ephemeral). This keeps
  the chat engine pure and makes history a delete-one-module feature.
- `GET /api/conversations`, `GET /api/conversations/{id}`,
  `DELETE /api/conversations/{id}`, `POST /api/chat/claim { session_id, messages }`
  (continuity: attach pre-login guest turns once, idempotent) — in a new
  `routers/conversations.py`.

**Frontend**
- History drawer in the chat view (logged-in only); reopen loads a transcript and
  rehydrates cards from `meta`. On login, claim the current guest transcript.

**Render note:** in-memory `state.py` (Trip/prefs working memory) stays; the DB is
the durable transcript, so history is correct despite single-instance/cold-starts.

**Acceptance:** logged-in chat survives refresh & reappears in history; guest chat
becomes a claimed conversation exactly once after login; guest chat is never
written pre-claim.

---

## Phase 5 — List save (zonal)

**Backend**
- New tables `SavedList`, `SavedListItem` (named snapshot of a cluster's store ids +
  center/radius so it re-renders on the map). Unique `(user_id, name)`.
- `POST /api/lists`, `GET /api/lists`, `GET /api/lists/{id}`,
  `PATCH /api/lists/{id}`, `DELETE /api/lists/{id}` — all `get_current_user`,
  ownership-checked. New router registered in `main.py`.

**Frontend**
- "Save this list" on the cluster result (name prompt, default = cluster label);
  guest → `requireAuth` pending action → auto-saves post-login.
- `/lists` route under `<RequireAuth>`: view, open-on-map, rename, remove store,
  delete. Navbar entry point when logged-in.

**Acceptance:** save a cluster as a named list → appears in `/lists` with correct
stores/order; reopen reflects current store data; ownership enforced; guest build →
login → auto-saved.

---

## Clean-architecture & separability principles (apply throughout)

To avoid spaghetti and keep every feature independently removable:

- **No new backend dependencies.** Google auth uses existing `httpx`;
  personalization uses the existing `numpy`/sklearn stack; migrations use a tiny
  in-repo `ensure_schema()` (no Alembic yet). Nothing added to `requirements.txt`.
- **One feature = one module + one router**, each behind its own URL prefix:
  `auth_google.py`, `chat/history.py` + `routers/conversations.py`,
  `routers/lists.py`. Each is registered with one `include_router` line and could be
  deleted without touching the rest.
- **Don't edit the chat engine.** History is layered at the route boundary, so the
  four-pillar engine stays pure (matches its existing "single composition point"
  design).
- **Reuse existing patterns, don't invent new ones:** JWT+`TokenOut` for all auth
  providers; `get_current_user`/`get_optional_user` for gating; `store_to_dict` for
  serialization; the DB-backed stateless serving the recommender already uses;
  the `CHAT_*` env-flag style for optional features (`GOOGLE_CLIENT_ID` empty →
  feature self-disables).
- **Frontend auth is three small, decoupled files:** `auth/AuthContext.jsx` (state),
  `auth/pendingAction.js` (continuity queue), `auth/RequireAuth.jsx` (gating
  wrapper). Components consume `useAuth()`; `api.js` stays a thin transport with no
  React knowledge.
- **Idempotency everywhere continuity touches data** (save, claim, list-migrate) so
  a double-fire never duplicates.

## Sequencing & why

1. **Phase 1** unblocks everything (real `user`, gating, continuity).
2. **Phase 2** is needed for the prod launch and is small once Phase 1 exists.
3. **Phase 3** is mostly a `recommender.py` refactor + UI surfacing (no new
   user-facing CRUD) — low UI risk, high product value.
4. **Phases 4 & 5** are the two net-new persistence domains; independent of each
   other, so either order works.

Reviews/ratings (Privilege 4, [REVIEWS_AND_RATINGS_PLAN.md](REVIEWS_AND_RATINGS_PLAN.md))
is deferred per current scope but is a ~1-file frontend fix whenever you want it.
