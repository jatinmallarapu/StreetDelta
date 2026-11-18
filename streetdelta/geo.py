"""Compute compass bearings and robust ray intersections in Chicago's metric CRS."""

from dataclasses import dataclass
from math import atan, cos, degrees, radians, sin

import numpy as np
from pyproj import Transformer
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:26916", always_xy=True)
TO_GPS = Transformer.from_crs("EPSG:26916", "EPSG:4326", always_xy=True)


@dataclass(frozen=True)
class Ray:
    image_id: str
    kind: str
    east: float
    north: float
    bearing: float
    score: float
    captured_at: str
    value: int | None = None

    @property
    def origin(self):
        return np.array([self.east, self.north])

    @property
    def direction(self):
        angle = radians(self.bearing)
        return np.array([sin(angle), cos(angle)])


def bearing(heading, x, width, height, camera, focal=None, cx=None):
    if not all(np.isfinite([heading, x, width, height])) or width <= 0 or height <= 0:
        raise ValueError("Invalid camera measurements")
    if not 0 <= x <= width:
        raise ValueError("Detection center is outside the image")
    if camera == "spherical":
        return (heading + 360 * x / width - 180) % 360
    if camera != "perspective" or focal is None or not np.isfinite(focal) or focal <= 0:
        raise ValueError("Perspective images require calibrated focal length")
    center = width / 2 if cx is None else cx
    if not np.isfinite(center) or not 0 <= center <= width:
        raise ValueError("Principal point is outside the image")
    return (heading + degrees(atan((x - center) / (focal * max(width, height))))) % 360


def intersect(rays, angle_deg=12, max_range=90, max_residual=3):
    if len({ray.image_id for ray in rays}) < 2:
        return None
    origins = np.stack([ray.origin for ray in rays])
    directions = np.stack([ray.direction for ray in rays])
    angular = abs(directions @ directions.T)
    if angular.min() > cos(radians(angle_deg)):
        return None
    normals = np.column_stack((-directions[:, 1], directions[:, 0]))
    # Center UTM inputs before fitting to avoid subtracting large northings in the solver.
    center = origins.mean(axis=0)
    offsets = np.sum(normals * (origins - center), axis=1)
    point, _, rank, _ = np.linalg.lstsq(normals, offsets, rcond=None)
    if rank < 2:
        return None
    delta = point + center - origins
    distances = np.sum(delta * directions, axis=1)
    residual = float(np.sqrt(np.mean(np.sum(normals * delta, axis=1) ** 2)))
    if np.any(distances < 0) or np.any(distances > max_range) or residual > max_residual:
        return None
    return point + center, residual


def fuse(rays, proximity=40, cluster_radius=8):
    if not rays:
        return []
    # Each pair casts one hypothesis, with duplicates collapsed by contributing image ID.
    groups = {}
    origins = np.stack([ray.origin for ray in rays])
    neighbors = NearestNeighbors(radius=proximity, algorithm="kd_tree").fit(origins)
    nearby = neighbors.radius_neighbors(origins, return_distance=False)
    for i, left in enumerate(rays):
        for j in sorted(index for index in nearby[i] if index > i):
            right = rays[j]
            if (left.kind, left.value) != (right.kind, right.value):
                continue
            answer = intersect([left, right])
            if answer is not None:
                groups.setdefault((left.kind, left.value), []).append((answer[0], left, right))
    observations = []
    for kind, hypotheses in groups.items():
        labels = DBSCAN(eps=cluster_radius, min_samples=1).fit_predict([p[0] for p in hypotheses])
        for cluster in sorted(set(labels)):
            members = {}
            for label, (_, left, right) in zip(labels, hypotheses, strict=True):
                if label == cluster:
                    for ray in (left, right):
                        if ray.image_id not in members or ray.score > members[ray.image_id].score:
                            members[ray.image_id] = ray
            unique = list(members.values())
            result = intersect(unique)
            if result is not None:
                observations.append((kind, result[0], result[1], unique))
    return observations
