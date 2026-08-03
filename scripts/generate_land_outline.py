"""Generate `dashboard_hub/hub/src/components/land.json` — the globe's coastlines.

Natural Earth's 110m land layer, public domain, simplified down to something a
browser can re-project sixty times a second. The full layer is 5,143 points
across 128 rings; at the size the globe is drawn, most of that detail lands
inside a single pixel, so it is thinned with Ramer–Douglas–Peucker and the
smallest islands are dropped entirely.

    python -m scripts.generate_land_outline

Re-run it only to change the tolerance — the coastlines themselves are not
exactly breaking news.
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

SOURCE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
    "/master/geojson/ne_110m_land.geojson"
)

OUT_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "dashboard_hub"
    / "hub"
    / "src"
    / "components"
    / "land.json"
)

# Degrees. Roughly 55 km at the equator — below one pixel on a 700px globe, and
# the point that survives is always an original vertex, so coastlines keep their
# shape rather than being smoothed into blobs.
TOLERANCE = 0.5

# A ring whose bounding box is smaller than this is an island that would draw as
# a speck. Dropping them is most of the size saving.
MIN_EXTENT = 3.0

# Two decimals is about 1 km — far finer than the globe can show, and it halves
# the file against the raw four.
PRECISION = 2


def _perpendicular(point, start, end) -> float:
    """Distance from `point` to the segment `start`–`end`, in degrees."""
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5

    # Projection of the point onto the segment, clamped to its ends.
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def simplify(points: list, tolerance: float) -> list:
    """Ramer–Douglas–Peucker, iterative so a long coastline cannot blow the stack."""
    if len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue

        worst, index = 0.0, first
        for i in range(first + 1, last):
            distance = _perpendicular(points[i], points[first], points[last])
            if distance > worst:
                worst, index = distance, i

        if worst > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))

    return [point for point, kept in zip(points, keep, strict=True) if kept]


def _extent(ring: list) -> float:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return max(max(lons) - min(lons), max(lats) - min(lats))


def build() -> list[list[list[float]]]:
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "kubera-edw/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)

    rings: list[list[list[float]]] = []
    for feature in payload["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        for polygon in polygons:
            for ring in polygon:
                if len(ring) < 4 or _extent(ring) < MIN_EXTENT:
                    continue
                thinned = simplify([tuple(p) for p in ring], TOLERANCE)
                if len(thinned) < 4:
                    continue
                rings.append(
                    [[round(lon, PRECISION), round(lat, PRECISION)] for lon, lat in thinned]
                )

    # Biggest landmasses first: the globe draws in this order, so a continent is
    # never hidden under an island's stroke.
    rings.sort(key=lambda r: -_extent(r))
    return rings


def main() -> int:
    rings = build()
    points = sum(len(r) for r in rings)
    if len(rings) < 20 or points < 500:
        print(f"only {len(rings)} rings / {points} points — refusing to overwrite", file=sys.stderr)
        return 1

    OUT_PATH.write_text(json.dumps(rings, separators=(",", ":")) + "\n")
    size = OUT_PATH.stat().st_size
    print(f"wrote {len(rings)} rings, {points} points, {size / 1024:.0f} KB")
    print(f"  -> {OUT_PATH.relative_to(OUT_PATH.parents[5])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
