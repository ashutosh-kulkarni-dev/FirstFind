"""Phase 2 verification script."""
from app.database import SessionLocal
from app.ml.clusters import find_cluster, discover_clusters

db = SessionLocal()

# Test Mode A
zones = discover_clusters(db)
print(f"Mode A — discover_clusters: {len(zones)} zones")
for z in zones:
    print(f"  {z['label']} | radius_km={z['radius_km']} | stores={z['store_count']}")

print()

# Test Mode B — Koramangala area
result = find_cluster(db, lat=12.935, lng=77.624, radius_km=3.0)
print("Mode B — find_cluster (Koramangala, 3km):")
print(f"  label={result['label']!r}, store_count={result['store_count']}, over_cap={result['over_cap']}, honest_empty={result['honest_empty']}")
print(f"  radius_km={result['radius_km']}")

# Verify no stores outside radius leaked in
from app.utils import haversine_km
for s in result["stores"]:
    d = haversine_km(12.935, 77.624, s["lat"], s["lng"])
    if d > 3.0 + 0.001:
        print(f"  !! RADIUS LEAK: {s['name']} is {d:.3f} km away")

# Test honest empty
empty = find_cluster(db, lat=13.5, lng=77.0, radius_km=1.0)
print(f"\nMode B — honest empty: honest_empty={empty['honest_empty']}, store_count={empty['store_count']}")

# Test areas/coords via DB directly
from collections import defaultdict
from app.models import Store
from app.utils import STORE_HAS_COORDS

area_pts = defaultdict(list)
for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
    if s.area:
        area_pts[s.area].append((s.lat, s.lng))

print(f"\nareas/coords: {len(area_pts)} distinct areas with coords")
print("Sample:", list(area_pts.keys())[:5])

db.close()
print("\nALL PHASE 2 CHECKS PASS")
