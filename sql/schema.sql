-- Use WGS84 at the API boundary and UTM for indexed meter-distance joins.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS images (
    image_id text PRIMARY KEY,
    captured_at timestamptz NOT NULL,
    camera_type text NOT NULL,
    heading double precision,
    geom geometry(Point,4326) NOT NULL,
    metadata jsonb NOT NULL,
    content_sha256 text
);
CREATE INDEX IF NOT EXISTS images_geom_idx ON images USING gist(geom);
CREATE INDEX IF NOT EXISTS images_captured_idx ON images(captured_at);
CREATE TABLE IF NOT EXISTS detections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key text UNIQUE,
    image_id text NOT NULL REFERENCES images(image_id),
    kind text NOT NULL,
    score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
    bbox double precision[] NOT NULL CHECK (cardinality(bbox) = 4),
    mask_rle jsonb,
    ocr_value integer,
    ocr_confidence double precision,
    est_depth_m double precision
);
ALTER TABLE detections ADD COLUMN IF NOT EXISTS source_key text UNIQUE;
CREATE TABLE IF NOT EXISTS baseline_features (
    id text PRIMARY KEY,
    kind text NOT NULL,
    value integer,
    geom geometry(Point,26916) NOT NULL,
    source_tags jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS baseline_geom_idx ON baseline_features USING gist(geom);
CREATE TABLE IF NOT EXISTS road_centerlines (
    id text PRIMARY KEY,
    geom geometry(LineString,26916) NOT NULL
);
CREATE INDEX IF NOT EXISTS roads_geom_idx ON road_centerlines USING gist(geom);
CREATE TABLE IF NOT EXISTS observed_features (
    id text PRIMARY KEY,
    kind text NOT NULL,
    value integer,
    geom geometry(Point,26916) NOT NULL,
    evidence jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS observed_geom_idx ON observed_features USING gist(geom);
CREATE TABLE IF NOT EXISTS map_change_candidates (
    id text PRIMARY KEY,
    change_type text NOT NULL CHECK (change_type IN ('new','changed','removed')),
    kind text NOT NULL,
    confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    geom geometry(Point,4326) NOT NULL,
    payload jsonb NOT NULL,
    review text NOT NULL DEFAULT 'pending' CHECK (review IN ('pending','accept','reject')),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS candidates_geom_idx ON map_change_candidates USING gist(geom);
CREATE TABLE IF NOT EXISTS review_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id text NOT NULL REFERENCES map_change_candidates(id),
    decision text NOT NULL CHECK (decision IN ('accept','reject')),
    reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE VIEW nearby_osm_matches AS
SELECT observed.id AS observation_id, nearest.id AS baseline_id, nearest.distance_m
FROM observed_features observed
LEFT JOIN LATERAL (
    SELECT id, ST_Distance(observed.geom, geom) AS distance_m
    FROM baseline_features
    WHERE kind = observed.kind AND ST_DWithin(observed.geom, geom, 15)
    ORDER BY observed.geom <-> geom, id LIMIT 1
) nearest ON true;
CREATE OR REPLACE VIEW road_snaps AS
SELECT observed.id, road.id AS road_id, ST_ClosestPoint(road.geom, observed.geom) AS snapped
FROM observed_features observed
CROSS JOIN LATERAL (
    SELECT id, geom FROM road_centerlines
    WHERE ST_DWithin(observed.geom, geom, 30)
    ORDER BY observed.geom <-> geom, id LIMIT 1
) road;
CREATE OR REPLACE VIEW change_tiles AS
SELECT id, change_type, kind, confidence, review, geom FROM map_change_candidates;
