# 05 — Social & Personalization

Covers: **Save & Share Routes** (export a custom crawl as a clickable link) and
**Community Presets** (user-curated zone setups, e.g. "Best 4-Shop Denim Route").

Grounded against your stack: JWT auth already exists (`auth.py`), you already have
a `User` table and an `Interaction` table (view/save/like), FastAPI + SQLAlchemy,
and `save_store` already writes a save. The plan already ranks "Shareable /
saveable crawl" as a medium-effort personalization idea (`ZONAL_STORE_HOPPER_PLAN.md`
#7).

---

## The uncomfortable answer first

Both of these are feasible and neither needs any private data from you. The catch
isn't feasibility — it's that **Community Presets is a two-sided-marketplace
feature masquerading as a UI toggle.** It only has value once you have enough
active thrifters creating and consuming routes. At 48 stores and an early user
base, you'll be building a sharing feature with no one to share with. **[Likely]**
build Save & Share first (useful for a single user with friends), and hold
Community Presets until you have the user volume to populate it — otherwise it's
an empty gallery that signals "dead app."

---

## Feasibility

### Save & Share Routes — **[Certain] feasible, moderate effort**

A "route" / "crawl" is a small, serialisable object: an ordered list of
`store_ids` + the parameters that made it (center, radius, min_shops, optional
name). You already have the auth and DB plumbing. Work breaks into:

1. **Persist a route.** New table `Route` (or `SavedCrawl`): `id, user_id, name,
   center_lat, center_lng, radius_km, store_ids (ordered), created_at`. One
   migration, one CRUD router. **[Certain]** straightforward — it mirrors your
   existing `Zone`/`Interaction` patterns.
2. **Share link.** Two designs:
   - **Stateful:** save the route, generate a short slug (`/r/ab12cd`), resolve
     it server-side. Robust, works if store data changes, needs a public
     read-only endpoint. **Recommended.**
   - **Stateless:** encode the whole route in the URL (base64 of the ids +
     params). No DB row, but ugly long links and they break if a store is
     delisted. Fine as a quick v0.
3. **Open link → render the crawl** on the existing map/cards. Mostly frontend.

The "clickable map link to coordinate with friends" is the stateful version +
rendering the ordered pins. This pairs naturally with the **route-ordering / ETA**
idea (nearest-neighbour walking path, `ZONAL_STORE_HOPPER_PLAN.md` #1) — a shared
route is far more compelling as an *ordered walkable loop* than an unordered set.
Build route-ordering alongside this.

Effort: **[Likely] 2–4 days** for stateful save + share + render, more with a
polished route-ordering path.

### Community Presets — **[Likely] feasible, but it's moderation + curation, not just code**

"Access user-curated setups like 'Best 4-Shop Denim Route'." This is Save & Share
Routes made *public and browsable*. Technically it's the same `Route` table with a
`is_public` flag + a discovery endpoint (`GET /api/routes/public?sort=popular`).
The code delta over Save & Share is small.

The **non-code** costs are the real ones, and they're the uncomfortable part:

- **Cold-start / empty gallery.** Covered above. No routes → looks abandoned.
  Mitigation: seed it yourself with 5–10 hand-built "official" routes so it's
  never empty.
- **Moderation.** Public user content = spam, junk names, dead routes when shops
  close. You need at minimum a report/hide mechanism and a way to prune routes
  pointing at delisted stores. **[Likely]** you'll underestimate this; every UGC
  feature does.
- **Ranking / trust.** "Best denim route" implies a ranking signal — likes,
  saves, completions. You have an `Interaction` pattern to reuse, but you need to
  decide what "top local thrifter" and "best" actually mean (see needs).

I disagree with shipping Community Presets in the same sprint as Save & Share.
**Instead:** ship Save & Share (single-user + friends via link), watch whether
people actually create routes, and only then flip on the public gallery — seeded
with your own routes. **The risk** in launching the community layer early is that
an empty or spammy gallery does active brand damage, worse than not having it.

---

## Privacy note you should decide up front

Shared routes expose *where a user thrifts*, and if you ever attach a username,
*who made it*. **[Likely]** you'll want: default routes private, explicit opt-in
to make public, and no personal location (home GPS) baked into a shared link.
Decide this before building the share link, because retrofitting privacy onto
already-shared URLs is painful.

---

## What I need from you (can't get reliably from web search)

1. **Stateful vs stateless share links.** I recommend stateful (short slugs,
   survive data changes, enable a public gallery later). Confirm, or tell me you
   want quick stateless links for v0. This decides the schema.

2. **What a "route" contains and whether it's ordered.** Just `store_ids`, or
   center + radius + min_shops + a walking order too? I recommend ordered (pairs
   with the ETA/route feature). Your call defines the `Route` object.

3. **The definition of "best" / "top local thrifter" for Community Presets.**
   This is a product/values decision search can't answer: is ranking by likes,
   saves, route-completions, curator reputation, or hand-picked editorial? Until
   you define it, "Best 4-Shop Denim Route" is just a title with no backing
   signal.

4. **Your moderation appetite and owner.** Who reviews/prunes public routes, and
   what's the minimum (report button? pre-publish review? auto-hide on delisted
   store?). If nobody owns moderation, don't ship the public gallery — ship
   Save & Share only.

5. **Privacy defaults.** Confirm: routes private by default, explicit opt-in to
   publish, no home GPS in shared links. I'll build to whatever you set, but I
   need it set before the share endpoint exists.

Note: unlike files 03 and 04, **none of these needs external datasets** — it's
all your own app data (users, stores, routes). The blockers here are product
decisions and operational ownership, not missing data.

   Answers: Keep this in the side for now., we will implement later.