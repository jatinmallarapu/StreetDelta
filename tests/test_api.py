"""Protect the boundary between synthetic map candidates and exportable edits."""

from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient

from streetdelta.api import app
from streetdelta.change import export_osc


def test_review_and_bounds(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STREETDELTA_MODE", "demo")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        result = client.get("/changes", params={"type": "changed"}).json()
        assert result["mode"] == "demo" and result["features"]
        ident = result["features"][0]["properties"]["id"]
        detail = client.get(f"/features/{ident}").json()
        assert detail["image_ids"] and detail["review"] == "pending"
        assert (
            client.post(f"/changes/{ident}/review", json={"decision": "accept"}).status_code == 200
        )
        assert client.get(f"/features/{ident}").json()["review"] == "accept"
        assert client.get("/changes", params={"bbox": "0,0,1,1"}).json()["features"] == []
        assert client.get("/changes", params={"bbox": "0,1,1,0"}).status_code == 422
        assert client.get("/changes/export.osc").status_code == 409


def test_only_accepted_node_proposals_export():
    row = {
        "review": "accept",
        "type": "new",
        "kind": "speed_limit",
        "value": 25,
        "coordinates": [-87.63, 41.88],
        "baseline": None,
    }
    xml = fromstring(export_osc([row, {**row, "type": "changed"}, {**row, "review": "pending"}]))
    [node] = list(xml.findall("create/node"))
    assert node.attrib["id"] == "-1"
    assert node.find("tag").attrib == {"k": "traffic_sign", "v": "US:R2-1-25"}
