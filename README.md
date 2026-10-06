# FirstFind

AI-powered store discovery for Bengaluru — search by area, budget, or vibe, chat with a style assistant, and see live sentiment on real stores.

🔗 **Live demo:** https://first-find.vercel.app
🧰 **Tech stack:** [TECHSTACK.md](TECHSTACK.md)

---

## What it does

- **Explore** 100+ verified thrift stores on an interactive map with walkable-radius clustering, Namma Metro overlay, open-now filters, and personalized ranking.
- **Chat assistant** (Groq LLM + rule-based fallback) handles natural queries like _"vintage under ₹500 near Koramangala"_ or _"what's open now?"_ and returns stores + an inline map.
- **Reviews + sentiment**: users post reviews, a HuggingFace sentiment model (`cardiffnlp/twitter-xlm-roberta-base-sentiment`) runs in the background, and each store surfaces a live sentiment meter.
- **Accounts**: email/password + **Google sign-in** (Google Identity Services), with JWT sessions, saved lists, and personalized recommendations driven by interaction history.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 · Vite · Leaflet · React Router |
| Backend | FastAPI · SQLAlchemy · PostgreSQL (Supabase in prod, SQLite locally) |
| ML | HuggingFace Inference API (sentiment) · VADER fallback · Groq LLM (chat phrasing) |
| Auth | JWT · Google Identity Services (OpenID) |
| Hosting | Vercel (frontend) · Render (backend, Docker) · Supabase (DB) |
| Maps | Leaflet · CARTO Voyager basemap |

## Highlights worth a code read

- [app/backend/app/routers/auth_routes.py](app/backend/app/routers/auth_routes.py) — Google ID-token verification, link-existing-account flow, JWT issuance.
- [app/backend/app/ml/pipeline.py](app/backend/app/ml/pipeline.py) — background sentiment pipeline with graceful fallback.
- [app/frontend/src/components/MapExplorer.jsx](app/frontend/src/components/MapExplorer.jsx) — Leaflet integration with ResizeObserver-driven tile invalidation (so the map re-tiles correctly on layout changes).
- [app/frontend/src/components/ChatCore.jsx](app/frontend/src/components/ChatCore.jsx) — chat UI with inline MiniMap context bubbles.

---

## License

© 2026 Ashutosh Kulkarni. All rights reserved.

This repository is public for **portfolio and review purposes only**. No permission is granted to copy, modify, redistribute, deploy, or create derivative works from any part of this code without prior written consent.

The absence of an OSI-approved license file is deliberate — see [GitHub's guidance on unlicensed code](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository#choosing-the-right-license).
