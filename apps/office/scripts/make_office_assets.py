"""Generate placeholder pixel art + a Tiled map for the office. Stdlib only.

    python3 apps/office/scripts/make_office_assets.py

Writes into apps/office/public/assets/:
  office-tiles.png   16x16 tileset (floor, wall, desk, carpet, plant, door)
  character.png      16x16 frames: idle, walk-a, walk-b (tinted per employee in Phaser)
  office.tmj         Tiled JSON map: tile layers + "spots" object layer (desks, door, huddle)

The .tmj opens in the Tiled editor; edit the map there and keep this script for art only.
Replace the PNGs with real CC0 art later without touching game code.
"""

import json
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "public" / "assets"
T = 16  # tile size

# ---- tiny PNG writer -----------------------------------------------------------


def png(path: Path, width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def hexrgba(h: str) -> tuple[int, int, int, int]:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)


CLEAR = (0, 0, 0, 0)

# Each tile is 16 strings of 16 chars; the legend maps chars to colours.
LEGEND = {
    ".": CLEAR,
    "f": hexrgba("#c8a46e"),
    "F": hexrgba("#b48f5c"),
    "w": hexrgba("#5b6475"),
    "W": hexrgba("#454c5a"),
    "d": hexrgba("#8a5a3b"),
    "D": hexrgba("#6e4529"),
    "m": hexrgba("#2b2f3a"),
    "s": hexrgba("#7fd1ff"),
    "c": hexrgba("#6c8ebf"),
    "C": hexrgba("#5a79a6"),
    "g": hexrgba("#4caf50"),
    "G": hexrgba("#2e7d32"),
    "p": hexrgba("#a1663a"),
    "o": hexrgba("#3d2b1f"),
    "k": hexrgba("#1b1b1b"),
    "h": hexrgba("#f2d0a9"),
    "b": hexrgba("#ffffff"),
    "B": hexrgba("#d0d0d0"),
}

FLOOR = ["ffffffffFfffffff", "ffffffffFfffffff", "ffffffffFfffffff", "FFFFFFFFFFFFFFFF"] * 4
WALL = ["wwwwwwwwwwwwwwww"] * 12 + ["WWWWWWWWWWWWWWWW"] * 4
DESK = (
    ["ffffffffffffffff"] * 2
    + [
        "ffffmmmmmmmmffff",
        "ffffmssssssmffff",
        "ffffmssssssmffff",
        "ffffmmmmmmmmffff",
        "ffffffmmmmffffff",
    ]
    + ["dddddddddddddddd"] * 5
    + ["DDDDDDDDDDDDDDDD"] * 2
    + ["DffffffffffffffD", "DffffffffffffffD"]
)
CARPET = ["cccccccccccccccc", "cCcCcCcCcCcCcCcC"] * 8
PLANT = [
    "ffffffffffffffff",
    "ffffffgggfffffff",
    "fffffgGgggffffff",
    "ffffgggGgggfffff",
    "fffggGgggGggffff",
    "ffffgggGgggfffff",
    "fffffgggGgffffff",
    "ffffffgggfffffff",
    "ffffffpppfffffff",
    "fffffpppppffffff",
    "fffffpppppffffff",
    "fffffpppppffffff",
    "ffffffpppfffffff",
] + ["ffffffffffffffff"] * 3
DOOR = ["wwwoooooooooowww"] + ["wwwodddddddddowww"[:16]] * 13 + ["wwwoooooooooowww"] * 2
TILES = [FLOOR, WALL, DESK, CARPET, PLANT, DOOR]  # gids 1..6
GID = {name: i + 1 for i, name in enumerate(["floor", "wall", "desk", "carpet", "plant", "door"])}

# Character frames: white body (tinted per employee in Phaser), skin head, dark legs.
IDLE = [
    "................",
    ".....kkkkkk.....",
    "....khhhhhhk....",
    "....khkhhkhk....",
    "....khhhhhhk....",
    ".....khhhhk.....",
    "....kbbbbbbk....",
    "...kbbbbbbbbk...",
    "...kbBbbbbBbk...",
    "...kbBbbbbBbk...",
    "....kbbbbbbk....",
    "....kbbbbbbk....",
    ".....kkkkkk.....",
    ".....kk..kk.....",
    ".....kk..kk.....",
    "................",
]
WALK_A = [*IDLE[:13], ".....kk...kk....", "....kk.....kk...", "................"]
WALK_B = [*IDLE[:13], "....kk...kk.....", "...kk.....kk....", "................"]


def sheet(frames: list[list[str]]) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    width = T * len(frames)
    rows = [[LEGEND[frame[y][x]] for frame in frames for x in range(T)] for y in range(T)]
    return width, T, rows


# ---- Tiled map -------------------------------------------------------------------

COLS, ROWS = 30, 20


def office_map() -> dict[str, object]:
    floor = [GID["floor"]] * (COLS * ROWS)
    furniture = [0] * (COLS * ROWS)

    def put(layer: list[int], x: int, y: int, gid: int) -> None:
        layer[y * COLS + x] = gid

    for x in range(COLS):
        put(floor, x, 0, GID["wall"])
        put(floor, x, 1, GID["wall"])
        put(floor, x, ROWS - 1, GID["wall"])
    for y in range(ROWS):
        put(floor, 0, y, GID["wall"])
        put(floor, COLS - 1, y, GID["wall"])
    put(floor, 14, ROWS - 1, GID["door"])
    put(floor, 15, ROWS - 1, GID["door"])
    for x in range(10, 20):  # huddle carpet where the coordinator stands
        for y in range(8, 12):
            put(floor, x, y, GID["carpet"])
    for x, y in [(2, 2), (27, 2), (2, 17), (27, 17), (9, 9), (20, 9)]:
        put(furniture, x, y, GID["plant"])

    spots: list[dict[str, object]] = []
    desk_cells = [(x, y) for y in (4, 14) for x in range(3, 27, 3)]  # 16 desks, 2 rows
    for i, (x, y) in enumerate(desk_cells, start=1):
        put(furniture, x, y, GID["desk"])
        # The employee sits just below their desk.
        spots.append(point(f"desk-{i}", "desk", x * T + T / 2, (y + 1) * T + T / 2))
    spots.append(point("door", "door", 15 * T, (ROWS - 2) * T + T / 2))
    spots.append(point("huddle", "huddle", 15 * T, 10 * T))
    for i, spot in enumerate(spots, start=1):
        spot["id"] = i

    def tiles(name: str, data: list[int], layer_id: int) -> dict[str, object]:
        return {
            "id": layer_id,
            "name": name,
            "type": "tilelayer",
            "width": COLS,
            "height": ROWS,
            "x": 0,
            "y": 0,
            "opacity": 1,
            "visible": True,
            "data": data,
        }

    return {
        "type": "map",
        "version": "1.10",
        "tiledversion": "1.11.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "infinite": False,
        "width": COLS,
        "height": ROWS,
        "tilewidth": T,
        "tileheight": T,
        "nextlayerid": 4,
        "nextobjectid": len(spots) + 1,
        "layers": [
            tiles("floor", floor, 1),
            tiles("furniture", furniture, 2),
            {
                "id": 3,
                "name": "spots",
                "type": "objectgroup",
                "draworder": "topdown",
                "opacity": 1,
                "visible": True,
                "x": 0,
                "y": 0,
                "objects": spots,
            },
        ],
        "tilesets": [
            {
                "firstgid": 1,
                "name": "office-tiles",
                "image": "office-tiles.png",
                "imagewidth": T * len(TILES),
                "imageheight": T,
                "tilewidth": T,
                "tileheight": T,
                "tilecount": len(TILES),
                "columns": len(TILES),
                "margin": 0,
                "spacing": 0,
            }
        ],
    }


def point(name: str, kind: str, x: float, y: float) -> dict[str, object]:
    return {
        "id": 0,
        "name": name,
        "type": kind,
        "point": True,
        "x": x,
        "y": y,
        "width": 0,
        "height": 0,
        "rotation": 0,
        "visible": True,
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    png(OUT / "office-tiles.png", *sheet(TILES))
    png(OUT / "character.png", *sheet([IDLE, WALK_A, WALK_B]))
    (OUT / "office.tmj").write_text(json.dumps(office_map(), indent=1) + "\n")
    print(f"wrote {', '.join(p.name for p in sorted(OUT.iterdir()))}")
