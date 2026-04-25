#!/usr/bin/env python3
"""
make_assets.py — generate icon.icns and dmg-background.png for the voxterm app.

No external dependencies — uses only Python stdlib + macOS built-ins:
  sips      (resize PNGs — ships with macOS)
  iconutil  (assemble .iconset → .icns — ships with Xcode CLT)

Run once before building the .app:
    python make_assets.py
"""

import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)

# ── Brand colours (match ui.py palette) ────────────────────────────────────
_BG     = (13,  10, 30)    # #0D0A1E — near-black with purple tint
_WHITE  = (255, 255, 255)
_ACCENT = (167, 139, 250)  # #A78BFA — violet (unused in current design, kept for future)

# ── Icon dimensions ─────────────────────────────────────────────────────────
ICON_SIZE = 512             # source PNG — sips scales to all required sizes

# ── DMG background dimensions ───────────────────────────────────────────────
DMG_W, DMG_H = 540, 380


# ---------------------------------------------------------------------------
# Minimal PNG encoder (stdlib only)
# ---------------------------------------------------------------------------

def _png_chunk(name: bytes, data: bytes) -> bytes:
    payload = name + data
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)


def write_png(path: Path, pixels: bytearray, width: int, height: int):
    """
    Write an RGB image (3 bytes/pixel, row-major) to a PNG file.
    Uses filter type 0 (None) — simple, zero extra dependencies.
    """
    assert len(pixels) == width * height * 3, "pixel buffer size mismatch"

    # Prepend a filter byte (0 = None) to every scanline
    row_bytes = width * 3
    raw = bytearray(height * (1 + row_bytes))
    for y in range(height):
        raw[y * (1 + row_bytes)] = 0  # filter type
        src = y * row_bytes
        raw[y * (1 + row_bytes) + 1 : (y + 1) * (1 + row_bytes)] = pixels[src : src + row_bytes]

    png  = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

def make_canvas(width: int, height: int, color: tuple[int, int, int]) -> bytearray:
    """Create a flat RGB pixel buffer filled with a solid colour."""
    r, g, b = color
    buf = bytearray(width * height * 3)
    for i in range(0, len(buf), 3):
        buf[i], buf[i + 1], buf[i + 2] = r, g, b
    return buf


def fill_rect(buf: bytearray, width: int, height: int,
              x0: int, y0: int, x1: int, y1: int,
              color: tuple[int, int, int]):
    """Fill an axis-aligned rectangle (x1, y1 exclusive)."""
    cr, cg, cb = color
    for y in range(max(0, y0), min(height, y1)):
        row = y * width * 3
        for x in range(max(0, x0), min(width, x1)):
            i = row + x * 3
            buf[i], buf[i + 1], buf[i + 2] = cr, cg, cb


def fill_circle(buf: bytearray, width: int, height: int,
                cx: int, cy: int, radius: int,
                color: tuple[int, int, int]):
    """Fill a solid circle using the midpoint criterion."""
    cr, cg, cb = color
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        y = cy + dy
        if not (0 <= y < height):
            continue
        chord = int((r2 - dy * dy) ** 0.5)
        row = y * width * 3
        for dx in range(-chord, chord + 1):
            x = cx + dx
            if 0 <= x < width:
                i = row + x * 3
                buf[i], buf[i + 1], buf[i + 2] = cr, cg, cb


def fill_rounded_rect(buf: bytearray, width: int, height: int,
                      x0: int, y0: int, x1: int, y1: int, radius: int,
                      color: tuple[int, int, int]):
    """
    Fill a rectangle with fully-rounded corners (stadium / pill shape when
    radius == half the shorter side).
    Implemented as: inner rect + 4 corner circles + 2 edge rects.
    """
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    # Centre band (full width)
    fill_rect(buf, width, height, x0, y0 + r, x1, y1 - r, color)
    # Top / bottom bands (trimmed width for the straight edges)
    fill_rect(buf, width, height, x0 + r, y0, x1 - r, y0 + r, color)
    fill_rect(buf, width, height, x0 + r, y1 - r, x1 - r, y1, color)
    # Corner circles
    fill_circle(buf, width, height, x0 + r, y0 + r, r, color)
    fill_circle(buf, width, height, x1 - r, y0 + r, r, color)
    fill_circle(buf, width, height, x0 + r, y1 - r, r, color)
    fill_circle(buf, width, height, x1 - r, y1 - r, r, color)


def draw_arc(buf: bytearray, width: int, height: int,
             cx: int, cy: int, radius: int, thickness: int,
             start_deg: float, end_deg: float,
             color: tuple[int, int, int]):
    """
    Draw a thick arc (annulus sector) using angular sweep.
    start_deg / end_deg are in degrees, measured counter-clockwise from right.
    Renders by testing every pixel in the bounding box.
    """
    import math
    cr, cg, cb = color
    r_outer2 = (radius + thickness // 2) ** 2
    r_inner2 = max(0, radius - thickness // 2) ** 2

    start_r = math.radians(start_deg)
    end_r   = math.radians(end_deg)

    bbox = radius + thickness // 2 + 1
    for dy in range(-bbox, bbox + 1):
        y = cy + dy
        if not (0 <= y < height):
            continue
        row = y * width * 3
        for dx in range(-bbox, bbox + 1):
            x = cx + dx
            if not (0 <= x < width):
                continue
            d2 = dx * dx + dy * dy
            if not (r_inner2 <= d2 <= r_outer2):
                continue
            angle = math.atan2(-dy, dx)  # atan2 in standard orientation
            if angle < 0:
                angle += 2 * math.pi
            if start_r <= angle <= end_r:
                i = row + x * 3
                buf[i], buf[i + 1], buf[i + 2] = cr, cg, cb


# ---------------------------------------------------------------------------
# Icon design — microphone on dark background
# ---------------------------------------------------------------------------

def make_icon(size: int = ICON_SIZE) -> bytearray:
    """
    Draw a white microphone on a dark purple background.

    Layout (all values proportional to `size`):
      • Mic capsule — pill-shaped rounded rect, upper-centre
      • Mic stand   — thin vertical stem below capsule
      • Mic arc     — open U-shaped stand at the bottom
      • Base line   — horizontal bar at the bottom of the arc
    """
    W = H = size
    buf = make_canvas(W, H, _BG)

    s = size / 512  # scale factor

    # ── Capsule ──────────────────────────────────────────────────────────
    cap_w  = int(130 * s)
    cap_h  = int(230 * s)
    cap_r  = cap_w // 2           # fully-rounded (pill shape)
    cap_cx = W // 2
    cap_cy = int(200 * s)         # vertical centre of capsule
    fill_rounded_rect(
        buf, W, H,
        cap_cx - cap_w // 2, cap_cy - cap_h // 2,
        cap_cx + cap_w // 2, cap_cy + cap_h // 2,
        cap_r, _WHITE,
    )

    # ── Stem ─────────────────────────────────────────────────────────────
    stem_w    = int(14 * s)
    stem_top  = cap_cy + cap_h // 2           # bottom of capsule
    stem_bot  = int(370 * s)
    fill_rect(
        buf, W, H,
        cap_cx - stem_w // 2, stem_top,
        cap_cx + stem_w // 2, stem_bot,
        _WHITE,
    )

    # ── Arc (open U stand) ───────────────────────────────────────────────
    arc_cx    = cap_cx
    arc_cy    = stem_top + int(10 * s)       # arc centre just below capsule bottom
    arc_r     = int(90 * s)
    arc_thick = int(14 * s)
    draw_arc(buf, W, H, arc_cx, arc_cy, arc_r, arc_thick, 180, 360, _WHITE)

    # ── Base bar ─────────────────────────────────────────────────────────
    base_y = arc_cy + arc_r
    base_w = arc_r * 2 + arc_thick
    base_h = arc_thick
    fill_rounded_rect(
        buf, W, H,
        arc_cx - base_w // 2, base_y,
        arc_cx + base_w // 2, base_y + base_h,
        base_h // 2, _WHITE,
    )

    return buf


# ---------------------------------------------------------------------------
# DMG background — two-tone dark design
# ---------------------------------------------------------------------------

def make_dmg_bg() -> bytearray:
    """
    Two-zone DMG background:
      Left  ~½  — very slightly lighter, where the .app icon sits
      Right ~½  — base dark, where the Applications alias sits
    Separated by a 1-pixel divider line.
    """
    buf = make_canvas(DMG_W, DMG_H, _BG)

    left_colour  = (min(255, _BG[0] + 10), min(255, _BG[1] + 8), min(255, _BG[2] + 18))
    div_colour   = (50, 42, 90)

    mid = DMG_W // 2
    fill_rect(buf, DMG_W, DMG_H, 0, 0, mid, DMG_H, left_colour)

    # 1-pixel vertical divider
    for y in range(DMG_H):
        i = (y * DMG_W + mid) * 3
        buf[i], buf[i + 1], buf[i + 2] = div_colour

    # Subtle top highlight strip on both sides
    highlight = (min(255, _BG[0] + 20), min(255, _BG[1] + 16), min(255, _BG[2] + 36))
    fill_rect(buf, DMG_W, DMG_H, 0, 0, DMG_W, 2, highlight)

    return buf


# ---------------------------------------------------------------------------
# .icns assembly via macOS iconutil
# ---------------------------------------------------------------------------

# All sizes required by macOS for a complete iconset.
# @2x variants are produced by doubling each size from the same source.
_ICONSET_SIZES = [16, 32, 128, 256, 512]


def build_icns(source_png: Path, output_icns: Path):
    """
    Resize source_png to every required size using sips, then call iconutil.
    Requires: sips and iconutil (both ship with macOS + Xcode CLT).
    """
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "voxterm.iconset"
        iconset.mkdir()

        for sz in _ICONSET_SIZES:
            for mult, suffix in [(1, ""), (2, "@2x")]:
                px = sz * mult
                out = iconset / f"icon_{sz}x{sz}{suffix}.png"
                subprocess.run(
                    ["sips", "-z", str(px), str(px), str(source_png), "--out", str(out)],
                    check=True,
                    capture_output=True,
                )

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(output_icns)],
            check=True,
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Generating VoxTerm assets...")

    # 1. Icon source PNG (full-size, before iconutil resizing)
    icon_src = ASSETS / "icon_source.png"
    print(f"  Drawing icon ({ICON_SIZE}×{ICON_SIZE} px)...", end=" ", flush=True)
    write_png(icon_src, make_icon(), ICON_SIZE, ICON_SIZE)
    print("done")

    # 2. Assemble .icns
    icns_out = ASSETS / "icon.icns"
    print(f"  Building {icns_out.name} via iconutil...", end=" ", flush=True)
    try:
        build_icns(icon_src, icns_out)
        print("done")
    except subprocess.CalledProcessError as exc:
        print(f"FAILED\n  {exc.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    # 3. DMG background
    dmg_out = ASSETS / "dmg-background.png"
    print(f"  Drawing DMG background ({DMG_W}×{DMG_H} px)...", end=" ", flush=True)
    write_png(dmg_out, make_dmg_bg(), DMG_W, DMG_H)
    print("done")

    print(f"\nAssets written to {ASSETS}/")
    for f in sorted(ASSETS.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
