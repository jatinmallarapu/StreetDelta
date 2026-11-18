"""Evaluate the full change pipeline on a known synthetic geometry fixture."""

import json

import numpy as np

from streetdelta.change import build_changes
from streetdelta.fixture import AS_OF, generate
from streetdelta.geo import TO_UTM, fuse


def main():
    rays, baseline, truth = generate()
    candidates = build_changes(rays, baseline, AS_OF)
    positions = fuse(rays)

    def closest(point, kind):
        return min(
            (float(np.linalg.norm(point - [row["east"], row["north"]])), row["type"])
            for row in truth
            if row["kind"] == kind
        )

    errors = [closest(point, kind[0])[0] for kind, point, _, _ in positions]
    flags = []
    for candidate in candidates:
        position = np.array(TO_UTM.transform(*candidate["coordinates"]))
        distance, kind = closest(position, candidate["kind"])
        flags.append(distance <= 8 and kind == candidate["type"])
    print(
        json.dumps(
            {
                "synthetic_objects": len(truth),
                "recovered": len(positions),
                "bearing_rays": len(rays),
                "median_m": float(np.median(errors)),
                "p90_m": float(np.percentile(errors, 90)),
                "candidate_count": len(candidates),
                "precision": sum(flags) / len(flags),
                "precision_at_25": sum(flags[:25]) / 25 if len(flags) >= 25 else None,
                "precision_at_50": sum(flags[:50]) / 50 if len(flags) >= 50 else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
