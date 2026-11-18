"""Generate a repeatable, entirely synthetic Chicago geometry benchmark."""

import argparse
import json
from datetime import UTC, datetime
from math import atan2, degrees
from pathlib import Path

import numpy as np

from .change import build_changes
from .geo import TO_UTM, Ray

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def generate(seed=42):
    rng = np.random.default_rng(seed)
    origin = np.array(TO_UTM.transform(-87.638, 41.881))
    rays, baseline, truth = [], [], []
    for i in range(60):
        point = origin + np.array([95 * (i % 10), 85 * (i // 10)])
        kind = ("speed_limit", "stop_sign", "traffic_signal", "crosswalk")[i % 4]
        value = 25 if kind == "speed_limit" else None
        for view, offset in enumerate(([-12, -13], [11, -12], [10, 9], [-11, 10])):
            center = point + offset
            distance = point - center
            direction = degrees(atan2(*distance)) + rng.normal(0, 1.15)
            ray = Ray(
                f"synthetic-{i}-{view}",
                kind,
                *center,
                direction,
                float(rng.uniform(0.78, 0.96)),
                "2025-12-01T00:00:00+00:00",
                value,
            )
            rays.append(ray)
        if i % 3 != 0:
            old_value = 30 if kind == "speed_limit" else value
            baseline.append(
                {
                    "id": f"fixture-osm-{i}",
                    "kind": kind,
                    "value": old_value,
                    "east": float(point[0] + 2),
                    "north": float(point[1] - 1),
                }
            )
        truth.append(
            {
                "east": float(point[0]),
                "north": float(point[1]),
                "kind": kind,
                "type": "new" if i % 3 == 0 else ("changed" if value else "unchanged"),
            }
        )
    return rays, baseline, truth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rays, baseline, _ = generate()
    data = json.dumps(build_changes(rays, baseline, AS_OF), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
