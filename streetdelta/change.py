"""Rank spatial differences and export a conservative, human-reviewed OSM proposal."""

from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from math import exp, log
from xml.etree.ElementTree import Element, SubElement, tostring

import numpy as np

from .geo import TO_GPS, fuse


def confidence(rays, residual, as_of):
    # Bound repeated-view influence and shrink old or poorly aligned evidence toward the prior.
    odds = log(0.35 / 0.65)
    for ray in sorted(rays, key=lambda x: x.score, reverse=True)[:6]:
        p = min(0.95, max(0.50, ray.score))
        age = max(0.0, (as_of - datetime.fromisoformat(ray.captured_at)).days)
        quality = exp(-age / 730) * exp(-residual / 4) / 2
        odds += quality * log(p / (1 - p))
    return 1 / (1 + exp(-odds))


def feature_id(kind, value, point):
    return sha256(
        f"{kind}:{float(point[0]):.1f}:{float(point[1]):.1f}:{value}".encode()
    ).hexdigest()[:16]


def build_changes(rays, baseline, as_of, max_distance=15, *, observations=None):
    matched = set()
    proposals = []
    observations = fuse(rays) if observations is None else observations
    for (kind, value), point, residual, views in sorted(
        observations, key=lambda x: (-len(x[3]), x[2], x[1][0], x[1][1])
    ):
        eligible = []
        for record in baseline:
            if record["kind"] != kind or record["id"] in matched:
                continue
            distance = float(np.linalg.norm(point - [record["east"], record["north"]]))
            if distance <= max_distance:
                eligible.append((distance, record["id"], record))
        old = min(eligible)[2] if eligible else None
        if old:
            matched.add(old["id"])
            if value == old.get("value"):
                continue
        lon, lat = TO_GPS.transform(*point)
        ident = feature_id(kind, value, point)
        proposals.append(
            {
                "id": ident,
                "type": "changed" if old else "new",
                "kind": kind,
                "value": value,
                "mapped_value": old.get("value") if old else None,
                "confidence": confidence(views, residual, as_of),
                "coordinates": [lon, lat],
                "residual_m": residual,
                "n_views": len(views),
                "first_seen": min(x.captured_at for x in views),
                "last_seen": max(x.captured_at for x in views),
                "image_ids": sorted(x.image_id for x in views),
                "baseline": old,
                "review": "pending",
            }
        )
    return sorted(proposals, key=lambda row: (-row["confidence"], row["id"]))


def export_osc(candidates):
    root = Element("osmChange", version="0.6", generator="StreetDelta")
    sections = defaultdict(list)
    for item in candidates:
        if item["review"] != "accept" or item["type"] != "new" or item["baseline"]:
            continue
        if item["kind"] not in {"stop_sign", "speed_limit"}:
            continue
        if item["kind"] == "speed_limit" and item["value"] not in range(15, 56, 5):
            continue
        tag = "US:R1-1" if item["kind"] == "stop_sign" else f"US:R2-1-{item['value']}"
        sections["create"].append((item["coordinates"], tag))
    for action, nodes in sections.items():
        group = SubElement(root, action)
        for index, ((lon, lat), tag) in enumerate(nodes, start=1):
            node = SubElement(group, "node", id=str(-index), lon=f"{lon:.7f}", lat=f"{lat:.7f}")
            SubElement(node, "tag", k="traffic_sign", v=tag)
    return tostring(root, encoding="unicode")
