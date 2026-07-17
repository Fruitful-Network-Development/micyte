from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

HOPS_PREFIX = ("3", "76")
HOPS_PARTITION_SEGMENT_COUNT = 16
HOPS_BUCKET_COUNT = 100


def as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def normalize_ring_open(ring: Any) -> list[list[float]]:
    if not isinstance(ring, list):
        return []
    normalized = [
        [float(point[0]), float(point[1])]
        for point in ring
        if isinstance(point, list) and len(point) >= 2
    ]
    if not normalized:
        return []
    if normalized[0] == normalized[-1]:
        return normalized[:-1]
    return normalized


def normalize_ring_closed(ring: Any) -> list[list[float]]:
    if not isinstance(ring, list):
        raise ValueError("Expected ring coordinate list")
    normalized = [
        [float(point[0]), float(point[1])]
        for point in ring
        if isinstance(point, list) and len(point) >= 2
    ]
    if not normalized:
        raise ValueError("Expected at least one valid coordinate in ring")
    if normalized[0] != normalized[-1]:
        normalized.append(list(normalized[0]))
    return normalized


def reference_polygons_from_geojson(payload: dict[str, Any]) -> list[list[list[list[float]]]]:
    out: list[list[list[list[float]]]] = []
    payload_type = as_text(payload.get("type"))
    if payload_type == "FeatureCollection":
        features = [item for item in list(payload.get("features") or []) if isinstance(item, dict)]
    elif payload_type == "Feature":
        features = [payload]
    else:
        return out

    for feature in features:
        geometry = dict(feature.get("geometry") or {})
        geometry_type = as_text(geometry.get("type"))
        coordinates = geometry.get("coordinates")
        if geometry_type == "Polygon" and isinstance(coordinates, list):
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon" and isinstance(coordinates, list):
            polygons = list(coordinates)
        else:
            continue
        for polygon in polygons:
            if not isinstance(polygon, list):
                continue
            rings = [normalize_ring_open(ring) for ring in polygon]
            rings = [ring for ring in rings if ring]
            if rings:
                out.append(rings)
    return out


def encode_hops_coordinate(longitude: float, latitude: float) -> str:
    lon_min = -180.0
    lon_max = 180.0
    lat_min = -90.0
    lat_max = 90.0
    parts = [*HOPS_PREFIX]
    for index in range(HOPS_PARTITION_SEGMENT_COUNT):
        if index % 2 == 0:
            span = (lon_max - lon_min) / HOPS_BUCKET_COUNT
            bucket = math.floor((float(longitude) - lon_min) / span)
            bucket = max(0, min(HOPS_BUCKET_COUNT - 1, bucket))
            lon_min = lon_min + (span * bucket)
            lon_max = lon_min + span
        else:
            span = (lat_max - lat_min) / HOPS_BUCKET_COUNT
            bucket = math.floor((float(latitude) - lat_min) / span)
            bucket = max(0, min(HOPS_BUCKET_COUNT - 1, bucket))
            lat_min = lat_min + (span * bucket)
            lat_max = lat_min + span
        parts.append(str(bucket))
    return "-".join(parts)


__all__ = [
    "as_text",
    "encode_hops_coordinate",
    "normalize_ring_closed",
    "normalize_ring_open",
    "read_json",
    "reference_polygons_from_geojson",
    "sha256_file",
    "write_json",
]
