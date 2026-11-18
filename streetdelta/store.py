"""Keep the offline demo and PostgreSQL repository behind the same review contract."""

from threading import Lock

import psycopg
from psycopg.types.json import Jsonb


class MemoryStore:
    def __init__(self, records):
        self.records = {row["id"]: dict(row) for row in records}
        self.lock = Lock()

    def list(self, bounds, change_type, minimum):
        with self.lock:
            out = [
                dict(row)
                for row in self.records.values()
                if row["confidence"] >= minimum
                and (change_type is None or row["type"] == change_type)
                and (
                    bounds is None
                    or bounds[0] <= row["coordinates"][0] <= bounds[2]
                    and bounds[1] <= row["coordinates"][1] <= bounds[3]
                )
            ]
        return sorted(out, key=lambda row: (-row["confidence"], row["id"]))

    def get(self, ident):
        with self.lock:
            row = self.records.get(ident)
            return dict(row) if row else None

    def review(self, ident, decision):
        with self.lock:
            row = self.records.get(ident)
            if row is None:
                return None
            row["review"] = decision
            return dict(row)


class PostGISStore:
    def __init__(self, dsn, mode="live"):
        self.dsn = dsn
        self.mode = mode

    def seed(self, records):
        with psycopg.connect(self.dsn, connect_timeout=10) as db, db.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO map_change_candidates(id,change_type,kind,confidence,geom,payload)
                    VALUES (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)
                    ON CONFLICT (id) DO NOTHING""",
                [
                    (
                        row["id"],
                        row["type"],
                        row["kind"],
                        row["confidence"],
                        *row["coordinates"],
                        Jsonb({**row, "source_mode": self.mode}),
                    )
                    for row in records
                ],
            )

    def list(self, bounds, change_type, minimum):
        statement = """SELECT payload || jsonb_build_object('review',review)
                       FROM map_change_candidates WHERE confidence >= %s
                       AND payload->>'source_mode' = %s"""
        parameters = [minimum, self.mode]
        if change_type is not None:
            statement += " AND change_type = %s"
            parameters.append(change_type)
        if bounds is not None:
            statement += " AND ST_Intersects(geom, ST_MakeEnvelope(%s,%s,%s,%s,4326))"
            parameters.extend(bounds)
        with psycopg.connect(self.dsn, connect_timeout=10) as db:
            return [
                value
                for (value,) in db.execute(statement + " ORDER BY confidence DESC, id", parameters)
            ]

    def get(self, ident):
        with psycopg.connect(self.dsn, connect_timeout=10) as db:
            row = db.execute(
                """SELECT payload || jsonb_build_object('review',review)
                   FROM map_change_candidates WHERE id = %s AND payload->>'source_mode' = %s""",
                (ident, self.mode),
            ).fetchone()
        return row[0] if row else None

    def tile(self, zoom, x, y):
        # Use a WGS84 prefilter to let the geometry index prune each tile query.
        sql = """WITH bounds AS (SELECT ST_TileEnvelope(%s,%s,%s) AS geom),
        candidates AS (
            SELECT id, change_type, kind, confidence, review,
                   ST_AsMVTGeom(ST_Transform(c.geom,3857),bounds.geom,4096,0,true) AS geom
            FROM map_change_candidates c CROSS JOIN bounds
            WHERE c.payload->>'source_mode' = %s
              AND ST_Intersects(c.geom,ST_Transform(bounds.geom,4326))
        ) SELECT ST_AsMVT(candidates,'changes',4096,'geom') FROM candidates WHERE geom IS NOT NULL"""
        with psycopg.connect(self.dsn, connect_timeout=10) as db:
            return bytes(db.execute(sql, (zoom, x, y, self.mode)).fetchone()[0])

    def review(self, ident, decision):
        # A lock keeps audit events aligned with the decision readers see after commit.
        with psycopg.connect(self.dsn, connect_timeout=10) as db:
            row = db.execute(
                """SELECT payload,review FROM map_change_candidates
                   WHERE id = %s AND payload->>'source_mode' = %s FOR UPDATE""",
                (ident, self.mode),
            ).fetchone()
            if row is None:
                return None
            if row[1] != decision:
                db.execute(
                    "UPDATE map_change_candidates SET review=%s, updated_at=now() WHERE id=%s",
                    (decision, ident),
                )
                db.execute(
                    "INSERT INTO review_events(candidate_id,decision) VALUES (%s,%s)",
                    (ident, decision),
                )
            return {**row[0], "review": decision}
