"""
Verify store + area search accuracy against the running backend.

Usage:
    python scripts/verify_search.py [--base http://127.0.0.1:8000]

Checks:
  1. Area filter — every area returned by /api/stores/areas appears in at
     least one store result, and every returned store belongs to that area.
  2. Name search — sample of store names; each must surface in /api/stores?q=.
  3. Locality search — sample of locality_raw values; each must surface in results.

Prints a summary table. Exits 0 if all pass, 1 if any fail.
"""

import sys
import argparse
import urllib.request
import urllib.parse
import json

def get(base, path):
    url = f"{base}{path}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def check_areas(base):
    areas = get(base, "/api/stores/areas")
    results = []
    for area in areas:
        qs = urllib.parse.urlencode({"area": area})
        data = get(base, f"/api/stores?{qs}")
        stores = data.get("stores", [])
        wrong = [s["name"] for s in stores if s.get("area") != area]
        results.append({
            "check": f"area={area!r}",
            "count": len(stores),
            "pass": len(stores) > 0 and not wrong,
            "note": f"wrong area: {wrong[:3]}" if wrong else ("no results" if not stores else ""),
        })
    return results

def check_name_search(base):
    # Grab all stores, pick a sample of names to query
    data = get(base, "/api/stores")
    all_stores = data.get("stores", [])
    sample = all_stores[:min(10, len(all_stores))]
    results = []
    for s in sample:
        name = s["name"]
        # Use first significant word (skip very short tokens)
        token = next((w for w in name.split() if len(w) >= 4), name.split()[0])
        qs = urllib.parse.urlencode({"q": token})
        hit = get(base, f"/api/stores?{qs}")
        ids = {r["id"] for r in hit.get("stores", [])}
        found = s["id"] in ids
        results.append({
            "check": f"q={token!r} → {name!r}",
            "count": hit.get("count", 0),
            "pass": found,
            "note": "" if found else "store NOT in results",
        })
    return results

def check_locality_search(base):
    data = get(base, "/api/stores")
    all_stores = data.get("stores", [])
    # Pick stores that have a locality_raw value
    with_locality = [s for s in all_stores if s.get("locality")][:8]
    results = []
    for s in with_locality:
        loc = s.get("locality", "")
        if not loc:
            continue
        token = loc.split()[0] if loc else ""
        qs = urllib.parse.urlencode({"q": token})
        hit = get(base, f"/api/stores?{qs}")
        ids = {r["id"] for r in hit.get("stores", [])}
        found = s["id"] in ids
        results.append({
            "check": f"q={token!r} (locality) → {s['name']!r}",
            "count": hit.get("count", 0),
            "pass": found,
            "note": "" if found else "store NOT in results",
        })
    return results

def print_table(rows):
    w = max(len(r["check"]) for r in rows) + 2
    print(f"{'CHECK':<{w}} {'COUNT':>6}  {'PASS':>5}  NOTE")
    print("-" * (w + 20))
    for r in rows:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{r['check']:<{w}} {r['count']:>6}  {status:>5}  {r['note']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"\n=== FirstFind search verification — {base} ===\n")

    all_results = []

    print("--- Area filter ---")
    area_rows = check_areas(base)
    print_table(area_rows)
    all_results.extend(area_rows)

    print("\n--- Name search ---")
    name_rows = check_name_search(base)
    print_table(name_rows)
    all_results.extend(name_rows)

    print("\n--- Locality search ---")
    loc_rows = check_locality_search(base)
    print_table(loc_rows)
    all_results.extend(loc_rows)

    failures = [r for r in all_results if not r["pass"]]
    print(f"\n{'All checks passed.' if not failures else f'{len(failures)} FAILURES — see FAIL rows above.'}")
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
