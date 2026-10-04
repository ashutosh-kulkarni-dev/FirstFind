import httpx, time

time.sleep(3)  # let uvicorn hot-reload

r = httpx.get("http://localhost:8000/api/stores/blr-0001")
data = r.json()
similar = data.get("similar", [])
print(f"similar count: {len(similar)}")
for s in similar:
    mp = s.get("match_pct", "MISSING")
    print(f"  {s['name']} ({s['area']}) -> match_pct={mp}")

all_have = all("match_pct" in s for s in similar)
print(f"\nAll similar stores have match_pct: {all_have}")
print("FIX VERIFIED" if all_have and similar else "FIX FAILED")
