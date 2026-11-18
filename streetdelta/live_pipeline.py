"""Join calibrated metadata to detector records and stage candidates for human review."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .change import build_changes
from .geo import TO_UTM, Ray, bearing
from .store import PostGISStore


def as_rays(metadata, detections):
    images = {row["image_id"]: row for row in metadata}
    for row in detections:
        image = images.get(row["image_id"])
        if image is None or image["heading"] is None:
            continue
        camera = image["camera_type"]
        focal = (image.get("camera_parameters") or [None])[0]
        value = row.get("ocr_value")
        if row["kind"] == "speed_limit" and value not in range(15, 56, 5):
            continue
        try:
            direction = bearing(
                image["heading"],
                (row["bbox"][0] + row["bbox"][2]) / 2,
                row["width"],
                row["height"],
                camera,
                focal,
            )
        except ValueError:
            continue
        east, north = TO_UTM.transform(*image["coordinates"])
        yield Ray(
            row["image_id"],
            row["kind"],
            east,
            north,
            direction,
            row["score"],
            image["captured_at"],
            value,
        )


def main():
    import pyarrow.parquet as pq

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="Normalized UTM baseline JSON")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--write-postgis", action="store_true")
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    detections = [
        json.loads(line)
        for line in args.detections.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rays = list(as_rays(pq.read_table(args.images).to_pylist(), detections))
    if not rays:
        parser.error("No detections have usable camera calibration and labels")
    records = build_changes(rays, baseline, datetime.now(UTC))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    if args.write_postgis:
        PostGISStore(os.environ["DATABASE_URL"]).seed(records)
    print(f"Staged {len(records)} candidate edits from {len(rays)} usable rays")


if __name__ == "__main__":
    main()
