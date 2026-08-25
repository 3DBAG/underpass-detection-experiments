"""Sample Mapterhorn Terrarium terrain pixels for RD New polygons."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import transform, unary_union
from shapely.prepared import prep


MAPTERHORN_TILE_URL_TEMPLATE = "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"
MAPTERHORN_ZOOM = 14
MAPTERHORN_TILE_SIZE = 512
MAPTERHORN_EFFECTIVE_RESOLUTION_M = 5.0
TERRAIN_PERCENTILE = 90.0
WEB_MERCATOR_HALF_WORLD_M = 20037508.342789244

_RD_TO_WEB_MERCATOR = Transformer.from_crs("EPSG:28992", "EPSG:3857", always_xy=True)


@dataclass(frozen=True)
class TerrainSample:
    elevation_m_nap: float
    pixel_count: int
    tile_count: int
    selection: str
    minimum_m_nap: float
    maximum_m_nap: float

    def metadata(self, zoom: int, percentile: float) -> dict[str, object]:
        return {
            "elevation_m_nap": self.elevation_m_nap,
            "vertical_datum": "NAP",
            "vertical_crs": "EPSG:5709",
            "source": "mapterhorn_ahn5_5m_filled",
            "effective_resolution_m": MAPTERHORN_EFFECTIVE_RESOLUTION_M,
            "tile_zoom": zoom,
            "percentile": percentile,
            "pixel_count": self.pixel_count,
            "tile_count": self.tile_count,
            "pixel_selection": self.selection,
            "minimum_m_nap": self.minimum_m_nap,
            "maximum_m_nap": self.maximum_m_nap,
        }


def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    """Decode a uint8 RGB array to elevation in metres."""
    rgb = np.asarray(rgb)
    if rgb.ndim < 1 or rgb.shape[-1] < 3:
        raise ValueError("Terrarium data must have at least three RGB channels")
    values = rgb[..., :3].astype(np.float64)
    return values[..., 0] * 256.0 + values[..., 1] + values[..., 2] / 256.0 - 32768.0


def _download_tile(url: str, timeout_s: float, attempts: int = 3) -> bytes:
    request = Request(url, headers={"User-Agent": "underpass-detection-experiments/1.0"})
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout_s) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
    raise RuntimeError(f"Could not download terrain tile {url}: {last_error}")


def _read_tile_bytes(
    z: int,
    x: int,
    y: int,
    url_template: str,
    cache_dir: str,
    timeout_s: float,
) -> bytes:
    cache_path = Path(cache_dir) / str(z) / str(x) / f"{y}.webp"
    try:
        cached = cache_path.read_bytes()
        if cached:
            return cached
    except FileNotFoundError:
        pass

    url = url_template.format(z=z, x=x, y=y)
    data = _download_tile(url, timeout_s)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_bytes(data)
        os.replace(temporary_path, cache_path)
    except OSError:
        # Another worker may have populated the shared cache concurrently. The
        # downloaded bytes are still valid for this request.
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
    return data


@lru_cache(maxsize=16)
def load_mapterhorn_tile(
    z: int,
    x: int,
    y: int,
    url_template: str,
    cache_dir: str,
    timeout_s: float,
) -> np.ndarray:
    data = _read_tile_bytes(z, x, y, url_template, cache_dir, timeout_s)
    try:
        with Image.open(BytesIO(data)) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except Exception as exc:
        raise RuntimeError(f"Could not decode Mapterhorn tile z={z} x={x} y={y}: {exc}") from exc
    expected_shape = (MAPTERHORN_TILE_SIZE, MAPTERHORN_TILE_SIZE, 3)
    if rgb.shape != expected_shape:
        raise RuntimeError(
            f"Unexpected Mapterhorn tile shape {rgb.shape}; expected {expected_shape}"
        )
    rgb.setflags(write=False)
    return rgb


def _global_pixel_scale(zoom: int) -> float:
    return (MAPTERHORN_TILE_SIZE * (2 ** zoom)) / (2.0 * WEB_MERCATOR_HALF_WORLD_M)


def _mercator_to_global_pixel(x_m: float, y_m: float, zoom: int) -> tuple[float, float]:
    scale = _global_pixel_scale(zoom)
    return (
        (x_m + WEB_MERCATOR_HALF_WORLD_M) * scale,
        (WEB_MERCATOR_HALF_WORLD_M - y_m) * scale,
    )


def _global_pixel_center_to_mercator(col: int, row: int, zoom: int) -> tuple[float, float]:
    scale = _global_pixel_scale(zoom)
    return (
        (col + 0.5) / scale - WEB_MERCATOR_HALF_WORLD_M,
        WEB_MERCATOR_HALF_WORLD_M - (row + 0.5) / scale,
    )


def _global_pixel_box(col: int, row: int, zoom: int):
    scale = _global_pixel_scale(zoom)
    left = col / scale - WEB_MERCATOR_HALF_WORLD_M
    right = (col + 1) / scale - WEB_MERCATOR_HALF_WORLD_M
    top = WEB_MERCATOR_HALF_WORLD_M - row / scale
    bottom = WEB_MERCATOR_HALF_WORLD_M - (row + 1) / scale
    return box(left, bottom, right, top)


def polygon_pixel_addresses(geometry_rd, zoom: int) -> tuple[list[tuple[int, int]], str]:
    """Return global XYZ pixel addresses selected by an EPSG:28992 polygon."""
    if geometry_rd is None or geometry_rd.is_empty:
        raise ValueError("Cannot sample terrain for an empty polygon")
    if zoom < 0:
        raise ValueError("Terrain zoom cannot be negative")

    geometry_mercator = transform(_RD_TO_WEB_MERCATOR.transform, unary_union([geometry_rd]))
    if geometry_mercator.is_empty:
        raise ValueError("Terrain polygon became empty after reprojection")

    min_x, min_y, max_x, max_y = geometry_mercator.bounds
    min_col_f, max_row_f = _mercator_to_global_pixel(min_x, min_y, zoom)
    max_col_f, min_row_f = _mercator_to_global_pixel(max_x, max_y, zoom)
    world_pixels = MAPTERHORN_TILE_SIZE * (2 ** zoom)
    min_col = max(0, int(np.floor(min_col_f)))
    max_col = min(world_pixels - 1, int(np.floor(max_col_f)))
    min_row = max(0, int(np.floor(min_row_f)))
    max_row = min(world_pixels - 1, int(np.floor(max_row_f)))
    if min_col > max_col or min_row > max_row:
        raise ValueError("Terrain polygon lies outside the Web Mercator tile pyramid")

    prepared = prep(geometry_mercator)
    selected: list[tuple[int, int]] = []
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            x_m, y_m = _global_pixel_center_to_mercator(col, row, zoom)
            if prepared.covers(Point(x_m, y_m)):
                selected.append((col, row))
    if selected:
        return selected, "pixel_centers"

    # Very narrow or small polygons may contain no pixel centre. Include every
    # intersecting pixel so that such an underpass still gets a terrain value.
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            if prepared.intersects(_global_pixel_box(col, row, zoom)):
                selected.append((col, row))
    if not selected:
        raise ValueError("No Mapterhorn terrain pixels intersect the underpass polygon")
    return selected, "all_touched_fallback"


def sample_polygon_terrain(
    geometry_rd,
    *,
    zoom: int = MAPTERHORN_ZOOM,
    percentile: float = TERRAIN_PERCENTILE,
    url_template: str = MAPTERHORN_TILE_URL_TEMPLATE,
    cache_dir: Path,
    timeout_s: float = 30.0,
) -> TerrainSample:
    if not np.isfinite(percentile) or not 0.0 <= percentile <= 100.0:
        raise ValueError("Terrain percentile must be between 0 and 100")
    if not np.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("Terrain request timeout must be positive")

    pixel_addresses, selection = polygon_pixel_addresses(geometry_rd, zoom)
    pixels_by_tile: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for col, row in pixel_addresses:
        tile_x, local_x = divmod(col, MAPTERHORN_TILE_SIZE)
        tile_y, local_y = divmod(row, MAPTERHORN_TILE_SIZE)
        pixels_by_tile[(tile_x, tile_y)].append((local_x, local_y))

    elevations: list[float] = []
    for (tile_x, tile_y), local_pixels in pixels_by_tile.items():
        rgb = load_mapterhorn_tile(
            zoom,
            tile_x,
            tile_y,
            url_template,
            str(cache_dir),
            float(timeout_s),
        )
        pixel_rgb = np.asarray([rgb[local_y, local_x] for local_x, local_y in local_pixels])
        decoded = decode_terrarium(pixel_rgb)
        elevations.extend(float(value) for value in decoded if np.isfinite(value) and value > -32768.0)

    if not elevations:
        raise ValueError("Mapterhorn returned no valid terrain elevations for the polygon")
    values = np.asarray(elevations, dtype=np.float64)
    return TerrainSample(
        elevation_m_nap=float(np.percentile(values, percentile)),
        pixel_count=int(values.size),
        tile_count=len(pixels_by_tile),
        selection=selection,
        minimum_m_nap=float(np.min(values)),
        maximum_m_nap=float(np.max(values)),
    )
