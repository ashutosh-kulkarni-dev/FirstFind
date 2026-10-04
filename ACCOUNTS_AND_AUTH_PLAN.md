# Accounts & Auth — Foundation Plan

> Part of the [Accounts & Logged-In Privileges](ACCOUNTS_FEATURES_INDEX.md) work.
> **Build this first** — Files 2–4 depend on the `user` object, the gating
> pattern, and the continuity pattern defined here.

## Scope (from the request)

1. **Fix the login/auth issue.**
2. **Account creation** — email/password *and* Google sign-in.
3. **Gate privileged features** — guests can browse; the four privileges
   (personalization, chat history, saved lists, contributing reviews) are
   login-only.
4. **Continuity** — if a guest starts doing something (chatting, hearting stores,
   drafting a list/review) and then signs up / logs in, that work is preserved.

Privileges themselves are specified in Files 2–4; this file provides the
primitives they plug into.

---

## Part A — Fix the login/auth issue

### What's actually broken

Two distinct defects, both real:

1. **Stale auth UI (documented as P3 in [app/BUGS.md](app/BUGS.md)).** Auth lives
   as module-level mutable variables in
   [app/frontend/src/api.js](app/frontend/src/api.js#L7-L8) (`_token`, `_user`),
   not React state. `Navbar` reads `getUser()` once into local state
   ([Navbar.jsx:17](app/frontend/src/components/Navbar.jsx#L17)). Logging out or
   in updates the module variables but **does not notify React**. `Navbar`
   only re-renders because `App` subscribes to `useLocation`; logging out while
   already on `/` calls `nav('/')` (no route change) so the navbar keeps showing
   the logged-in name until the next navigation/refresh. Same class of bug hits
   login: the greeting/`Log out` button can lag.

2. **Login doesn't persist across a tab close.** The token is stored in
   `sessionStorage` ([api.js:7](app/frontend/src/api.js#L7)). Close the tab and
   the session is gone — which reads to users as "it logged me out / login
   doesn't work." Reviews/saves silently start failing with 401 once the
   in-memory token is lost mid-session too.

### Fix — introduce a real `AuthContext`

Make React the source of truth for auth; keep `api.js` as a thin token holder
that the context drives.

- **New file `app/frontend/src/auth/AuthContext.jsx`:**
  - Holds `{ user, token, loading }` in React state.
  - On mount: read token from `localStorage`, and (recommended) call
    `GET /api/auth/me` to hydrate/validate `user`; if the token is expired/invalid,
    clear it. Falls back to decoding the JWT payload if you want to skip the round
    trip.
  - Exposes `login(token, user)`, `logout()`, and the current `user`.
  - `login`/`logout` update **both** React state and `setAuth()` in `api.js`, so
    every consumer re-renders immediately (kills P3).
- **`api.js` changes:**
  - Switch storage from `sessionStorage` → `localStorage` for `tf_token` /
    `tf_user` so login survives tab close/refresh. (Keep `tf_chat_session` in
    `sessionStorage` — see continuity below.)
  - Add a `401` interceptor in `req()`: on 401, clear auth and emit an event the
    context listens to (so an expired token cleanly logs the user out instead of
    leaving a half-broken UI).
  - Add `me: () => req('/api/auth/me')`.
- **Wire the provider** in [app/frontend/src/main.jsx](app/frontend/src/main.jsx)
  around `<App/>`; replace `getUser()`/`setAuth()` direct calls in `Navbar` and
  `Auth` with `useAuth()`.

### Backend addition for the fix

- **`GET /api/auth/me`** in
  [app/backend/app/routers/auth_routes.py](app/backend/app/routers/auth_routes.py):
  returns the current user (`get_current_user` dependency) as
  `{ id, name, email, created_at }`. Lets the frontend validate a stored token on
  reload and hydrate `user` reliably.

**Acceptance for Part A:** log in → navbar updates instantly without navigating;
log out on `/` → navbar updates instantly; refresh / reopen tab → still logged in;
expired token → clean auto-logout, no 401 spam.

---

## Part B — Account creation

### B1. Email/password (already exists — harden it)

`POST /api/auth/register` and `/login` already work
([auth_routes.py](app/backend/app/routers/auth_routes.py), PBKDF2 in
[auth.py](app/backend/app/auth.py)). Keep them. Minor polish:

- Normalise email to lowercase before store/compare (avoids duplicate accounts by
  case).
- Consider returning `user` object in `TokenOut` (id included) so the frontend
  doesn't need a follow-up `/me` right after register/login.

### B2. Google sign-in

**Recommended approach: Google Identity Services (GIS) ID-token flow.** The
frontend renders Google's button, receives a signed **ID token (JWT)**, and posts
it to the backend, which verifies it and issues *our* app JWT. No server-side
OAuth redirect dance, no session cookies to manage — it fits the existing
"backend mints a JWT" model exactly.

**Data model — make password optional & track provider.** In
[app/backend/app/models.py](app/backend/app/models.py) `User`:

```python
password_hash = Column(String(255), nullable=True)   # null for OAuth-only users
auth_provider = Column(String(20), default="local")  # "local" | "google"
google_sub    = Column(String(64), nullable=True, unique=True, index=True)
avatar_url    = Column(String(300), nullable=True)    # optional, from Google
```

> Note: the app uses SQLAlchemy `create_all` with **no migration tool**
> ([main.py:39](app/backend/app/main.py#L39)). Adding columns to an existing DB
> won't auto-alter. For dev the flow is reseed (`python -m app.seed`). For
> anything with real data, add Alembic (or a one-off `ALTER TABLE` script) — call
> this out in DEPLOYMENT. This caveat applies to **every** model change across
> Files 1–4, so decide the migration story once, here.

**Backend:**
- Add `google-auth` to [requirements.txt](app/backend/requirements.txt) (verifies
  Google ID tokens without extra network calls).
- Config: `GOOGLE_CLIENT_ID` in [config.py](app/backend/app/config.py) (env var).
- New endpoint `POST /api/auth/google` (schema `GoogleAuthIn { credential: str }`):
  1. `google.oauth2.id_token.verify_oauth2_token(credential, ..., GOOGLE_CLIENT_ID)`.
  2. Extract `sub`, `email`, `name`, `picture`, `email_verified`.
  3. Find user by `google_sub`, else by `email` (link existing local account to
     Google — set `google_sub`), else create a new `auth_provider="google"` user
     with `password_hash=None`.
  4. Return the same `TokenOut` (our JWT) as login. From here everything downstream
     is provider-agnostic.
- `verify_password` already safely returns `False` for a null/again-malformed hash,
  but guard the `/login` path so an OAuth-only account can't be brute-forced via the
  password endpoint (it simply won't match — acceptable, but add a clear
  "use Google to sign in" message when `auth_provider != "local"`).

**Frontend:**
- Add `VITE_GOOGLE_CLIENT_ID` to [frontend/.env.example](app/frontend/.env.example).
- Load GIS (`https://accounts.google.com/gsi/client`) and render the Google button
  on [Auth.jsx](app/frontend/src/pages/Auth.jsx) (both login and register modes —
  "Continue with Google" does both).
- On credential callback → `api.google(credential)` → `auth.login(res.token, res)`.

**Open decision:** whether to also support the traditional server-redirect OAuth
(needed only if you later want offline access / Google API scopes). For "just sign
in", the ID-token flow above is simpler and recommended — flagged in Open Questions.

---

## Part C — Gating privileged features

Guests keep full browse access (stores, explore, zones map, chatting). The four
privileges are login-only. Two enforcement layers:

### C1. Backend (authoritative)

- Privileged **write/read-your-data** endpoints depend on `get_current_user`
  (already the case for reviews/save in
  [stores.py](app/backend/app/routers/stores.py#L176) — returns 401 for guests).
- Endpoints that *enhance* for logged-in users but still work for guests keep
  `get_optional_user` (e.g. `/api/recommendations`, `/api/chat` today).
- Every new privileged endpoint in Files 2–4 uses `get_current_user`.

### C2. Frontend (UX)

- **`useAuth()`** exposes `user`; components branch on it.
- **`requireAuth(action, { reason })`** helper: if `user` exists, run `action()`;
  else stash a **pending action** (see Part D) and redirect to `/auth?next=...`
  with a reason string shown on the auth page ("Log in to save this list").
- **`<RequireAuth>`** route/section wrapper for whole privileged views (e.g. a
  "My Lists" page) that renders a friendly "log in to use this" panel for guests
  instead of the feature.
- Privileged buttons (Save-list, Post-review) are always **visible** (so guests
  discover the value) but funnel through `requireAuth`.

---

## Part D — Continuity ("keep what I was doing")

Requirement: a guest mid-task who then creates an account / logs in should not lose
their work. Two complementary mechanisms.

### D1. Pending-action resume (in-flight task)

- A tiny module `app/frontend/src/auth/pendingAction.js` stores **one** intended
  action in `sessionStorage` as a serialisable descriptor, e.g.
  `{ type: 'post_review', storeId, rating, text }` or
  `{ type: 'save_list', zoneId, name, storeIds }`.
- `requireAuth` writes it before redirecting to `/auth`.
- After a successful login/register/Google, `AuthContext` checks for a pending
  action and dispatches it (via a small registry mapping `type → handler`), then
  navigates back to `next`.
- Result: guest clicks "Post review" → prompted to log in → after login the review
  is submitted automatically and they land back on the store page.

### D2. Guest-state migration (accumulated work)

On the **first successful authentication in a browser that has guest state**, run
a one-shot migration, then clear the local guest copies:

| Guest state (local) | Migrated to | Mechanism |
|---|---|---|
| Hearted stores — `ff_saved` in localStorage ([lib/saved.js](app/frontend/src/lib/saved.js)) | `Interaction(kind="save")` per store | `POST /api/stores/{id}/save` for each id (endpoint exists) |
| Draft saved-list (guest-built, see File 3) | `SavedList` + items | `POST /api/lists` (File 3) |
| Guest chat transcript (see File 2) | `Conversation` + messages under the user | `POST /api/chat/claim { session_id }` (File 2) |
| Pending review draft | `Review` | handled by D1 pending-action |

- The chat migration is the interesting one: the guest already has a
  `tf_chat_session` UUID in `sessionStorage`
  ([api.js:12](app/frontend/src/api.js#L12)). On login, send that `session_id` to a
  **claim** endpoint that attaches the current transcript to the user's history
  (detailed in File 2). Keep `tf_chat_session` in `sessionStorage` (not
  localStorage) so it stays tab-scoped and doesn't bleed between users on a shared
  browser.
- Make migration **idempotent** (saving an already-saved store is a no-op;
  claiming an already-claimed session is a no-op) so a double-fire can't duplicate.
- Guard against **account switching on a shared device**: only migrate guest state
  that was created while logged-out; on `logout()` clear in-memory user data (but
  leave the server data intact).

---

## Data-model summary (this file)

`User` gains: `password_hash` nullable, `auth_provider`, `google_sub`,
`avatar_url`. (Other tables are added in Files 2–4.)

## New/changed endpoints (this file)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/auth/me` | required | Validate token / hydrate `user` |
| POST | `/api/auth/google` | none | Google ID-token → app JWT |
| POST | `/api/auth/register` | none | (existing) + email normalise, return user |
| POST | `/api/auth/login` | none | (existing) + provider-aware error msg |

## Frontend changes (this file)

- New: `auth/AuthContext.jsx`, `auth/pendingAction.js`, `<RequireAuth>`.
- Changed: `api.js` (localStorage + 401 handling + `me`/`google`), `main.jsx`
  (provider), `Navbar.jsx` (use context), `Auth.jsx` (Google button + `next`
  + pending-action resume).

## Testing / acceptance

- Unit: `verify_oauth2_token` mocked → creates/links user correctly for new email,
  existing-local email, and returning Google user.
- Unit: login against an OAuth-only account returns the "use Google" message, not a
  500.
- E2E: (a) refresh keeps session; (b) logout on `/` updates navbar instantly;
  (c) guest hearts 2 stores + starts a review → registers → both are on the server
  and the review posts; (d) expired token auto-logs-out cleanly.

## Open questions

1. **Google flow:** ID-token (recommended, simplest) vs full server-redirect OAuth
   (only if future Google API scopes/offline access are needed)?
2. **Token persistence:** `localStorage` (recommended for "stay logged in") vs
   keeping `sessionStorage` (more conservative; requires re-login each tab). Note
   the XSS trade-off of localStorage tokens — acceptable for this app, but worth an
   explicit call.
3. **Migrations:** adopt Alembic now, or stay on reseed-in-dev + manual SQL for
   prod? Every feature file adds columns/tables, so decide here.
4. **Shared-device policy:** how aggressively to migrate guest state on login
   (auto vs "we found unsaved work — add it to your account?" prompt).
