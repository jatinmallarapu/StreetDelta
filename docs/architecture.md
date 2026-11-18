# StreetDelta architecture

| Boundary | Input | Output |
| --- | --- | --- |
| Mapillary ingestion | Study-area grid and a client token | Incremental metadata Parquet |
| Perception | Authorized local photos | Grounding DINO detections and normalized OCR fields |
| Geometry | Calibrated camera poses and detections | Unique-view clusters in UTM 16N |
| Reconciliation | Cluster positions and normalized map baseline | Ranked new and changed candidates |
| Review | Candidate evidence and a decision | Transactional PostGIS audit event or a local demo update |

## Confidence

Start with prior log odds of ln(0.35/0.65). For up to six distinct, highest-scoring images, add half the detector log odds, discounted by exp(-age_days/730) and exp(-fit_residual_m/4). Clip detector scores into [0.50, 0.95] before computing log odds. Apply the logistic function to the result.

This is a ranking heuristic. Calibration requires disjoint real labels, and nearby camera frames are correlated. The half-weight and view cap limit their influence. A residual measures geometric agreement and can remain small when headings are biased in the same direction.

## Decisions and limitations

- Bearings follow a compass convention. All geometry calculations happen in EPSG:26916 and the API reports longitude first.
- Two-view fits must have distinct images, enough angular separation, forward intersections and finite range. Near-parallel views are discarded. Dense corridors can still associate rays from different objects.
- Point inventories and road attributes are evaluated separately. A speed-limit sign does not identify the exact beginning and end of a road's restriction. Existing ways, nodes and relations require editor review with current versions and complete tags.
- A feature missing from an image is not a removal. That needs independent, dated coverage and explicit negative observations.
- Multipath and urban canyons can shift the entire reconstruction. Rare signs, occlusion, night imagery, sign duplication, lens distortion and panorama conventions need hand-labelled slices.
- The offline API and Compose demo are intended for a trusted local reviewer. Use an authenticated ingress and a restricted database role before sharing a real deployment.
