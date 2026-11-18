"""Check tile bounds, URL constraints, and use of corrected Mapillary pose."""

from datetime import UTC, datetime

import httpx
import pytest

from streetdelta.mapillary import fetch, grid
from streetdelta.perception import speed_limit


def test_grid_does_not_extend_past_study_area():
    boxes = list(grid((0, 0, 0.009, 0.007)))
    assert len(boxes) == 4
    assert boxes[-1] == (0.005, 0.005, 0.009, 0.007)


def test_corrected_pose_and_offsite_pagination():
    row = {
        "id": "sample",
        "captured_at": 1764547200000,
        "computed_compass_angle": 0,
        "compass_angle": 90,
        "computed_geometry": {"coordinates": [-87.63, 41.88]},
        "geometry": {"coordinates": [-87.62, 41.89]},
    }

    def handler(request):
        assert request.url.host == "graph.mapillary.com"
        return httpx.Response(
            200,
            json={"data": [row], "paging": {"next": "https://example.invalid/images?after=test"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = fetch(client, (0, 0, 0.004, 0.004), datetime(2025, 1, 1, tzinfo=UTC))
        first = next(rows)
        assert first["heading"] == 0 and first["coordinates"] == [-87.63, 41.88]
        with pytest.raises(ValueError, match="pagination origin"):
            next(rows)


def test_ocr_rejects_ambiguous_or_out_of_scope_numbers():
    assert speed_limit("SPEED LIMIT 25") == 25
    assert speed_limit("25 30") is None
    assert speed_limit("125") is None
    assert speed_limit("60") is None
