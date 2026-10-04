# Chatbot Capabilities — Brainstorm

> The ThriftFind chatbot is the app's primary interface. This doc argues for a single shift in how we think about it — **from a stateless lookup tool into a stateful shopping companion that shares one brain with the map** — then works through what that unlocks across the five shopping-journey stages (Discover → Plan → Navigate → Shop → Personalize).
>
> Companion docs: map UX in `map-ux-brainstorm.md`, the map-side trip planner in `shopping-trip-planner-brainstorm.md`. This doc is the **conversational** layer; where it overlaps NAVIGATE/PLAN, it reuses the trip-planner's mechanics rather than reinventing them.

---

## The central idea

Today the chatbot is a **stateless lookup over half a brain**: each message is answered independently, using only the *tabular* half of a knowledge base it already shares with the map (string area-match, price, category), while the *geospatial* half of that same brain (live clustering, radius search, metro proximity) sits unused a few files away.

The best-case ThriftFind chatbot is the opposite on both axes. It is a **shopping companion** that:

1. **Uses the whole brain** — the chatbot and the map read the *same* data and call the *same* geospatial engine, so they can never disagree, and every answer can be metro-aware. *(Pillar 1 — your Q1)*
2. **Remembers the conversation** — a lightweight session state lets a plan be refined turn to turn ("cheaper", "add Indiranagar", "only open ones"). *(Pillar 2)*
3. **Thinks in trips, not lists** — discovery returns a coherent, walkable *set* of shops that seeds a plan, not a scattered top-6. *(Pillar 3 — your Q2)*
4. **Shows, not just tells** — geographic answers carry a small inline map and can hand off to the full Zones page. *(Pillar 4 — your Q3)*

These four **pillars** are the spine of this doc. The five journey stages are what they add up to: get the pillars right and DISCOVER→PLAN→NAVIGATE fall out almost for free, because they stop being separate features and become one continuous "find shops → shape a trip → walk it" flow.

---

## Current State — how the chatbot works today

`chatbot.respond(msg, db, user)` is a **stateless, single-turn** pipeline ([app/backend/app/ml/chatbot.py](../app/backend/app/ml/chatbot.py)):

1. **Understand** — normalize text, detect intent (regex → fuzzy fallback), extract area / category / price / store names. Token-free.
2. **Retrieve** — hard filters (area/locality, visibility) bound the set; category/price exclude only *known* violations; open-now & experience_score only *rank*. Honest empty sets, no city-wide padding.
3. **Context** — assemble a full per-store payload (hours, price, contact, sentiment, snippets).
4. **Phrase** — Groq rephrases the deterministic draft, grounded strictly in retrieved stores ([llm.py](../app/backend/app/ml/llm.py)). Falls back to the rule-based draft on any failure.

**Intents today:** `find_by_area`, `find_by_category`, `find_by_price`, `open_now`, `zone_exploration`, `store_recommendation`, `review_insight`, `store_comparison`, `best_time_to_visit`, `general_assistance`.

**Two structural limits shape everything below:**

- **It's stateless.** Each message is independent — no memory, no mutable plan, no learned preferences. `respond()` is one-message-in, one-reply-out.
- **It uses half the brain.** It retrieves via string area-match (`_rank`) and never calls the geospatial engine (`find_cluster`, `split_cluster`, `cluster_stores`, `metro/nearest`) that the map is built on — even though both sit on the same DB and serializers.

DISCOVER works well *because* it needs neither. The other four stages need one or both. That's the whole story of the scorecard.

---

## Scorecard — coverage against the 5 stages

| Stage | Coverage | What's missing | Pillar that fixes it |
|-------|----------|----------------|----------------------|
| 🔎 DISCOVER | ~75% ✅ | Store-level not item-level; scattered results | P1 (whole brain), P3 (trips) |
| 🗺️ PLAN | ~40% ⚠️ | Can't refine — no memory | P2 (state), P3 (trips) |
| 🚶 NAVIGATE | ~5% ❌ | No routing/ordering in chat | P1 (metro), P2 (state), P4 (map) |
| 🛍️ SHOP | ~25% ⚠️ | Advice hardcoded in one intent | *(none — standalone)* |
| 👤 PERSONALIZE | ~20% ⚠️ | No conversational memory | P2 (state) |

> **Your input:** Do these coverage numbers match your intuition? Anything you'd rank higher/lower?
> _(space for your notes)_

---

## The four pillars

This is the heart of the doc. Each pillar has: **the idea → why it fits THIS app → options ranked → your open question.** SHOP is the one capability that stands apart from the pillars, so it lives in its own short section afterward.

---

### Pillar 1 — Use the whole brain *(your Q1: shared knowledge base)*

**Short answer: the shared brain already exists; the chatbot only uses half of it.**

The chatbot and the zonal/map features already sit on **one knowledge base** — the same DB (`Store`, `Zone`, `Review`) and the same serializers. This is true in code today, not aspirational:

- `zone_to_dict()` in [utils.py](../app/backend/app/utils.py) is documented as the *"single source of truth for /api/zones, /api/clusters, and the chatbot."*
- `store_to_dict()`, `haversine_km()`, `is_open_now()`, `sentiment_summary()`, `STORE_HAS_COORDS` are shared helpers used by both surfaces.

So there's no silo to bridge. The gap is which *half* of the brain the chatbot taps:

| Capability | Map / zonal uses it | Chatbot uses it today |
|------------|:---:|:---:|
| Store / Zone / Review tables | ✅ | ✅ |
| String area / locality match (`_rank`) | ✅ | ✅ |
| `find_cluster(lat, lng, radius)` — live radius search | ✅ | ❌ |
| `split_cluster()` — break an over-dense cluster | ✅ | ❌ |
| `cluster_stores()` — HDBSCAN geographic zones | ✅ | ❌ |
| `metro/nearest` — nearest station + walking distance | ✅ | ❌ |

**Why this fits ThriftFind:** metro proximity is the app's entire premise, and it's one unused helper call away. Wiring the chatbot to the geospatial engine:

- Makes geographic queries **coherent** — "stores near Indiranagar" calls `find_cluster()` and returns a real cluster (radius, coords, avg score/price), the *same* result the map would show. Chat and map stop being able to disagree.
- Makes every answer **metro-aware** — *"Love Me Twice — 400 m from Indiranagar metro (Purple Line)"* via `metro/nearest`.
- Makes zone talk **consistent** — chat zone summaries come from the same precomputed `Zone` rows the map renders.

**Options**

- **A. Chatbot calls the geospatial engine directly (recommended).** Geographic intents route through `find_cluster` / `metro/nearest` instead of string-match. One brain, two front doors.
- **B. Keep chat on string-match, sync manually.** Lower touch, but chat and map will drift as the map evolves. Rejected — reintroduces the silo we don't have.
- **C. Extract a shared retrieval service** both surfaces import. Cleanest long-term, more upfront refactor. Worth it only if a third surface appears.

**Recommendation:** A. It's cheap (functions exist and are tested), it's on-brand (metro), and it's the foundation the other three pillars stand on.

**Why this is the linchpin:** P3 (coherent trip sets) *needs* clustering; P4 (inline maps) *needs* cluster coords + metro. Do P1 first and both become easy.

> **Your input — whole brain:** Agree the chatbot should call `find_cluster`/`metro nearest` directly? Any reason to keep chat's retrieval separate from the map's?
> _(space for your notes)_

---

### Pillar 2 — Remember the conversation *(session state, the keystone)*

Three stages (PLAN, NAVIGATE, PERSONALIZE) are gated on the **same** missing piece: **state**. Today `respond()` forgets everything between messages. Add a lightweight per-session context —

```
{ last_intent, last_entities, candidate_stores, current_plan, stated_prefs }
```

— and each of those stages unlocks at once:

- PLAN gets a `current_plan` to *refine* ("make it cheaper" mutates the set instead of starting over).
- NAVIGATE gets a set to *order* (the `current_plan`).
- PERSONALIZE gets somewhere to *hold* stated preferences.

**Options**

- **A. Minimal session-scoped state dict (recommended).** Keyed by session (logged-out) or user (logged-in). Small, unlocks three stages, keeps the LLM as a pure phraser.
- **B. Stateless "restate everything each turn."** No code, worse UX — exactly the friction we're removing.
- **C. Full LLM agent with tool-calling.** The LLM manages state and calls retrieval tools itself. Most flexible, most tokens, hardest to keep grounded — overkill for a <100-store dataset.

**Recommendation:** A. **If we build one thing, it's this.** It's the difference between a lookup box and a companion.

> **Your input — state:** Where should it live — browser (per-tab, logged-out friendly) vs backend session/user (cross-device, needs login)? How many turns of memory is "enough"? Comfortable keeping the LLM phrasing-only (A) rather than tool-calling (C)?
> _(space for your notes)_

---

### Pillar 3 — Think in trips, not lists *(your Q2: shopping experience)*

You asked whether the bot can *"provide a shopping experience — a few shops meeting the criteria — so it can later use this to plan."* Yes — and it's the bridge from DISCOVER to PLAN.

**Where we are:** the bot returns a ranked top-6. But it's a flat *list of matches*, not a *shopping outing*: nothing carries forward, and the shops can be scattered across the city.

**Best case:** reshape discovery output into a **candidate shopping experience** — a small, coherent set (~3–5 shops) that is:

1. **Constraint-meeting** — matches stated area/category/budget/open-now (already done by `_rank`).
2. **Geographically coherent** — the shops are actually near each other, so visiting them as one trip makes sense. This is exactly what `find_cluster()` / `split_cluster()` produce (**Pillar 1**). A flat top-6 by score can scatter; a cluster is walkable.
3. **Held as `current_plan`** (**Pillar 2**) — so the next message ("drop the pricey one", "add a vintage place", "order these") refines *this* set. That's the seed the trip planner (`shopping-trip-planner-brainstorm.md`) consumes.

Notice this pillar is literally P1 + P2 pointed at discovery output. That's why the pillars compound.

**Options**

- **A. Cluster-backed candidate set (recommended).** Geographic discovery returns a `find_cluster`-based coherent set, stored as `current_plan`, framed as an experience: *"Here's a walkable Koramangala thrift run — 4 shops under ₹600, all open now."*
- **B. Score-ranked flat set (today).** Simpler, but shops may be far apart → a poor basis for a plan.
- **C. LLM-composed itinerary narrative (later).** Groq phrases the set as a mini shopping story ("start at X for denim, then Y two minutes away…"), grounded strictly in the retrieved cluster + metro data.

**Recommendation:** A as the mechanism, C as phrasing polish once P1/P2 land. **This is not LLM fine-tuning** — it's shaping retrieval into trip-shaped sets; the LLM stays a grounded phraser.

> **Your input — trips:** Always try to form a coherent trip set, or only on explicit trip intent ("plan a run")? Ideal set size — 3, 5, more? Prefer walkable-tight even if it means a slightly lower-rated shop?
> _(space for your notes)_

---

### Pillar 4 — Show, don't just tell *(your Q3: zonal wiring + inline map)*

You asked whether the chatbot can *"activate the zonal features when needed, give better answers, and show a small map for context."* Yes — this is the front-end payoff of Pillar 1.

**What makes it easy:** the chat response already carries `stores` with `lat`/`lng`, and `/api/chat` is a normal JSON endpoint. Two *additive* payload fields turn chat map-aware with no breaking changes:

- **`map`** — a render spec: `{ center: {lat,lng}, radius_km, stores:[…coords…], metro:{nearest station/line} }`. The frontend ([ChatCore.jsx](../app/frontend/src/components/ChatCore.jsx)) renders a **mini Leaflet map inside the chat bubble** for geographic answers. Extract the Zones map into a reusable `<MiniMap>` so chat and Zones share one component — the shared-brain principle, on the frontend.
- **`action`** — an optional directive like `{ type: "open_zones", params: { lat, lng, radius_km } }`. A "View on full map →" button deep-links into the Zones page **pre-configured** with that cluster. That is literally *"the chatbot activating the zonal feature."*

Because the `map` payload is basically the `find_cluster` output from Pillar 1, this pillar is mostly frontend glue once P1 exists.

**Options**

- **A. Inline mini-map + "open full map" deep link (recommended).** Quick context in chat, full power on the map. Best of both.
- **B. Deep-link only (no inline map).** Chat stays text + cards; a button opens Zones. Lower effort, less magic, more context-switching.
- **C. Full map controls in chat** (radius slider, drag, split). Duplicates the Zones page and clutters chat — the map UX doc already owns that surface. Avoid.

**Recommendation:** A. Inline mini-map for context, deep link for depth.

> **Your input — show:** Inline mini-map (A) or deep-link only (B)? When the bot "activates zones," navigate the user to the Zones page or keep them in chat with the mini-map? Any concern with asking for the user's location to center the map?
> _(space for your notes)_

---

## The one stage outside the pillars — 🛍️ SHOP

*"What to look for, how to thrift well?"*

**Where we are (~25%):** one genuinely useful bit — `best_time_to_visit` gives real advice (mornings for fresh stock, avoid Sunday evenings, Monday closures). But it's hardcoded inside one intent; there's no general thrift-knowledge capability. Unlike the other stages, SHOP doesn't depend on any pillar — it's a content problem, not an architecture one, which makes it an easy independent win.

**Best case:** a small, curated **thrift-advice knowledge layer** — inspecting garments, spotting fakes, checking zippers/seams, bargaining politely, what's worth buying secondhand — as its own intent and woven contextually into store answers ("this store leans denim — check the inseam and rivets").

**Options**

- **A. Curated advice intent (recommended, low effort).** A `shopping_advice` intent backed by a small hand-written knowledge file. Deterministic, grounded, on-brand, no hallucination risk.
- **B. LLM free-form advice.** Fast to ship but ungrounded — breaks the "never invent" discipline the rest of the bot keeps.
- **C. Category-contextual tips (nice add-on).** Attach a tip to category results. Small, delightful, reinforces expertise.

**Recommendation:** A as the backbone, C as a garnish on discovery results. Avoid B as the primary.

> **Your input — SHOP:** Hand-write the advice (A), or let the LLM freewheel for this stage only (B)? Any advice topics you definitely want covered?
> _(space for your notes)_

---

## How the pillars add up — the five stages, revisited

The pillars aren't abstract; they *are* the stages. Reading the journey through them:

| Stage | Today | With the pillars |
|-------|-------|------------------|
| 🔎 **DISCOVER** | Flat, store-level, string-matched (~75%) | Coherent metro-aware trip sets with "why this store" rationale (P1+P3) |
| 🗺️ **PLAN** | Static zone readout, no refine (~40%) | A `current_plan` you refine conversationally (P2+P3) |
| 🚶 **NAVIGATE** | Absent (~5%) | Order the current set (metro-aware), show it on the mini-map, hand off to Maps (P1+P2+P4) |
| 🛍️ **SHOP** | One hardcoded tip (~25%) | A curated advice layer + contextual tips *(no pillar needed)* |
| 👤 **PERSONALIZE** | Interaction-based recs only (~20%) | Remembered preferences applied as soft boosts (P2) |

Two things stand out. First, **DISCOVER, PLAN and NAVIGATE collapse into one flow** once the pillars exist — "find shops → shape a trip → walk it" is a single conversation over a `current_plan`, not three features. Second, the two stages that *don't* lean on the pillars (SHOP, and the interaction-recs half of PERSONALIZE) are the cheap standalone wins to ship early while the pillars land.

**Detail on the two stages the table compresses:**

- **NAVIGATE** should be a *front door* to the trip planner, not a reimplementation. New `plan_route` intent orders the `current_plan` with the trip planner's own nearest-neighbour / metro-aware logic (`shopping-trip-planner-brainstorm.md` §c) — **one routing implementation, two surfaces.** Reply = numbered itinerary + distances + the mini-map + a Google Maps deep link.
- **PERSONALIZE** has two tracks: explicit preference capture ("I like vintage, budget ~₹500") stored in `stated_prefs` and applied as *soft* ranking boosts (never hard filters — keeps the "honest set" philosophy); and implicit inference from chat/interaction history later. The existing `user_recs()` interaction-based recommendation already works and needs no pillar — ship it as-is.

> **Your input — the flow:** Does collapsing DISCOVER→PLAN→NAVIGATE into one `current_plan` conversation match how you want the product to feel? Should NAVIGATE render inline or mostly hand off to the map?
> _(space for your notes)_

---

## Suggested build order

Ordered so each phase unlocks the next. **Pillar 1 is the cheap linchpin** — do it first and Pillars 3 and 4 get most of the way there for free.

| Phase | Change | Pillar / Stage | Effort |
|-------|--------|----------------|--------|
| 0 | **Wire chatbot to the geospatial engine** (`find_cluster` + `metro/nearest`) | P1 (Q1) | Low |
| 0 | **Composite discovery** (pass all entities to `_rank`) + "why this store" rationale | DISCOVER | Low |
| 0 | **Curated `shopping_advice` intent** + category tips | SHOP | Low |
| 1 | **Session state** — the keystone dict | P2 | Medium |
| 1 | **Trip-shaped discovery** — cluster-backed set held as `current_plan` | P3 (Q2) | Medium |
| 1 | **Plan refinement** ("cheaper", "add X", "only open") | PLAN | Medium |
| 2 | **Inline mini-map + "open full map" deep link** | P4 (Q3) | Medium |
| 2 | **`plan_route` intent** reusing trip-planner ordering (shared impl) | NAVIGATE | Medium |
| 2 | **Explicit preference capture** as soft boosts | PERSONALIZE | Medium |
| 3 | **Metro-aware routing** in chat + map (the differentiator) | NAVIGATE+ | Medium-High |
| 3 | **Implicit preference inference** from history | PERSONALIZE+ | Medium-High |
| — | Item-level discovery / full profile memory | blocked on data | High |

> **Your input — priorities:** Reorder, cut, or star anything. What's the ONE thing you'd ship first?
> _(space for your notes)_

---

## Open questions (for you)

1. **Whole brain (Q1)** — chatbot calls `find_cluster`/`metro nearest` directly so chat and map never disagree, or keep chat on its own string-match?
2. **State location** — browser (logged-out friendly, per-tab) vs backend session/user (cross-device, needs login)? The trip-planner doc leans localStorage-first — should chat match?
3. **Trip sets (Q2)** — always form a coherent set on discovery, or only on explicit trip intent? Preferred set size? Favour walkable-tight over highest-rated?
4. **Show (Q3)** — inline mini-map or deep-link only? "Activate zones" = navigate away or stay in chat? OK to ask for user location to center the map?
5. **LLM role** — keep Groq strictly phrasing-only (safe, grounded), or let it call retrieval/plan tools (flexible, more tokens, harder to ground)?
6. **The flow** — is collapsing DISCOVER→PLAN→NAVIGATE into one `current_plan` conversation the product feel you want?
7. **Personalization consent** — remember silently or confirm what was stored? Cross-session persistence, or session-only for privacy?
8. **SHOP content** — hand-write the advice (grounded), or accept LLM free-form for that stage only?
9. **Launch bar** — which stages must be "good" for a launch you'd be proud of, and which can ship at current coverage?
