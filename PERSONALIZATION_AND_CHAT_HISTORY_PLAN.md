# Personalization & Chat History — Privileges 1 & 2

> Part of the [Accounts & Logged-In Privileges](ACCOUNTS_FEATURES_INDEX.md) work.
> **Depends on** [ACCOUNTS_AND_AUTH_PLAN.md](ACCOUNTS_AND_AUTH_PLAN.md) (the `user`
> object, gating, and the continuity/migration primitives).

These two privileges are grouped because they are the *same shape of problem*:
take something the app currently computes for a session/guest and start persisting
it **per user** in the DB, then expose a "your history" read path — and both must
survive the guest→login migration.

---

## Privilege 1 — Activate personalization

### Current state (mostly already built)

Personalization already works server-side for logged-in users and is already
guest-safe:

- `/api/recommendations` uses `get_optional_user`; logged-in →
  `user_recs(db, user.id)` with `personalized: true`, guest → top-rated fallback
  ([misc.py:33-50](app/backend/app/routers/misc.py#L33-L50)).
- Interactions (`view`/`save`) are logged for logged-in users and the recommender
  **refits on interaction** ([stores.py:136-147](app/backend/app/routers/stores.py#L136-L147),
  save at [stores.py:193-204](app/backend/app/routers/stores.py#L193-L204)).
  (BUGS.md C2 — "never refits" — is marked **resolved** in the current tree; verify
  this still holds when testing.)
- The chatbot also personalizes `store_recommendation`
  ([engine.py:173-183](app/backend/app/chat/engine.py#L173-L183)).

So "activate on login" is largely a **gating + surfacing** task, not new ML.

### What to actually do

1. **Verify the refit path works end-to-end** for a freshly-registered user
   (register → view/save 3 stores → `/api/recommendations` returns
   `personalized: true`). BUGS.md flagged this as historically broken; confirm the
   fix holds before building UI on top of it.
2. **Surface personalization in the UI, gated by `user`:**
   - On Explore/Landing, a "**Picked for you**" rail that calls
     `/api/recommendations` and, when `personalized`, labels it as tailored; for
     guests show the same rail titled "Top rated" with a subtle "Log in for picks
     tailored to you" nudge (funnels through `requireAuth`).
   - Show the `personalized` boolean the API already returns to drive the heading.
3. **Continuity tie-in (from File 1, Part D):** when a guest's hearted stores
   (`ff_saved`) migrate to `Interaction(kind="save")` on login, the recommender
   refit that already fires on save
   ([stores.py:203](app/backend/app/routers/stores.py#L203)) means their first
   logged-in recommendations immediately reflect what they hearted as a guest.
   Trigger one `refit_recommender(force=True)` after the batch migration.
4. **Move "saved hearts" to server truth (optional but recommended).** Today
   [lib/saved.js](app/frontend/src/lib/saved.js) is localStorage-only and the
   backend has `POST /save` but **no list endpoint**. Add
   `GET /api/me/saved` (returns the user's `save` interactions as stores) so the
   navbar `♥ SAVED (n)` and a "Saved" view reflect real per-user data once logged
   in. Guests keep the localStorage mirror; on login it migrates and the server
   becomes source of truth. (This also feeds naturally into File 3's saved-lists.)

### No schema change required for core personalization

`Interaction`, `UserRecommendation`, `StoreSimilarity` already exist
([models.py](app/backend/app/models.py)). Only the optional `GET /api/me/saved`
read endpoint is new.

---

## Privilege 2 — Store & view past conversations

### Current state

Chat state is **in-memory only** and **not per-user**: keyed by an opaque
`session_id` UUID in a process-local dict with 1-hour TTL
([chat/state.py](app/backend/app/chat/state.py)), and only the `Trip`/`prefs` are
kept — **not the message transcript** ([contracts.py:58-63](app/backend/app/chat/contracts.py#L58-L63)).
Nothing is persisted; refresh or an hour idle loses everything. This is the real
net-new work in this file.

### New data model

Add to [models.py](app/backend/app/models.py):

```python
class Conversation(Base):
    __tablename__ = "conversations"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)  # links the guest UUID at claim time
    title      = Column(String(160), default="")   # derived from first user message
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)
    messages   = relationship("ChatMessage", back_populates="conversation",
                              order_by="ChatMessage.created_at",
                              cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id              = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role            = Column(String(12), nullable=False)   # "user" | "assistant"
    text            = Column(Text, nullable=False)
    # Optional: store the assistant payload (stores/map/suggestions/intent) so a
    # reopened conversation can re-render cards, not just text.
    meta            = Column(Text, nullable=True)          # JSON blob
    created_at      = Column(DateTime, default=dt.datetime.utcnow)
    conversation    = relationship("Conversation", back_populates="messages")
```

Add `conversations = relationship("Conversation", ...)` to `User`.

### Persistence hook (minimal, non-invasive)

The single composition point is `engine.respond(msg, db, user, session_id)`
([engine.py:40](app/backend/app/chat/engine.py#L40)). Persist there so *all* reply
paths (greeting short-circuit, advice, refinement, normal) are covered without
touching handlers:

- At the **start** of `respond`, if `user` is present: resolve-or-create the
  `Conversation` for `(user_id, session_id)`; append the user message.
- At each **return**, append the assistant message (wrap the existing `return
  _serialize(...)` sites, or refactor to a single exit that persists then returns).
  Storing `meta` = the serialized extras (stores/suggestions/map/intent) lets the
  history view re-render rich cards.
- **Guests (`user is None`) are not persisted** — matches the gating rule. Their
  in-memory session still works for the current visit; it becomes durable only if
  they log in and claim it.
- Keep the existing in-memory `state.py` store for `Trip`/`prefs` (fast per-turn
  working memory); the DB is the durable transcript. They're complementary.

### Endpoints (all `get_current_user`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/conversations` | List the user's conversations (id, title, updated_at, message count) for a "History" panel |
| GET | `/api/conversations/{id}` | Full transcript (messages + meta) to re-open a past chat |
| DELETE | `/api/conversations/{id}` | Let users delete a conversation (ownership-checked) |
| POST | `/api/chat/claim` | Body `{ session_id }` — attach the guest transcript to the user (continuity, File 1 D2) |

`claim` handling: the guest visit wasn't persisted (guests aren't stored), so
"claim" means **the current live in-memory session's turns are flushed to a new
`Conversation` under the user**, keyed by that `session_id`. Simplest robust
option: on login, the frontend replays nothing — instead, from the moment the user
is authenticated, `respond` persists as normal; to preserve *pre-login* turns,
have the frontend hold the guest transcript in memory (it already renders it in
`ChatCore`) and POST it to `claim` as the seed messages. Idempotent on
`session_id` so a repeat is a no-op.

### Frontend

- `api.js`: `conversations()`, `conversation(id)`, `deleteConversation(id)`,
  `claimChat(session_id)`.
- **History UI:** a drawer/panel in the chat view (Chat page + `ChatWidget`) listing
  past conversations for logged-in users; clicking one loads
  `/api/conversations/{id}` and rehydrates the message list (and cards, from
  `meta`). Guests see a "Log in to save and revisit your chats" nudge instead.
- **Continuity:** on login, if there's a non-empty guest transcript in the current
  tab, call `claimChat(tf_chat_session)` with the buffered turns; then refresh the
  history list.
- Consider a "New chat" button that rotates `tf_chat_session` so a user can keep
  multiple distinct conversations.

### Testing / acceptance

- Logged-in user chats → refresh → conversation reappears in history and reopens
  with cards intact.
- Guest chats, then registers → the pre-login turns show up as a claimed
  conversation exactly once (idempotency check: call `claim` twice → still one).
- Guest chat is **not** written to `conversations`/`chat_messages` until claim.
- Deleting a conversation you don't own → 403/404.

### Notes / risks

- `meta` JSON can get large (store cards, map specs). Cap what you persist (e.g.
  store ids + intent, re-fetch cards on reopen) if size becomes a concern.
- Multi-worker deploys: the in-memory `state.py` is process-local (already noted in
  the file). The DB transcript is the shared truth, so history is correct across
  workers even though live per-turn working memory isn't shared — acceptable, and
  the existing code already flags the Redis swap path if you need it.
