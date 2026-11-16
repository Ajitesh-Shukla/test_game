# osm2godot

Turns a real place into a 3D city you can open in **Godot 4**, using only free
OpenStreetMap data.

Given an address (or a latitude/longitude), it:

1. downloads the **buildings, roads, water and parks** around it from OpenStreetMap
2. turns building outlines into **3D buildings** of the right height, and roads into
   **flat road ribbons** of the right width
3. writes a **glTF** file for Godot, plus a **road graph** for traffic AI

## Run it

```bash
cd osm2godot
python3 -m pip install --user -r requirements.txt
python3 osm2godot.py --address "1920 Rock Street, Mountain View, CA" --radius 400 --out output/rock_street_mountain_view
```

| Option | Meaning |
|---|---|
| `--address "..."` | Place to centre on. Looked up with OpenStreetMap's Nominatim |
| `--lat 37.4131 --lon -122.0882` | Centre on exact coordinates instead |
| `--radius 400` | Half the width of the square area, in metres (400 → 800 × 800 m) |
| `--out folder` | Where to write the files |
| `--from-cache` | Rebuild from the saved `osm_raw.json` without downloading again |

Start with a radius of 300–600 m. Bigger areas work, but make bigger files.

## What you get

| File | What it is |
|---|---|
| `city.glb` | The 3D city: ground, parks/water, roads and buildings |
| `road_graph.json` | Drivable roads as a graph of intersections and segments |
| `metadata.json` | Centre point, area and the maths to convert lat/lon ↔ game metres |
| `osm_raw.json` | The raw OpenStreetMap download |
| `ATTRIBUTION.txt` | The credit the OpenStreetMap licence requires |

### Coordinates

- **1 unit = 1 metre.**
- In Godot, **+X is east, −Z is north, +Y is up**.
- The origin (0, 0, 0) is the address you gave.

### Inside `city.glb`

| Node | Contents |
|---|---|
| `Ground-col` | Flat ground covering the whole area |
| `Areas` | Parks / grass (green) and water (blue), just above the ground |
| `Roads` | Road ribbons: major, minor, service roads and footpaths each have their own material |
| `Buildings-col` | All buildings: walls in 6 colour variants and roofs |

The **`-col`** at the end of a node name tells Godot's importer to add **collision**
automatically, so cars and characters can stand on the ground and bump into buildings.

Every surface has UV coordinates, so you can swap the plain colours for real
textures later (e.g. CC0 facades from ambientCG or Poly Haven). On walls, 1 UV unit
is 3 m.

### Building heights

The script uses the first of these that OpenStreetMap has for a building:

1. its `height` tag
2. its number of floors (`building:levels` × 3.2 m)
3. a default for its type (house 6.5 m, garage 3 m, apartments 12 m, office 14 m, otherwise 7 m)

Parts of buildings that start above the ground (`min_height`) are handled too.

### `road_graph.json`

```json
{
  "nodes": [ {"id": 123, "x": -40.2, "z": 15.8, "lat": 37.41, "lon": -122.08, "degree": 3} ],
  "edges": [ {"from": 123, "to": 456, "highway": "residential", "name": "Rock Street",
              "oneway": false, "lanes": 2, "maxspeed_kmh": null, "length_m": 87.4,
              "points": [[-40.2, 15.8], [-12.0, 18.3], [20.1, 21.0]]} ]
}
```

- **Nodes** are intersections and dead ends. `x`/`z` are Godot coordinates in metres.
- **Edges** are the road pieces between them. `points` is the road's centre line as [x, z] pairs.
- A one-way edge only allows driving from `from` to `to`.
- Only roads for cars are included (no footpaths).

This is the input for traffic: cars pick an edge, follow its `points`, and choose
a new edge at each intersection.

## Open it in Godot 4

1. Create a new Godot 4 project, or use an existing one.
2. Copy `city.glb` into the project folder. Godot imports it automatically.
3. Double-click `city.glb` in the FileSystem panel, then **New Inherited Scene**,
   or drag it into a 3D scene.
4. Add a **DirectionalLight3D** (the sun) and a **WorldEnvironment**, then look around.
   The area is about 800 m across, so zoom out.

To use the road graph, copy `road_graph.json` into the project and read it with
`JSON.parse_string(FileAccess.get_file_as_string("res://road_graph.json"))`.

## Licence and credit

The map data is **© OpenStreetMap contributors**, under the
[Open Database License](https://www.openstreetmap.org/copyright). Any game you
make with it must show that credit, for example in the credits screen. The script
itself is yours to use however you like.

Please use the free servers politely: download an area once and use `--from-cache`
afterwards.
