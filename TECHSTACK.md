# Tech Stack

A quick tour of what powers FirstFind and why each piece is there.

## Frontend

| Tech | What it does here |
|---|---|
| **React 18** | Component model for the whole UI. |
| **Vite** | Dev server + build. Fast HMR; `VITE_*` env vars baked at build time. |
| **React Router v6** | Client-side routing for Explore, Store, Chat, Lists, Auth. |
| **Leaflet** | The map on Explore + the inline MiniMap in chat bubbles. |
| **CARTO Voyager** | Basemap tiles (light, label-friendly, supports a free API key). |
| **Google Identity Services** | Google sign-in button + ID-token flow. |
| **three.js** | Landing-page 3D accent. |

## Backend

| Tech | What it does here |
|---|---|
| **FastAPI** | HTTP API, dependency injection, auto-generated OpenAPI docs. |
| **Uvicorn** | ASGI server (dev + production inside Docker). |
| **SQLAlchemy** | ORM for stores, users, reviews, lists, interactions. |
| **PostgreSQL (Supabase)** | Production database. |
| **SQLite** | Local-dev database (auto-created, zero setup). |
| **psycopg2** | PostgreSQL driver (prod only). |
| **python-jose** | JWT issue + verify for auth sessions. |
| **passlib + bcrypt** | Password hashing. |
| **httpx** | Outbound calls to Groq, HuggingFace, Google tokeninfo, Places API. |
| **python-dotenv** | Loads `.env` for local dev. |

## Machine learning / AI

| Tech | What it does here |
|---|---|
| **HuggingFace Inference API** | `cardiffnlp/twitter-xlm-roberta-base-sentiment` scores every new review in a background task. |
| **VADER (nltk)** | Offline fallback when the HF token isn't set or the call fails. |
| **Groq LLM** (`llama-3.3-70b-versatile`) | Natural-language phrasing for chat replies. Rule-based fallback if no key. |
| **Custom retrieval + ranking** | Keyword + geo + intent routing in `app/chat/`; no external vector DB needed at this scale. |

## Auth

- **Email + password** (bcrypt-hashed, JWT session).
- **Google sign-in** via Google Identity Services — backend verifies the ID token against Google's `tokeninfo` endpoint, links or creates the user, and returns the same JWT.

## Maps + geo

- **Leaflet** for rendering + interaction (clustering, dragging, popups, radius circle).
- **CARTO Voyager** tiles via an API-keyed URL.
- **Haversine distance** for walkable-radius clustering and "stores near me" queries.
- **Namma Metro overlay** sourced from a local JSON of station coordinates.

## Hosting

| Where | What |
|---|---|
| **Vercel** | Frontend static build (`app/frontend`), served from CDN. |
| **Render** | Backend as a Docker web service (`app/backend/Dockerfile`), auto-deploy on `main`. |
| **Supabase** | Managed PostgreSQL, region near Bengaluru. |
| **GitHub Actions** | CI: pyflakes lint + smoke tests on every push. |

## Dev tooling

- **Python 3.12**, **Node 18+**
- **pyflakes** for lint (CI gate)
- **PowerShell** scripts for one-off ops (`scripts/`)
- **Docker** for the backend's reproducible build
