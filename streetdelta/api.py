"""Serve ranked map candidates and keep review actions explicit."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .change import build_changes, export_osc
from .fixture import AS_OF, generate
from .store import MemoryStore, PostGISStore

DASHBOARD = Path(
    os.getenv("STREETDELTA_DASHBOARD", str(Path(__file__).resolve().parent.parent / "dashboard"))
)


@asynccontextmanager
async def lifespan(app):
    dsn = os.getenv("DATABASE_URL")
    mode = os.getenv("STREETDELTA_MODE", "demo")
    if mode not in {"demo", "live"}:
        raise ValueError("STREETDELTA_MODE must be demo or live")
    if mode == "live" and not dsn:
        raise ValueError("Live mode needs PostGIS")
    records = []
    if mode == "demo":
        rays, baseline, _ = generate()
        records = build_changes(rays, baseline, AS_OF)
    app.state.mode = mode
    if dsn:
        store = PostGISStore(dsn, mode=mode)
        if records:
            store.seed(records)
        app.state.store = store
    else:
        app.state.store = MemoryStore(records)
    yield


app = FastAPI(title="StreetDelta", version="0.1.0", lifespan=lifespan)
if DASHBOARD.is_dir():
    app.mount("/static", StaticFiles(directory=DASHBOARD), name="dashboard")


class Decision(BaseModel):
    decision: Literal["accept", "reject"]


def bbox(value):
    if value is None:
        return None
    try:
        west, south, east, north = map(float, value.split(","))
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Use bbox=west,south,east,north with valid coordinates") from None
    return west, south, east, north


@app.get("/", include_in_schema=False)
def dashboard():
    if not DASHBOARD.is_dir():
        raise HTTPException(404, "Dashboard assets are not installed")
    return FileResponse(DASHBOARD / "index.html")


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "mode": request.app.state.mode}


@app.get("/changes")
def changes(
    request: Request,
    bounds: Annotated[str | None, Query(alias="bbox")] = None,
    change_type: Annotated[Literal["new", "changed", "removed"] | None, Query(alias="type")] = None,
    min_conf: Annotated[float, Query(ge=0, le=1)] = 0,
):
    rows = request.app.state.store.list(bbox(bounds), change_type, min_conf)
    return {
        "type": "FeatureCollection",
        "mode": request.app.state.mode,
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": row["coordinates"]},
                "properties": {
                    key: row[key]
                    for key in (
                        "id",
                        "type",
                        "kind",
                        "value",
                        "mapped_value",
                        "confidence",
                        "review",
                    )
                },
            }
            for row in rows
        ],
    }


@app.get("/features/{ident}")
def feature(ident: str, request: Request):
    row = request.app.state.store.get(ident)
    if row is None:
        raise HTTPException(404, "Candidate not found")
    return row


@app.post("/changes/{ident}/review")
def review(ident: str, decision: Decision, request: Request):
    row = request.app.state.store.review(ident, decision.decision)
    if row is None:
        raise HTTPException(404, "Candidate not found")
    return row


@app.get("/changes/export.osc")
def osc(request: Request):
    if request.app.state.mode == "demo":
        raise HTTPException(409, "Synthetic candidates cannot be exported as OSM edits")
    return Response(
        export_osc(request.app.state.store.list(None, None, 0)),
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=streetdelta.osc"},
    )


@app.get("/tiles/changes/{z}/{x}/{y}.pbf")
def tiles(z: int, x: int, y: int, request: Request):
    if not 0 <= z <= 20 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(422, "Invalid XYZ tile coordinate")
    store = request.app.state.store
    if not isinstance(store, PostGISStore):
        raise HTTPException(503, "Vector tiles require PostGIS")
    return Response(store.tile(z, x, y), media_type="application/vnd.mapbox-vector-tile")
