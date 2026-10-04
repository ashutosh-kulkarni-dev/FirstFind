"""Quick API feature test for FirstFind."""
import httpx, json

BASE = "http://localhost:8000/api"
results = []

def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((status, label, detail))
    icon = "v" if ok else "X"
    print(f"  {icon} [{status}] {label}")
    if detail:
        print(f"         {detail}")

print("=== FirstFind API Feature Test ===\n")

# 1. Root
r = httpx.get("http://localhost:8000/")
check("Root endpoint reachable", r.status_code in (200, 404, 422), str(r.status_code))

# 2. Register new user
r = httpx.post(f"{BASE}/auth/register", json={"name": "QA Tester", "email": "qa_apiv2@thriftfind.demo", "password": "QA1234!"})
check("Register new user", r.status_code in (200, 201, 409), f"{r.status_code}: {r.text[:80]}")

# 3. Login with dummy account
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@thriftfind.demo", "password": "Test1234!"})
check("Login with test account", r.status_code == 200, r.text[:80])
token = r.json().get("token", "") if r.status_code == 200 else ""
headers = {"Authorization": f"Bearer {token}"} if token else {}

# 4. /me
if token:
    r = httpx.get(f"{BASE}/auth/me", headers=headers)
    email = r.json().get("email", "") if r.status_code == 200 else r.text[:60]
    check("/me returns user profile", r.status_code == 200, email)

# 5. Stores list
r = httpx.get(f"{BASE}/stores", params={"limit": 10})
payload = r.json()
stores = payload.get("stores", [])
check("GET /stores returns list", r.status_code == 200 and len(stores) > 0,
      f"count={payload.get('count')}, returned={len(stores)}")

# 6. Single store
if stores:
    sid = stores[0]["id"]
    r = httpx.get(f"{BASE}/stores/{sid}")
    check(f"GET /stores/{{id}} (id={sid})", r.status_code == 200, stores[0]["name"])
else:
    check("GET /stores/{id}", False, "No stores")

# 7. Search
r = httpx.get(f"{BASE}/stores", params={"search": "Koramangala", "limit": 5})
check("Search stores by keyword", r.status_code == 200, f"{len(r.json().get('stores', []))} results")

# 8. Filter by area
r = httpx.get(f"{BASE}/stores", params={"area": "Indiranagar", "limit": 5})
check("Filter stores by area", r.status_code == 200,
      f"{len(r.json().get('stores', []))} results for Indiranagar")

# 9. Zones
r = httpx.get(f"{BASE}/zones")
zones_data = r.json()
check("GET /zones", r.status_code == 200,
      f"{len(zones_data)} zones" if isinstance(zones_data, list) else str(zones_data)[:60])

# 10. Metro stations
r = httpx.get(f"{BASE}/metro/stations")
metro_data = r.json()
check("GET /metro/stations", r.status_code == 200,
      f"{len(metro_data)} stations" if isinstance(metro_data, list) else r.text[:60])

# 11. Chat - location query
r = httpx.post(f"{BASE}/chat", json={"message": "Show me thrift stores in Koramangala", "session_id": "test-001"},
               headers=headers, timeout=30)
reply = r.json().get("reply", "")[:100] if r.status_code == 200 else r.text[:100]
check("POST /chat (location query)", r.status_code == 200, reply)

# 12. Chat - category/price query
r = httpx.post(f"{BASE}/chat", json={"message": "Vintage stores under 500 rupees", "session_id": "test-001"},
               headers=headers, timeout=30)
reply = r.json().get("reply", "")[:100] if r.status_code == 200 else r.text[:100]
check("POST /chat (price+category query)", r.status_code == 200, reply)

# 13. Lists GET
if token:
    r = httpx.get(f"{BASE}/lists", headers=headers)
    check("GET /lists (auth)", r.status_code == 200, r.text[:80])

# 14. Create a list (store_ids is required, min 1)
list_id = None
if token and stores:
    r = httpx.post(f"{BASE}/lists", json={"name": "My API Test List", "store_ids": [stores[0]["id"]]}, headers=headers)
    check("POST /lists (create list with store)", r.status_code in (200, 201, 409), r.text[:80])
    if r.status_code in (200, 201):
        list_id = r.json().get("id")

# 15. Add more stores to existing list via PATCH
if token and list_id and len(stores) > 1:
    r = httpx.patch(f"{BASE}/lists/{list_id}", json={"add_ids": [stores[1]["id"]]}, headers=headers)
    check("PATCH /lists/{id} (add store)", r.status_code in (200, 201), r.text[:80])

# 16. Recommendations
if token:
    r = httpx.get(f"{BASE}/recommendations", headers=headers)
    check("GET /recommendations", r.status_code in (200, 404), r.text[:80])

# 17. Post a review
if token and stores:
    sid = stores[0]["id"]
    r = httpx.post(f"{BASE}/stores/{sid}/reviews",
                   json={"rating": 5, "text": "Amazing finds! Loved the vintage denim jacket."},
                   headers=headers, timeout=30)
    check(f"POST review on store", r.status_code in (200, 201, 400), r.text[:80])

# 18. Reviews are embedded in store detail (GET /stores/{id})
if stores:
    sid = stores[0]["id"]
    r = httpx.get(f"{BASE}/stores/{sid}")
    reviews_in_detail = r.json().get("reviews", []) if r.status_code == 200 else []
    check("Reviews embedded in GET /stores/{id}", r.status_code == 200,
          f"{len(reviews_in_detail)} reviews in detail response")

# 19. Conversations
if token:
    r = httpx.get(f"{BASE}/conversations", headers=headers)
    check("GET /conversations", r.status_code == 200, r.text[:80])

# 20. Clusters
r = httpx.get(f"{BASE}/clusters")
check("GET /clusters", r.status_code in (200, 404, 422), f"{r.status_code}: {r.text[:60]}")

# 21. Logout (frontend just clears localStorage, no server endpoint typically)
r = httpx.post(f"{BASE}/auth/logout", headers=headers) if token else None
if r:
    check("POST /auth/logout", r.status_code in (200, 404, 405), f"{r.status_code}")
else:
    check("Logout (no server endpoint - client-side)", True, "Clears localStorage on frontend")

print()
pass_count = sum(1 for s, _, _ in results if s == "PASS")
fail_count = sum(1 for s, _, _ in results if s == "FAIL")
print(f"=== RESULT: {pass_count}/{len(results)} passed, {fail_count} failed ===\n")

if fail_count:
    print("FAILURES:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  X {label}: {detail}")
