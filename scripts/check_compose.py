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


if __name__ == "__main__":
    main()
