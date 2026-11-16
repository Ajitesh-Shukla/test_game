#!/usr/bin/env python3
"""osm2godot: turn a real-world area from OpenStreetMap into a Godot-ready 3D city.

Downloads buildings, roads, water and green areas around an address (or a
lat/lon) and writes:

    city.glb          3D city: ground, green/water areas, road ribbons, buildings
    road_graph.json   drivable road network (intersections + road segments) for traffic AI
    metadata.json     centre point, projection and bounds, so you can convert lat/lon <-> metres
    osm_raw.json      the raw OpenStreetMap download (re-run offline with --from-cache)
    ATTRIBUTION.txt   the credit line the OpenStreetMap licence (ODbL) requires

Coordinates: 1 unit = 1 metre. Godot axes: +X = east, -Z = north, +Y = up,
origin = the centre point.

Usage:
    python osm2godot.py --address "1920 Rock Street, Mountain View, CA" --radius 400 --out output/rock_st
    python osm2godot.py --lat 37.4131 --lon -122.0882 --radius 400 --out output/rock_st
"""
import argparse
import hashlib
import json
import math
import os
import struct
import sys
import time
import urllib.parse
import urllib.request

import mapbox_earcut
import numpy as np

USER_AGENT = "osm2godot-city-builder/0.1 (personal game project)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Public Overpass servers, tried in order (the main one is sometimes busy or blocks cloud IPs)
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
EARTH_R = 6378137.0

# Road widths (metres) and drawing order (higher draws on top)
ROAD_STYLE = {
    "motorway": (14.0, "road_major"), "trunk": (12.0, "road_major"),
    "primary": (11.0, "road_major"), "secondary": (10.0, "road_major"),
    "tertiary": (9.0, "road_major"),
    "motorway_link": (7.0, "road_major"), "trunk_link": (7.0, "road_major"),
    "primary_link": (7.0, "road_major"), "secondary_link": (7.0, "road_major"),
    "tertiary_link": (7.0, "road_major"),
    "residential": (7.0, "road_minor"), "unclassified": (7.0, "road_minor"),
    "living_street": (6.0, "road_minor"), "road": (6.0, "road_minor"),
    "service": (4.0, "road_service"),
    "footway": (2.0, "path"), "path": (2.0, "path"), "cycleway": (2.5, "path"),
    "pedestrian": (4.0, "path"), "steps": (2.0, "path"), "track": (3.0, "path"),
    "bridleway": (2.0, "path"),
}
ROAD_LAYER_HEIGHT = {"road_service": 0.04, "road_minor": 0.05, "road_major": 0.06, "path": 0.03}
DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
            "residential", "living_street", "service", "road", "motorway_link",
            "trunk_link", "primary_link", "secondary_link", "tertiary_link"}

# Default building heights when OSM has no height / levels tag
DEFAULT_HEIGHT = {
    "house": 6.5, "detached": 6.5, "semidetached_house": 6.5, "residential": 7.0,
    "apartments": 12.0, "terrace": 8.0, "garage": 3.0, "garages": 3.0, "shed": 2.5,
    "carport": 2.6, "roof": 4.0, "commercial": 10.0, "office": 14.0, "retail": 6.0,
    "industrial": 9.0, "warehouse": 9.0, "school": 8.0, "church": 12.0,
    "hospital": 15.0, "hotel": 15.0, "parking": 9.0,
}
LEVEL_HEIGHT = 3.2

MATERIALS = {  # name: (r, g, b, roughness)
    "ground": (0.42, 0.45, 0.38, 1.0),
    "grass": (0.36, 0.55, 0.30, 1.0),
    "water": (0.20, 0.42, 0.62, 0.15),
    "road_major": (0.20, 0.20, 0.22, 0.9),
    "road_minor": (0.27, 0.27, 0.29, 0.9),
    "road_service": (0.33, 0.33, 0.34, 0.9),
    "path": (0.62, 0.58, 0.52, 1.0),
    "roof": (0.30, 0.28, 0.29, 0.9),
    "wall_0": (0.86, 0.82, 0.74, 0.9),
    "wall_1": (0.78, 0.72, 0.64, 0.9),
    "wall_2": (0.90, 0.88, 0.85, 0.9),
    "wall_3": (0.70, 0.62, 0.55, 0.9),
    "wall_4": (0.74, 0.78, 0.82, 0.9),
    "wall_5": (0.82, 0.70, 0.58, 0.9),
}
WALL_VARIANTS = 6


# --------------------------------------------------------------- download ----
def http_get(url, data=None, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:  # network hiccups / Overpass "too busy"
            if attempt == retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  request failed ({e}); retrying in {wait}s")
            time.sleep(wait)


def geocode(address):
    q = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    res = json.loads(http_get(f"{NOMINATIM}?{q}"))
    if not res:
        sys.exit(f"Address not found: {address}")
    r = res[0]
    print(f"Found: {r['display_name']}")
    return float(r["lat"]), float(r["lon"])


def bbox_around(lat, lon, radius):
    dlat = math.degrees(radius / EARTH_R)
    dlon = math.degrees(radius / (EARTH_R * math.cos(math.radians(lat))))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def download_osm(bbox):
    s, w, n, e = bbox
    b = f"{s:.7f},{w:.7f},{n:.7f},{e:.7f}"
    query = f"""
[out:json][timeout:120];
(
  way["building"]({b});
  relation["building"]["type"="multipolygon"]({b});
  way["highway"]({b});
  way["natural"="water"]({b});
  relation["natural"="water"]({b});
  way["leisure"~"^(park|pitch|playground|garden|golf_course)$"]({b});
  way["landuse"~"^(grass|meadow|recreation_ground|forest|village_green|cemetery)$"]({b});
);
out geom;
"""
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for server in OVERPASS_SERVERS:
        try:
            print(f"  asking {server.split('/')[2]} ...")
            return json.loads(http_get(server, data=data, retries=2))
        except Exception as e:
            last = e
            print(f"  {server.split('/')[2]} failed: {e}")
    raise SystemExit(f"All Overpass servers failed (last error: {last})")


# ------------------------------------------------------------- projection ----
class Projection:
    """Local flat projection in metres around (lat0, lon0). Accurate to a few
    centimetres over a few kilometres, which is all a game needs."""

    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = math.radians(1) * EARTH_R * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * EARTH_R

    def to_en(self, lat, lon):
        """(east, north) in metres."""
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky


# --------------------------------------------------------------- geometry ----
def signed_area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return a / 2


def clean_ring(ring):
    """Drop the closing duplicate and consecutive duplicates."""
    out = []
    for p in ring:
        if not out or (abs(p[0] - out[-1][0]) > 1e-4 or abs(p[1] - out[-1][1]) > 1e-4):
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-4 and abs(out[0][1] - out[-1][1]) < 1e-4:
        out.pop()
    return out


def orient(ring, ccw):
    return ring if (signed_area(ring) > 0) == ccw else ring[::-1]


def triangulate(outer, holes=()):
    """Triangulate a polygon with holes. Returns triangles as index triples into
    the flattened vertex list [outer..., hole1..., ...], each CCW (facing up)."""
    verts = list(outer)
    ends = [len(verts)]
    for h in holes:
        verts.extend(h)
        ends.append(len(verts))
    arr = np.array(verts, dtype=np.float64).reshape(-1, 2)
    idx = mapbox_earcut.triangulate_float64(arr, np.array(ends, dtype=np.uint32))
    tris = []
    for i in range(0, len(idx), 3):
        a, b, c = int(idx[i]), int(idx[i + 1]), int(idx[i + 2])
        (x1, y1), (x2, y2), (x3, y3) = verts[a], verts[b], verts[c]
        if (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1) < 0:
            b, c = c, b
        tris.append((a, b, c))
    return verts, tris


def assemble_rings(member_ways):
    """Join relation member way pieces (lists of points) into closed rings."""
    pieces = [list(w) for w in member_ways if len(w) >= 2]
    rings = []
    while pieces:
        cur = pieces.pop(0)
        changed = True
        while changed and cur[0] != cur[-1]:
            changed = False
            for i, p in enumerate(pieces):
                if p[0] == cur[-1]:
                    cur += p[1:]
                elif p[-1] == cur[-1]:
                    cur += p[::-1][1:]
                elif p[-1] == cur[0]:
                    cur = p + cur[1:]
                elif p[0] == cur[0]:
                    cur = p[::-1] + cur[1:]
                else:
                    continue
                pieces.pop(i)
                changed = True
                break
        if len(cur) >= 4 and cur[0] == cur[-1]:
            rings.append(cur)
    return rings


def point_in_ring(pt, ring):
    x, y = pt
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def clip_polyline(pts, r):
    """Clip a polyline to the square [-r, r] x [-r, r].
    Returns a list of (points, start_cut, end_cut) pieces; *_cut is True where the
    piece was cut by the square's edge rather than ending at an original point."""
    def inside(p):
        return -r <= p[0] <= r and -r <= p[1] <= r

    def clip_seg(a, b):            # Liang-Barsky
        t0, t1 = 0.0, 1.0
        dx, dy = b[0] - a[0], b[1] - a[1]
        for p, q in ((-dx, a[0] + r), (dx, r - a[0]), (-dy, a[1] + r), (dy, r - a[1])):
            if p == 0:
                if q < 0:
                    return None
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
        if t0 > t1:
            return None
        return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy), t0 > 0, t1 < 1

    pieces, cur, cur_cut = [], None, False
    for i in range(len(pts) - 1):
        c = clip_seg(pts[i], pts[i + 1])
        if c is None:
            if cur:
                pieces.append((cur, cur_cut, True))
                cur = None
            continue
        a, b, a_cut, b_cut = c
        if cur is None:
            cur, cur_cut = [a], a_cut
        cur.append(b)
        if b_cut:
            pieces.append((cur, cur_cut, True))
            cur = None
    if cur:
        pieces.append((cur, cur_cut, False))
    return [pc for pc in pieces if len(pc[0]) >= 2 and math.dist(pc[0][0], pc[0][-1]) > 0.01]


def parse_length(value):
    """'12', '12 m', '40 ft', '12.5m' -> metres (or None)."""
    if not value:
        return None
    v = value.strip().lower().replace(",", ".")
    try:
        if v.endswith("ft") or v.endswith("'"):
            return float(v.rstrip("ft'").strip()) * 0.3048
        return float(v.rstrip("m").strip())
    except ValueError:
        return None


def building_height(tags):
    h = parse_length(tags.get("height"))
    if h is None:
        levels = parse_length(tags.get("building:levels"))
        if levels is not None:
            roof_levels = parse_length(tags.get("roof:levels")) or 0
            h = (levels + roof_levels) * LEVEL_HEIGHT + 1.0
    if h is None:
        h = DEFAULT_HEIGHT.get(tags.get("building"), 7.0)
    base = parse_length(tags.get("min_height"))
    if base is None:
        min_level = parse_length(tags.get("building:min_level"))
        base = min_level * LEVEL_HEIGHT if min_level else 0.0
    return max(base, 0.0), max(h, base + 1.0)


# -------------------------------------------------------------- mesh build ----
class MeshBuilder:
    """Collects triangles per material, flat-shaded, with UVs."""

    def __init__(self):
        self.parts = {}  # material -> dict(pos=[], nrm=[], uv=[])

    def _part(self, mat):
        return self.parts.setdefault(mat, {"pos": [], "nrm": [], "uv": []})

    def tri(self, mat, a, b, c, uva, uvb, uvc):
        p = self._part(mat)
        ax, ay, az = a
        bx, by, bz = b
        cx, cy, cz = c
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        if ln < 1e-9:
            return
        n = (nx / ln, ny / ln, nz / ln)
        p["pos"] += [a, b, c]
        p["nrm"] += [n, n, n]
        p["uv"] += [uva, uvb, uvc]

    def flat_polygon(self, mat, outer, holes, y, uv_scale=10.0):
        verts, tris = triangulate(outer, holes)
        for a, b, c in tris:
            pts = [verts[a], verts[b], verts[c]]
            p3 = [(e, y, -n) for e, n in pts]
            uvs = [(e / uv_scale, -n / uv_scale) for e, n in pts]
            self.tri(mat, *p3, *uvs)

    def walls(self, mat, ring, base, top):
        """ring is oriented so its outside is on the right (CCW outer, CW hole)."""
        dist = 0.0
        for i in range(len(ring)):
            (e1, n1), (e2, n2) = ring[i], ring[(i + 1) % len(ring)]
            seg = math.hypot(e2 - e1, n2 - n1)
            pb, qb = (e1, base, -n1), (e2, base, -n2)
            pt, qt = (e1, top, -n1), (e2, top, -n2)
            u0, u1 = dist / 3.0, (dist + seg) / 3.0
            v0, v1 = base / 3.0, top / 3.0
            self.tri(mat, pb, qb, qt, (u0, v0), (u1, v0), (u1, v1))
            self.tri(mat, pb, qt, pt, (u0, v0), (u1, v1), (u0, v1))
            dist += seg

    def ribbon(self, mat, pts, width, y):
        """Flat strip of the given width along a polyline (mitred joints)."""
        if len(pts) < 2:
            return
        half = width / 2
        left, right = [], []
        for i, (e, n) in enumerate(pts):
            if i == 0:
                de, dn = pts[1][0] - e, pts[1][1] - n
            elif i == len(pts) - 1:
                de, dn = e - pts[i - 1][0], n - pts[i - 1][1]
            else:
                d1 = (e - pts[i - 1][0], n - pts[i - 1][1])
                d2 = (pts[i + 1][0] - e, pts[i + 1][1] - n)
                l1, l2 = math.hypot(*d1) or 1, math.hypot(*d2) or 1
                de, dn = d1[0] / l1 + d2[0] / l2, d1[1] / l1 + d2[1] / l2
            ln = math.hypot(de, dn) or 1
            de, dn = de / ln, dn / ln
            ne, nn = -dn, de                       # left-hand normal
            scale = 1.0
            if 0 < i < len(pts) - 1:
                d1 = (e - pts[i - 1][0], n - pts[i - 1][1])
                l1 = math.hypot(*d1) or 1
                cos_half = ne * (-d1[1] / l1) + nn * (d1[0] / l1)
                scale = min(1.0 / max(cos_half, 0.25), 3.0)   # mitre, capped on sharp bends
            left.append((e + ne * half * scale, n + nn * half * scale))
            right.append((e - ne * half * scale, n - nn * half * scale))
        dist = 0.0
        for i in range(len(pts) - 1):
            seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            l0, l1 = left[i], left[i + 1]
            r0, r1 = right[i], right[i + 1]
            P = lambda q: (q[0], y, -q[1])
            v0, v1 = dist / width, (dist + seg) / width
            # winding chosen so the strip faces up
            self.tri(mat, P(r0), P(r1), P(l1), (1, v0), (1, v1), (0, v1))
            self.tri(mat, P(r0), P(l1), P(l0), (1, v0), (0, v1), (0, v0))
            dist += seg
        # round-ish end caps hide gaps where roads meet
        for (e, n) in (pts[0], pts[-1]):
            cap = [(e + math.cos(a) * half, n + math.sin(a) * half)
                   for a in [k * math.pi / 4 for k in range(8)]]
            for k in range(8):
                a, b = cap[k], cap[(k + 1) % 8]
                self.tri(mat, (e, y, -n), (a[0], y, -a[1]), (b[0], y, -b[1]),
                         (0.5, 0.5), (0.5, 0.5), (0.5, 0.5))


# --------------------------------------------------------------- glTF out ----
def write_glb(path, nodes, materials):
    """nodes: list of (node_name, MeshBuilder). Writes a binary glTF 2.0 file."""
    gltf = {"asset": {"version": "2.0", "generator": "osm2godot"},
            "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
            "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
    mat_index = {}
    for name, (r, g, b, rough) in materials.items():
        mat_index[name] = len(gltf["materials"])
        lin = [round(c ** 2.2, 4) for c in (r, g, b)]     # glTF colours are linear, ours are sRGB
        gltf["materials"].append({"name": name, "pbrMetallicRoughness": {
            "baseColorFactor": lin + [1.0], "metallicFactor": 0.0, "roughnessFactor": rough}})
    blob = bytearray()

    def add_view(data, target):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(data)
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(data),
                                    "target": target})
        return len(gltf["bufferViews"]) - 1

    def add_accessor(arr, kind, target, minmax=False):
        view = add_view(arr.tobytes(), target)
        acc = {"bufferView": view, "componentType": 5126 if arr.dtype == np.float32 else 5125,
               "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = arr.min(axis=0).tolist()
            acc["max"] = arr.max(axis=0).tolist()
        gltf["accessors"].append(acc)
        return len(gltf["accessors"]) - 1

    for node_name, builder in nodes:
        prims = []
        for mat, part in builder.parts.items():
            if not part["pos"]:
                continue
            pos = np.array(part["pos"], dtype=np.float32)
            nrm = np.array(part["nrm"], dtype=np.float32)
            uv = np.array(part["uv"], dtype=np.float32)
            idx = np.arange(len(pos), dtype=np.uint32)
            prims.append({"attributes": {
                "POSITION": add_accessor(pos, "VEC3", 34962, minmax=True),
                "NORMAL": add_accessor(nrm, "VEC3", 34962),
                "TEXCOORD_0": add_accessor(uv, "VEC2", 34962)},
                "indices": add_accessor(idx, "SCALAR", 34963),
                "material": mat_index[mat]})
        if not prims:
            continue
        gltf["meshes"].append({"name": node_name, "primitives": prims})
        gltf["nodes"].append({"name": node_name, "mesh": len(gltf["meshes"]) - 1})
        gltf["scenes"][0]["nodes"].append(len(gltf["nodes"]) - 1)

    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"].append({"byteLength": len(blob)})
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack("<II", len(blob), 0x004E4942))
        f.write(blob)


# ------------------------------------------------------------- road graph ----
def build_road_graph(ways, proj, radius):
    """Split drivable ways at shared nodes into a graph of intersections and segments."""
    usage = {}
    for w in ways:
        for nid in w["nodes"]:
            usage[nid] = usage.get(nid, 0) + 1
    coords = {}
    for w in ways:
        for nid, g in zip(w["nodes"], w["geometry"]):
            if g:
                coords[nid] = (g["lat"], g["lon"])

    nodes, edges = {}, []
    next_boundary = [-1]

    def graph_node(nid):
        if nid not in nodes:
            lat, lon = coords[nid]
            e, n = proj.to_en(lat, lon)
            nodes[nid] = {"id": nid, "x": round(e, 2), "z": round(-n, 2),
                          "lat": lat, "lon": lon, "degree": 0, "boundary": False}
        return nodes[nid]

    def boundary_node(x, z):
        """A node where a road leaves the map: a good spawn/despawn point for traffic."""
        nid = next_boundary[0]
        next_boundary[0] -= 1
        lat = proj.lat0 + (-z) / proj.ky
        lon = proj.lon0 + x / proj.kx
        nodes[nid] = {"id": nid, "x": round(x, 2), "z": round(z, 2), "lat": lat, "lon": lon,
                      "degree": 0, "boundary": True}
        return nodes[nid]

    for w in ways:
        t = w.get("tags", {})
        ids = [nid for nid in w["nodes"] if nid in coords]
        if len(ids) < 2:
            continue
        oneway_tag = t.get("oneway", "no")
        oneway = oneway_tag in ("yes", "true", "1", "-1") or t.get("junction") == "roundabout" \
            or t.get("highway") == "motorway"
        if oneway_tag == "-1":
            ids = ids[::-1]
        start = 0
        for i in range(1, len(ids)):
            if i == len(ids) - 1 or usage.get(ids[i], 0) > 1:
                seg = ids[start:i + 1]
                start = i
                full = []
                for nid in seg:
                    e, n = proj.to_en(*coords[nid])
                    full.append((e, -n))
                lanes = parse_length(t.get("lanes"))
                speed = parse_length((t.get("maxspeed") or "").replace("mph", "")) if t.get("maxspeed") else None
                if speed and "mph" in (t.get("maxspeed") or ""):
                    speed *= 1.609
                for piece, start_cut, end_cut in clip_polyline(full, radius):
                    a = boundary_node(*piece[0]) if start_cut else graph_node(seg[0])
                    b = boundary_node(*piece[-1]) if end_cut else graph_node(seg[-1])
                    a["degree"] += 1
                    b["degree"] += 1
                    pts = [[round(x, 2), round(z, 2)] for x, z in piece]
                    length = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
                    edges.append({
                        "from": a["id"], "to": b["id"], "way_id": w["id"],
                        "highway": t.get("highway"), "name": t.get("name", ""),
                        "oneway": oneway, "lanes": int(lanes) if lanes else (1 if oneway else 2),
                        "maxspeed_kmh": round(speed) if speed else None,
                        "length_m": round(length, 2), "points": pts})
    return {"coordinates": "Godot metres: x = east, z = south (-z = north), origin at centre",
            "note": "nodes with boundary=true are where a road leaves the map (negative ids)",
            "nodes": list(nodes.values()), "edges": edges}


# ------------------------------------------------------------------- main ----
def wall_material(osm_id):
    h = int(hashlib.md5(str(osm_id).encode()).hexdigest(), 16)
    return f"wall_{h % WALL_VARIANTS}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address", help="street address to centre on (looked up with Nominatim)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--radius", type=float, default=400, help="half-size of the square area, metres")
    ap.add_argument("--out", default="output/city", help="output folder")
    ap.add_argument("--from-cache", action="store_true", help="reuse osm_raw.json in --out")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    raw_path = os.path.join(args.out, "osm_raw.json")
    meta_path = os.path.join(args.out, "metadata.json")

    if args.from_cache:
        with open(meta_path) as f:
            meta = json.load(f)
        lat0, lon0, radius = meta["center"]["lat"], meta["center"]["lon"], meta["radius_m"]
        with open(raw_path) as f:
            osm = json.load(f)
    else:
        if args.lat is not None and args.lon is not None:
            lat0, lon0 = args.lat, args.lon
        elif args.address:
            lat0, lon0 = geocode(args.address)
        else:
            sys.exit("Give --address or --lat/--lon")
        radius = args.radius
        bbox = bbox_around(lat0, lon0, radius)
        print(f"Downloading OpenStreetMap data for {radius * 2:.0f} x {radius * 2:.0f} m "
              f"around {lat0:.6f}, {lon0:.6f} ...")
        osm = download_osm(bbox)
        with open(raw_path, "w") as f:
            json.dump(osm, f)
    proj = Projection(lat0, lon0)

    ground, areas, roads, buildings = MeshBuilder(), MeshBuilder(), MeshBuilder(), MeshBuilder()
    r = radius
    ground.flat_polygon("ground", [(-r, -r), (r, -r), (r, r), (-r, r)], [], 0.0, uv_scale=20)

    def ring_of(geometry):
        return clean_ring([proj.to_en(g["lat"], g["lon"]) for g in geometry if g])

    stats = {"buildings": 0, "roads": 0, "areas": 0, "skipped": 0}
    drivable_ways = []
    for el in osm.get("elements", []):
        t = el.get("tags", {})
        try:
            if el["type"] == "way" and "highway" in t and t.get("area") != "yes":
                style = ROAD_STYLE.get(t["highway"])
                pts = clean_ring([proj.to_en(g["lat"], g["lon"]) for g in el["geometry"] if g]) \
                    if el["geometry"][0] != el["geometry"][-1] else \
                    [proj.to_en(g["lat"], g["lon"]) for g in el["geometry"] if g]
                if style and len(pts) >= 2:
                    width, mat = style
                    lanes = parse_length(t.get("lanes"))
                    if lanes and mat != "path":
                        width = max(width, lanes * 3.4)
                    if t.get("tunnel") in ("yes", "building_passage"):
                        continue
                    for piece, _, _ in clip_polyline(pts, r):
                        roads.ribbon(mat, piece, width, ROAD_LAYER_HEIGHT[mat])
                    stats["roads"] += 1
                if t["highway"] in DRIVABLE:
                    drivable_ways.append(el)
                continue

            # polygons: buildings, water, green areas
            if el["type"] == "way":
                ring = ring_of(el["geometry"])
                if len(ring) < 3:
                    continue
                polys = [(orient(ring, True), [])]
            elif el["type"] == "relation":
                outers = assemble_rings([[(g["lat"], g["lon"]) for g in m["geometry"]]
                                         for m in el.get("members", [])
                                         if m.get("role") == "outer" and m.get("geometry")])
                inners = assemble_rings([[(g["lat"], g["lon"]) for g in m["geometry"]]
                                         for m in el.get("members", [])
                                         if m.get("role") == "inner" and m.get("geometry")])
                to_ring = lambda rr: clean_ring([proj.to_en(la, lo) for la, lo in rr])
                outer_rings = [orient(to_ring(o), True) for o in outers]
                inner_rings = [orient(to_ring(i), False) for i in inners]
                polys = [(o, [h for h in inner_rings if h and point_in_ring(h[0], o)])
                         for o in outer_rings if len(o) >= 3]
            else:
                continue

            polys = [(o, h) for o, h in polys
                     if abs(sum(p[0] for p in o) / len(o)) <= r and abs(sum(p[1] for p in o) / len(o)) <= r]
            if not polys:
                continue
            if "building" in t:
                if t.get("building") in ("no",) or t.get("location") == "underground":
                    continue
                base, top = building_height(t)
                wall = wall_material(el["id"])
                for outer, holes in polys:
                    buildings.walls(wall, outer, base, top)
                    for h in holes:
                        buildings.walls(wall, h, base, top)
                    buildings.flat_polygon("roof", outer, holes, top, uv_scale=5)
                    if base > 0:   # overhangs / bridges: close the bottom too
                        verts, tris = triangulate(outer, holes)
                        for a, b, c in tris:
                            pts = [verts[a], verts[c], verts[b]]  # reversed: faces down
                            buildings.tri("roof", *[(e, base, -n) for e, n in pts],
                                          (0, 0), (0, 0), (0, 0))
                stats["buildings"] += 1
            elif t.get("natural") == "water":
                for outer, holes in polys:
                    areas.flat_polygon("water", outer, holes, 0.02)
                stats["areas"] += 1
            else:
                for outer, holes in polys:
                    areas.flat_polygon("grass", outer, holes, 0.01)
                stats["areas"] += 1
        except Exception as ex:   # one broken shape shouldn't stop the whole city
            stats["skipped"] += 1
            print(f"  skipped {el['type']} {el.get('id')}: {ex}")

    # "-col" suffix: Godot's importer automatically adds static collision to these nodes.
    glb_path = os.path.join(args.out, "city.glb")
    write_glb(glb_path, [("Ground-col", ground), ("Areas", areas), ("Roads", roads),
                         ("Buildings-col", buildings)], MATERIALS)

    graph = build_road_graph(drivable_ways, proj, radius)
    with open(os.path.join(args.out, "road_graph.json"), "w") as f:
        json.dump(graph, f, indent=1)

    meta = {"center": {"lat": lat0, "lon": lon0}, "radius_m": radius,
            "bbox": dict(zip(("south", "west", "north", "east"), bbox_around(lat0, lon0, radius))),
            "projection": "local equirectangular around center; x = (lon - lon0) * metres_per_deg_lon, "
                          "z = -(lat - lat0) * metres_per_deg_lat",
            "metres_per_deg_lon": proj.kx, "metres_per_deg_lat": proj.ky,
            "axes": "Godot: +X east, -Z north, +Y up, 1 unit = 1 metre",
            "attribution": "Map data (c) OpenStreetMap contributors, ODbL",
            "stats": stats}
    if args.address:
        meta["address"] = args.address
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(args.out, "ATTRIBUTION.txt"), "w") as f:
        f.write("Map data (c) OpenStreetMap contributors.\n"
                "Available under the Open Database License (ODbL): https://www.openstreetmap.org/copyright\n"
                "The 3D city and road graph in this folder are derived from that data and must keep this credit.\n")

    print(f"Buildings: {stats['buildings']}   road ways: {stats['roads']}   areas: {stats['areas']}   "
          f"skipped: {stats['skipped']}")
    print(f"Road graph: {len(graph['nodes'])} intersections/ends, {len(graph['edges'])} segments")
    print(f"Wrote {glb_path} ({os.path.getsize(glb_path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
