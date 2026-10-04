# Saved Lists (Zonal) — Privilege 3

> Part of the [Accounts & Logged-In Privileges](ACCOUNTS_FEATURES_INDEX.md) work.
> **Depends on** [ACCOUNTS_AND_AUTH_PLAN.md](ACCOUNTS_AND_AUTH_PLAN.md).

## Requirement

In the zonal feature, a logged-in user can **save the list of shops in a cluster
at any time**, giving it **any name they choose** to identify it among their other
lists, and can **view their saved lists** later. Guests cannot save lists (but can
build one and are prompted to log in — continuity from File 1).

## Where this hangs off

The zonal "cluster" is produced by `GET /api/clusters/find` (Mode B) and rendered
by [ClusterResult.jsx](app/frontend/src/components/zones/ClusterResult.jsx). A
cluster result carries `label`, `count`, `radiusKm`, `avgScore`, and
`stores[] = { id, name, area, score, priceBand, distKm, ... }`. A "saved list" is a
**named snapshot of the store ids in that cluster** plus the cluster's defining
parameters (center + radius) so it can be re-shown on the map.

This is distinct from the existing localStorage "hearts"
([lib/saved.js](app/frontend/src/lib/saved.js)) — hearts are individual store
favourites; **lists are named collections**. They can share the "Saved" area in
the navbar but are different objects. (Optionally, hearts become "your default
list" — see Open Questions.)

## Data model

Add to [models.py](app/backend/app/models.py):

```python
class SavedList(Base):
    __tablename__ = "saved_lists"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name       = Column(String(120), nullable=False)     # user-chosen label
    # Cluster provenance so the list can be re-rendered on the zones map:
    center_lat = Column(Float, nullable=True)
    center_lng = Column(Float, nullable=True)
    radius_km  = Column(Float, nullable=True)
    source_label = Column(String(160), nullable=True)    # the cluster's label at save time
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)
    items      = relationship("SavedListItem", back_populates="list",
                              order_by="SavedListItem.position",
                              cascade="all, delete-orphan")

class SavedListItem(Base):
    __tablename__ = "saved_list_items"
    id       = Column(Integer, primary_key=True)
    list_id  = Column(Integer, ForeignKey("saved_lists.id"), nullable=False, index=True)
    store_id = Column(String(20), ForeignKey("stores.id"), nullable=False)
    position = Column(Integer, default=0)                # preserve display order
    note     = Column(String(300), nullable=True)        # optional per-store note
    list     = relationship("SavedList", back_populates="items")
```

Add `saved_lists = relationship("SavedList", ...)` to `User`. (Migration caveat
from File 1 applies — new tables via `create_all` are fine on a fresh DB but need
a migration/`ALTER` on an existing one.)

- **Name uniqueness:** enforce unique `(user_id, name)` so "identify that list
  among other lists" is meaningful; on collision return 409 and let the UI suggest
  "My list (2)".
- Storing **store ids only** (not a copy of store data) keeps lists live — if a
  store's score/hours change, the saved list reflects current data when viewed.
  Handle stores later deleted/hidden gracefully (skip on read).

## Endpoints (all `get_current_user`; ownership-checked)

| Method | Path | Body / notes | Purpose |
|---|---|---|---|
| POST | `/api/lists` | `{ name, store_ids[], center_lat?, center_lng?, radius_km?, source_label? }` | Save a new list from the current cluster |
| GET | `/api/lists` | — | List the user's lists (id, name, item count, updated_at) for the "My Lists" view |
| GET | `/api/lists/{id}` | — | Full list: metadata + hydrated stores (via `store_to_dict`) in order |
| PATCH | `/api/lists/{id}` | `{ name?, add_ids?[], remove_ids?[] }` | Rename / add / remove stores |
| DELETE | `/api/lists/{id}` | — | Delete a list |

- New schemas in [schemas.py](app/backend/app/schemas.py): `SavedListIn`,
  `SavedListPatch`. Validate `name` (1–120 chars, trimmed) and `store_ids`
  non-empty on create.
- New router `app/backend/app/routers/lists.py`, registered in
  [main.py](app/backend/app/main.py) alongside the others.
- `GET /api/lists/{id}` reuses `store_to_dict` and should filter hidden/no-coord
  stores the same way the rest of the app does (`has_coords`).

## Frontend

- **Save action in the zones view:** add a "**Save this list**" button near the
  cluster header in [ClusterResult.jsx](app/frontend/src/components/zones/ClusterResult.jsx)
  (or its parent [Zones.jsx](app/frontend/src/pages/Zones.jsx)). Clicking opens a
  small name prompt (default the cluster `label`), then:
  - Logged-in → `api.createList({ name, store_ids: result.stores.map(s=>s.id),
    center_lat, center_lng, radius_km, source_label: result.label })`.
  - Guest → `requireAuth` stashes a `{ type: 'save_list', ... }` pending action
    (File 1 D1) and redirects to `/auth`; after login the list is created
    automatically and the user is returned to the zones view.
- **"My Lists" view:** a new route `/lists` wrapped in `<RequireAuth>`:
  - Grid/list of the user's saved lists (name, store count, when saved).
  - Open a list → show its stores (reuse `StoreRow`/`StoreCard`) and, if it has
    `center/radius`, an "**Open on map**" action that re-runs the cluster on the
    zones map so they see the exact zone again.
  - Rename (inline edit → `PATCH`), remove a store, delete the whole list.
- **Navbar entry point:** add a "My Lists" link (visible only when `user`), or fold
  it into the existing `♥ SAVED` chip as a dropdown ("Hearted stores" + "My lists").
- `api.js`: `createList`, `lists`, `list(id)`, `updateList(id, patch)`,
  `deleteList(id)`.

## Continuity (File 1, Part D)

- **In-flight:** the `save_list` pending action resumes after login (above).
- **Accumulated:** if you let guests *build* a draft list client-side before
  logging in, persist that draft in localStorage and migrate it to a real
  `SavedList` on first login (idempotent — tag the draft with a client id so a
  double migration doesn't duplicate).

## Testing / acceptance

- Save a cluster as "Koramangala run" → appears in `/lists` with correct stores &
  order.
- Two lists can't share a name for one user; the same name is fine across users.
- Reopen a list after a store's score changes → shows current score (ids, not
  snapshots).
- Guest builds a list → prompted to log in → list is created post-login and they
  land back on zones.
- Ownership: user B gets 404/403 on user A's list id for GET/PATCH/DELETE.
- Deleting a list removes its items (cascade), not the stores.

## Open questions

1. Should the existing localStorage **hearts** become a special auto-created list
   ("Favourites") once server-backed, or stay a separate lightweight concept?
   (Recommended: keep hearts as quick per-store favourites; lists are the named,
   zone-derived collections.)
2. Do lists need to be **reorderable** by the user (drag), or is saved order
   (by score/distance) enough? `position` supports both.
3. Any need to **share** a list (public link)? Out of scope now, but the model
   (add a `share_token`) leaves room.
