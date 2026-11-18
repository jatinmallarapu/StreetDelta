"""Read recent Mapillary metadata through bounded grids and paginated requests."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

ENDPOINT = "https://graph.mapillary.com/images"
FIELDS = (
    "id,computed_geometry,geometry,compass_angle,computed_compass_angle,"
    "captured_at,camera_type,camera_parameters,sequence,thumb_2048_url"
)


def grid(bounds, step=0.005):
    west, south, east, north = bounds
    if not 0 < step <= 0.005 or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Use a valid WGS84 bounding box and a grid step at most 0.005 degrees")
    columns = ceil((east - west) / step)
    rows = ceil((north - south) / step)
    if columns * rows > 2000:
        raise ValueError("Study area contains too many grid cells")
    for x in range(columns):
        for y in range(rows):
            yield (
                west + x * step,
                south + y * step,
                min(east, west + (x + 1) * step),
                min(north, south + (y + 1) * step),
            )


def fetch(client, bounds, earliest, *, step=0.005, max_pages=25):
    seen = set()
    for box in grid(bounds, step):
        parameters = {"bbox": ",".join(f"{x:.7f}" for x in box), "fields": FIELDS, "limit": "100"}
        for _ in range(max_pages):
            response = client.get(ENDPOINT, params=parameters)
            if response.is_error:
                raise RuntimeError(f"Mapillary request failed with HTTP {response.status_code}")
            document = response.json()
            for entry in document["data"]:
                ts = datetime.fromtimestamp(entry["captured_at"] / 1000, UTC)
                geometry = entry.get("computed_geometry") or entry.get("geometry")
                heading = entry.get("computed_compass_angle")
                if heading is None:
                    heading = entry.get("compass_angle")
                if ts < earliest or not geometry or entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                yield {
                    "image_id": entry["id"],
                    "captured_at": ts.isoformat(),
                    "coordinates": geometry["coordinates"],
                    "heading": heading,
                    "camera_type": entry.get("camera_type", "unknown"),
                    "camera_parameters": entry.get("camera_parameters"),
                    "sequence": entry.get("sequence"),
                    "image_url": entry.get("thumb_2048_url"),
                }
            next_page = document.get("paging", {}).get("next")
            if not next_page:
                break
            url = urlsplit(next_page)
            if (
                url.scheme != "https"
                or url.netloc != "graph.mapillary.com"
                or url.path != "/images"
            ):
                raise ValueError("Mapillary returned an unexpected pagination origin")
            # Preserve cursor parameters but send credentials only via the fixed client's header.
            cursor = dict(parse_qsl(url.query))
            parameters = {
                **parameters,
                **{k: cursor[k] for k in ("after", "before") if k in cursor},
            }
            if not {"after", "before"} & cursor.keys():
                raise ValueError("Mapillary pagination did not provide a supported cursor")
        else:
            raise RuntimeError("Page cap reached. Narrow the study area or adjust the date filter.")


def main():
    import pyarrow as pa
    import pyarrow.parquet as pq

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/chicago.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--since", type=datetime.fromisoformat)
    args = parser.parse_args()
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        parser.error("Set MAPILLARY_TOKEN in the environment")
    earliest = args.since or datetime.now(UTC) - timedelta(days=1095)
    if earliest.tzinfo is None:
        parser.error("--since must include a UTC offset")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    with httpx.Client(
        headers={"Authorization": f"OAuth {token}"}, timeout=30, follow_redirects=False
    ) as client:
        rows = list(fetch(client, config["bbox"], earliest, step=config["grid_degrees"]))
    if args.out.exists():
        rows = list(
            {row["image_id"]: row for row in [*pq.read_table(args.out).to_pylist(), *rows]}.values()
        )
    if not rows:
        raise SystemExit("No matching imagery metadata returned")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temp = args.out.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temp)
    temp.replace(args.out)
    print(f"Saved metadata for {len(rows)} unique images")


if __name__ == "__main__":
    main()
