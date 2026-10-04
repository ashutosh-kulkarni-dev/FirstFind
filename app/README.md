# ThriftFind MVP

AI-powered thrift store discovery for Bengaluru. See `DESIGN.md` for architecture.

## Run it (Windows)

Prereqs: Python 3.10+ and Node 18+.

**Terminal 1 — backend (port 8000):**
```powershell
cd app\backend
pip install -r requirements.txt
python run.py
```
First startup auto-seeds the database from `..\..\data\stores.json` (48 real stores)
plus synthetic demo reviews/users, and trains the ML modules. Takes ~10s.

**Terminal 2 — frontend (port 5173):**
```powershell
cd app\frontend
npm install
npm run dev
```

Open http://localhost:5173

## Demo account
`priya@demo.thriftfind` / `demo1234` — a synthetic user with interaction history,
so recommendations are personalized. Or register your own account.

## Try in the chat
- "Show me thrift stores in Koramangala"
- "vintage stores under ₹500"
- "which stores are open right now?"
- "where are the budget thrift zones?"
- "what do people say about EcoDhaga?"
- "compare EcoDhaga and Love Me Twice"
- "best time to visit Love Me Twice?"

## Reset the database
Delete `app\backend\thriftfind.db` and restart the backend.
