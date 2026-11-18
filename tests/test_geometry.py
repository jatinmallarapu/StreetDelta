"""Verify bearing conventions and reject geometrically uninformative evidence."""

import numpy as np
import pytest

from streetdelta.change import build_changes
from streetdelta.fixture import AS_OF, generate
from streetdelta.geo import Ray, bearing, fuse, intersect


def ray(name, east, north, heading):
    return Ray(name, "stop_sign", east, north, heading, 0.9, AS_OF.isoformat())


def test_camera_models_and_wrap():
    assert bearing(350, 1000, 2000, 1000, "perspective", 0.5) == 350
    assert bearing(350, 2000, 2000, 1000, "perspective", 0.5) == 35
    assert bearing(340, 1500, 2000, 1000, "spherical") == 70
    with pytest.raises(ValueError):
        bearing(0, 0, 2000, 1000, "perspective")


def test_intersection_is_forward_metric_and_from_distinct_images():
    first, second = ray("a", -10, -10, 45), ray("b", 10, -10, 315)
    point, error = intersect([first, second])
    assert np.allclose(point, [0, 0], atol=1e-8)
    assert error < 1e-8
    assert intersect([first, ray("a", 10, -10, 315)]) is None
    assert intersect([first, ray("b", 10, -10, 45)]) is None
    assert intersect([ray("a", -10, -10, 225), second]) is None


def test_fixture_recovers_objects_and_preserves_unchanged_baseline():
    rays, baseline, truth = generate()
    found = fuse(rays)
    assert len(found) == len(truth)
    assert all(len(views) == 4 for _, _, _, views in found)
    rows = build_changes(rays, baseline, AS_OF)
    assert {row["type"] for row in rows} == {"new", "changed"}
    assert all(
        row["value"] == 25 and row["mapped_value"] == 30 for row in rows if row["type"] == "changed"
    )
    assert [row["confidence"] for row in rows] == sorted(
        [row["confidence"] for row in rows], reverse=True
    )
