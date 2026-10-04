# Chatbot Implementation Plan

> Turns the four pillars from `chatbot-capabilities-brainstorm.md` into an **airtight, low-coupling** build. The governing rule: **every pillar is an independent module with one clear job, talking only through typed contracts, composed in exactly one place.** No pillar imports another. Each ships on its own behind a graceful default.

---

## 1. Design rules (the anti-spaghetti contract)

These are non-negotiable; they're what keep future development clean.

1. **One composition point.** Only `chat/engine.py::respond()` wires pillars together. Nothing else orchestrates. If two modules need to talk, they don't — they both return data to the engine, and the engine passes it on.
2. **Contracts, not imports.** Modules exchange plain typed structures from `chat/contracts.py` (dataclasses). A pillar never imports another pillar's internals. `contracts.py` is a leaf — it imports nothing from `chat/`.
3. **Pure where possible.** `trip.py`, `mapspec.py`, `advice.py` are pure functions (input → output, no DB, no globals, no I/O). Trivially unit-testable, impossible to entangle.
4. **Side effects at the edges.** DB access lives in `retrieval.py` + `geo.py` only. Mutable state lives in `state.py` only. The pure core never touches either.
5. **Additive, never breaking.** Every new response field (`map`, `action`, `trip`) is optional. Old clients ignore them; the engine omits them when a pillar is off. No existing field changes shape.
6. **Graceful default per pillar.** Each pillar has an off-switch that degrades to today's behaviour — not an error. Groq-off already works this way; every pillar copies that discipline.
7. **The LLM stays a phraser.** `llm.py` is untouched in scope and role. No pillar gives the LLM new powers or new failure modes.

---

## 2. Target module map (dependency DAG — acyclic by construction)

A new `app/chat/` package holds all conversation logic. The existing geo/ML engines are reused, never duplicated.

```
                         ┌─────────────────────┐
                         │  chat/contracts.py  │   leaf: pure types, imports nothing from chat/
                         └──────────┬──────────┘
        ┌───────────────┬──────────┼───────────┬───────────────┬──────────────┐
        ▼               ▼          ▼           ▼               ▼              ▼
 chat/retrieval.py  chat/geo.py  chat/state.py  chat/trip.py  chat/advice.py  chat/mapspec.py
   (understand +     (adapter over  (session      (pure)        (pure +         (pure)
    rank + context)   clusters/metro) store)                     data file)
        │               │            │           │               │              │
        └───────────────┴────────────┴─────┬─────┴───────────────┴──────────────┘
                                            ▼
                                   chat/engine.py   ← THE ONLY composition point
                                            │
                                            ▼
                                routers/misc.py  (one-line import swap)
```

**Reused as-is (not modified):** `ml/clusters.py`, `ml/zones.py`, `routers/metro.py` logic, `utils.py`, `ml/recommender.py`, `ml/llm.py`.

**No arrows point sideways or up.** Every `chat/*` module depends only on `contracts.py` (+ an existing engine for the two that do I/O). The engine is the only node with many inbound edges. This shape *cannot* become spaghetti because the import graph forbids it.

---

## 3. Contracts (`chat/contracts.py`) — the shared vocabulary

Plain dataclasses. This is the only thing modules share. Written once, changed rarely.

```python
@dataclass(frozen=True)
class Entities:            # output of Stage-1 understand
    intent: str
    area: str | None
    locality: str | None
    category: str | None
    price_max: int | None
    store_names: list[str]

@dataclass(frozen=True)
class GeoResult:           # output of geo.py
    center: tuple[float, float] | None
    radius_km: float | None
    store_ids: list[str]
    nearest_metro: dict | None      # {name, line, distance_m} or None

@dataclass
class Trip:                # the mutable plan (only thing state persists)
    store_ids: list[str]
    center: tuple[float, float] | None
    radius_km: float | None
    origin_label: str | None        # "Koramangala thrift run"

@dataclass
class Prefs:               # personalization
    liked_categories: list[str]
    disliked_categories: list[str]
    budget_ceiling: int | None
    home_area: str | None

@dataclass
class ChatResult:          # what engine returns; superset of today's dict
    reply: str
    intent: str
    stores: list[dict]
    suggestions: list[str]
    map: dict | None = None         # Pillar 4
    action: dict | None = None      # Pillar 4
    trip: dict | None = None        # Pillar 3 (serialized Trip)
```

`ChatResult` serializes to exactly today's JSON plus optional keys → rule 5 satisfied by construction.

---

## 4. Phase 0 — Clean carve-out (refactor, zero behaviour change)

**Goal:** create the clean skeleton *before* adding features, so pillars drop into a tidy structure instead of bloating `respond()`.

1. Create `app/chat/` package + `contracts.py`.
2. Move Stage 1–3 helpers (`_normalize`, `_detect_intent`, `_extract_*`, `_rank`, `_build_context`) out of `ml/chatbot.py` into `chat/retrieval.py`, exposing two clean entry points:
   - `understand(msg, db) -> Entities`
   - `retrieve(db, entities) -> (list[Store], list[dict] context)`
3. **Kill the 150-line if-else.** Move each intent's draft-reply logic into `chat/handlers.py` as a registry:
   ```python
   HANDLERS: dict[str, Callable[[HandlerCtx], Draft]] = {...}
   ```
   Each handler is a small pure-ish function taking a context object and returning a draft (reply text + store list + suggestions). Adding an intent later = add one entry, touch nothing else.
4. Create `chat/engine.py::respond(msg, db, user, session_id=None) -> dict` that runs: `understand → retrieve → dispatch handler → phrase (llm) → serialize ChatResult`. This is a mechanical move of today's flow.
5. Update the single import site — [routers/misc.py:56](../app/backend/app/routers/misc.py#L56) — to call `engine.respond(...)`. Delete `ml/chatbot.py` once green (update `_verify.py`/`_audit.py` imports).

**Done when:** existing `_verify.py` and `_audit.py` pass unchanged (same outputs). Pure refactor, no new behaviour.

---

## 5. Pillar builds (each independent, each shippable alone)

Every pillar: **new files only + one wiring line in `engine.py`.** No pillar touches another pillar's files.

### Pillar 1 — Whole brain (`chat/geo.py`)  ·  flag: `CHAT_GEO`

- **New file** `chat/geo.py`, one public function:
  ```python
  def locate(db, entities) -> GeoResult   # calls ml.clusters.find_cluster + metro nearest
  ```
  Resolves an area/locality to a coordinate (reuse existing area-coords), calls `find_cluster`, attaches nearest metro. Pure adapter — returns a `GeoResult`, no reply text.
- **Engine wiring (1 block):** when `CHAT_GEO` on and intent is geographic, call `geo.locate()`; pass its `store_ids` to retrieval ordering and stash `GeoResult` for Pillars 3/4. When off → today's string-match path.
- **Isolation:** geo.py imports `ml.clusters` + metro logic only. Knows nothing of state, trips, or maps.
- **Tests:** `test_geo.py` — given a seeded area, `locate()` returns a cluster + metro. No engine needed.
- **Done when:** "stores near Indiranagar" returns the same store set the map's `/api/clusters/find` returns.

### Pillar 2 — Session state (`chat/state.py`)  ·  flag: `CHAT_STATE`

- **New file** `chat/state.py` — a tiny pluggable store behind an interface:
  ```python
  class SessionStore(Protocol):
      def get(self, sid) -> Session
      def put(self, sid, session) -> None
  class InMemoryStore(SessionStore): ...   # dict + LRU/TTL; default
  ```
  `Session` holds `{ last_entities, current_trip: Trip|None, prefs: Prefs }`. Swappable for Redis later by implementing the Protocol — zero ripple.
- **Engine wiring (2 lines):** load session at start via `session_id`, save at end. If `session_id` is `None` or flag off → a throwaway empty session (stateless, = today).
- **Isolation:** state.py imports `contracts` only. It stores data; it has no opinion about what's in it.
- **Frontend:** generate a `session_id` (uuid) once, keep in `sessionStorage`, send it in `api.chat`. `ChatIn.session_id` already exists ([schemas.py:39](../app/backend/app/schemas.py#L39)).
- **Tests:** `test_state.py` — put/get roundtrip, TTL eviction. Pure.
- **Done when:** two sequential requests with the same `session_id` share a `current_trip`.

### Pillar 3 — Trip-shaped output (`chat/trip.py`)  ·  flag: `CHAT_TRIPS`

- **New file** `chat/trip.py` — **pure functions**, no DB, no state:
  ```python
  def build(stores: list[dict], geo: GeoResult|None, prefs: Prefs|None) -> Trip
  def refine(trip: Trip, op: RefineOp, stores_index) -> Trip   # add/drop/filter-open/cheaper
  ```
  `build` shapes a coherent ~3–5 shop set (prefers geo cluster membership when present). `refine` returns a *new* Trip (immutable-style) for a parsed op.
- **Engine wiring:** discovery intents call `trip.build(...)` and put the Trip on the session (Pillar 2). "cheaper/add/drop" utterances parse to a `RefineOp` and call `trip.refine(...)`. Refinement needs Pillar 2; if `CHAT_STATE` is off, `build` still works (returns a one-shot Trip, just not refinable).
- **Isolation:** trip.py imports `contracts` only. Given lists in, Trip out. No I/O.
- **Tests:** `test_trip.py` — build from fixture stores; each refine op transforms correctly. Zero mocks.
- **Done when:** "plan a Koramangala run under ₹600" → a Trip; "drop the pricey one" → the same Trip minus one store.

### Pillar 4 — Map-aware output (`chat/mapspec.py`)  ·  flag: `CHAT_MAP`

- **New file** `chat/mapspec.py` — **pure**:
  ```python
  def build(geo: GeoResult|None, trip: Trip|None, stores: list[dict]) -> tuple[map|None, action|None]
  ```
  Produces the `map` render spec + `action` deep-link from data already computed by Pillars 1/3. No new retrieval.
- **Engine wiring (1 line):** call `mapspec.build(...)`, attach `map`/`action` to `ChatResult`. Off → both `None`, response unchanged.
- **Frontend:** a reusable `<MiniMap>` component (extract from `Zones.jsx`'s map). `ChatCore.jsx` renders `<MiniMap>` when `m.map` present and a "View on full map →" button when `m.action` present (deep-links to `/zones?lat=..&lng=..&radius=..`).
- **Isolation:** mapspec.py imports `contracts` only. Frontend `<MiniMap>` is shared by chat + Zones — one component, no fork.
- **Tests:** `test_mapspec.py` (pure) + a manual `<MiniMap>` render check.
- **Done when:** a geographic answer shows an inline map; the button opens Zones pre-centered.

### Standalone — SHOP advice (`chat/advice.py` + `data/thrift_advice.json`)  ·  flag: `CHAT_ADVICE`

- **New file** `chat/advice.py` — pure lookup over a hand-written `data/thrift_advice.json` (topic → tip). New `shopping_advice` intent handler in `handlers.py`; optional category-tip garnish on discovery drafts.
- **Isolation:** depends on `contracts` + the data file. Touches nothing else. Genuinely independent — no pillar, buildable first or last.
- **Done when:** "how do I check a thrifted jacket?" returns curated advice.

---

## 6. Personalization (small, rides on Pillars 2 + retrieval)

No new module — a `Prefs` field on the session (Pillar 2) + a soft-boost hook in `retrieval.py` ranking. Explicit capture ("I like vintage, budget ₹500") writes `Prefs`; ranking reads it as a *soft boost, never a hard filter* (preserves the honest-set philosophy). Interaction-based `user_recs()` already works and is untouched. Skip until Pillar 2 lands.

---

## 7. Frontend changes (mirror the backend discipline)

| File | Change | Coupling |
|------|--------|----------|
| `api.js` | send `session_id` in `chat()` | trivial |
| `ChatCore.jsx` | render `<MiniMap>` if `m.map`; "View on full map" if `m.action` | additive, guarded by presence |
| `components/MiniMap.jsx` (new) | extract map from `Zones.jsx`; props: center, radius, stores, metro | shared component |
| `Zones.jsx` | read `?lat&lng&radius` query params to honor deep-links; use `<MiniMap>` | additive |

All frontend changes are presence-guarded (`m.map && ...`) → old responses render exactly as today.

---

## 8. Build sequence (each row independently mergeable)

| Step | Deliverable | Depends on | Flag |
|------|-------------|-----------|------|
| 0 | Clean carve-out (§4) — refactor, no behaviour change | — | — |
| 1 | Pillar 1 geo adapter | Phase 0 | `CHAT_GEO` |
| 2 | SHOP advice (fully standalone) | Phase 0 | `CHAT_ADVICE` |
| 3 | Composite discovery + "why this store" | Phase 0 | — |
| 4 | Pillar 2 session state | Phase 0 | `CHAT_STATE` |
| 5 | Pillar 3 trips | P1 (better with), P2 (refine needs) | `CHAT_TRIPS` |
| 6 | Pillar 4 map + `<MiniMap>` | P1 | `CHAT_MAP` |
| 7 | Personalization soft-boosts | P2 | `CHAT_PREFS` |

Steps 1–3 depend only on Phase 0 and can land in any order / in parallel. The only real chain is P2 → P3(refine) and P1 → {P3 quality, P4}. Nothing else couples.

---

## 9. Testing strategy (isolation makes it cheap)

- **Pure modules** (`trip`, `mapspec`, `advice`, `contracts`): plain unit tests, no DB, no mocks — the payoff of rule 3.
- **I/O modules** (`geo`, `retrieval`, `state`): small tests against the seeded DB / in-memory store.
- **Engine**: a handful of end-to-end tests via the existing `_verify.py` harness (`POST /api/chat`), one per pillar flag on/off.
- **Regression guard:** every flag OFF must reproduce today's `_verify.py`/`_audit.py` output byte-for-byte. This is the airtight guarantee that pillars never break the baseline.

---

## 10. Explicit non-goals (scope fences)

To keep the surface clean, this plan **does not**:

- Give the LLM tool-calling or let it manage state (stays a grounded phraser).
- Add real turn-by-turn routing (hand off to Google Maps URL; trip ordering is nearest-neighbour, owned by the trip-planner doc).
- Add item-level inventory discovery (blocked on data we don't have).
- Duplicate any map control inside chat beyond the read-only `<MiniMap>` (the Zones page owns interactive map UX).
- Introduce a new datastore (in-memory `SessionStore` now; Redis only if/when multi-instance, via the existing Protocol — no code ripple).

---

## 11. One-glance summary

- **New package** `app/chat/`: `contracts, retrieval, handlers, geo, state, trip, mapspec, advice, engine`.
- **One composition point:** `engine.respond()`. **One backend seam:** `misc.py` import. **One contract file** everyone shares.
- **Every pillar:** new files + a flag + one wiring block. Independent, pure where possible, additive, off-by-default-safe.
- **The DAG forbids spaghetti:** no `chat/*` module imports another; the graph literally can't cycle.
