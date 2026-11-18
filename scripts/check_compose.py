"""Confirm the container stack serves real PostGIS state and writes an audit event."""

import subprocess
import time

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=5) as client:
        for _ in range(30):
            try:
                response = client.get("/health")
                response.raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(2)
        else:
            raise RuntimeError("StreetDelta did not become healthy")
        home = client.get("/")
        assert home.is_success and "Map change review" in home.text
        assert client.get("/static/review.js").is_success
        tile = client.get("/tiles/changes/0/0/0.pbf")
        assert tile.is_success and b"changes" in tile.content
        rows = client.get("/changes", params={"type": "changed"}).json()["features"]
        ident = rows[0]["properties"]["id"]
        saved = client.post(f"/changes/{ident}/review", json={"decision": "accept"})
        saved.raise_for_status()
        assert client.get(f"/features/{ident}").json()["review"] == "accept"
    output = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgis",
            "psql",
            "-U",
            "streetdelta",
            "-d",
            "streetdelta",
            "-tAc",
            "select count(*) from review_events where decision='accept'",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.stdout.strip() == "1"
    print("Dashboard, spatial queue, and persisted review verified")
    # Run inside the Compose network. The host never exposes the database port.
    subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-"],
        input="""
import os
import psycopg
from streetdelta.change import build_changes
from streetdelta.fixture import AS_OF, generate
from streetdelta.geo import TO_GPS, fuse
from streetdelta.store import PostGISStore

rays, baseline, _ = generate()
metadata = [
    {"image_id": ray.image_id, "captured_at": ray.captured_at, "camera_type": "perspective",
     "heading": ray.bearing, "coordinates": TO_GPS.transform(ray.east, ray.north)}
    for ray in rays
]
detections = [{"image_id": ray.image_id, "kind": ray.kind, "score": ray.score,
               "bbox": [0, 0, 100, 100]} for ray in rays]
observations = fuse(rays)
records = build_changes(rays, baseline, AS_OF, observations=observations)
for row in records:
    row["id"] = "integration-live-" + row["id"]
dsn = os.environ["DATABASE_URL"]
store = PostGISStore(dsn)
for _ in range(2):
    store.stage(metadata, detections, baseline, observations, records)
with psycopg.connect(dsn) as db:
    assert db.execute("select count(*) from images").fetchone()[0] == 240
    assert db.execute("select count(*) from detections").fetchone()[0] == 240
    assert db.execute("select count(*) from observed_features").fetchone()[0] == 60
stored = store.list(None, None, 0)
assert len(stored) == len(records)
assert all(row["id"].startswith("integration-live-") for row in stored)
print("Evidence staging is idempotent and synthetic candidates are isolated")
""",
        text=True,
        check=True,
    )


if __name__ == "__main__":
    main()
