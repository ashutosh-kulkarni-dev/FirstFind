"""Phase 4 verification: split_cluster invariants."""
from app.database import SessionLocal
from app.models import Store
from app.utils import STORE_HAS_COORDS, haversine_km
from app.ml.clusters import split_cluster

db = SessionLocal()

# Grab all stores within 5km of Koramangala — likely over_cap
lat, lng, radius = 12.935, 77.624, 5.0
stores_in = [
    s for s in db.query(Store).filter(*STORE_HAS_COORDS).all()
    if haversine_km(lat, lng, s.lat, s.lng) <= radius
]
print(f"Stores in {radius}km of Koramangala: {len(stores_in)}")

sub_zones = split_cluster(stores_in, lat, lng, max_shops=8)
print(f"Sub-zones produced: {len(sub_zones)}")

# Invariant 1: union of sub-zone store_ids == stores_in (no store dropped)
input_ids = {s.id for s in stores_in}
output_ids = {s["id"] for sz in sub_zones for s in sz["stores"]}
dropped = input_ids - output_ids
extra = output_ids - input_ids
print(f"Dropped stores: {len(dropped)} (expected 0)")
print(f"Extra stores: {len(extra)} (expected 0)")

# Invariant 2: each sub-zone <= max_shops (best effort)
over = [sz for sz in sub_zones if sz["store_count"] > 8]
print(f"Sub-zones over cap: {len(over)} (ideally 0)")

# Summary
for i, sz in enumerate(sub_zones):
    print(f"  Sub-zone {i+1}: label={sz['label']!r}, stores={sz['store_count']}, radius_km={sz['radius_km']}")

all_pass = len(dropped) == 0 and len(extra) == 0
print("\nOverall:", "ALL PASS" if all_pass else "INVARIANT VIOLATION")
db.close()
