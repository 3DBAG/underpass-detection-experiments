from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Iterable

import numpy as np


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


def _candidate_library_paths() -> list[Path]:
    if env_path := os.environ.get("ZIGPIP_LIB"):
        return [Path(env_path)]

    root = Path(__file__).resolve().parents[2]
    names = ["libzigpip.dylib", "libzigpip.so", "zigpip.dll"]
    return [root / "zig-out" / "lib" / name for name in names] + [root / "zig-out" / "bin" / name for name in names]


def _load_library() -> ctypes.CDLL:
    for path in _candidate_library_paths():
        if path.exists():
            return ctypes.CDLL(str(path))

    searched = "\n".join(str(path) for path in _candidate_library_paths())
    raise RuntimeError(
        "Could not find the zigpip shared library. Run `zig build` first or set ZIGPIP_LIB.\n"
        f"Searched:\n{searched}"
    )


_LIB = _load_library()
_LIB.zp_polygon_create.argtypes = [ctypes.POINTER(_Point), ctypes.c_size_t, ctypes.c_size_t]
_LIB.zp_polygon_create.restype = ctypes.c_void_p
_LIB.zp_polygon_destroy.argtypes = [ctypes.c_void_p]
_LIB.zp_polygon_destroy.restype = None
_LIB.zp_polygon_contains.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
_LIB.zp_polygon_contains.restype = ctypes.c_int
_LIB.zp_polygon_contains_many.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_uint8),
]
_LIB.zp_polygon_contains_many.restype = ctypes.c_int
_LIB.zp_polygon_contains_indexed.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_uint8),
]
_LIB.zp_polygon_contains_indexed.restype = ctypes.c_int


class PreparedRing:
    def __init__(self, coordinates: Iterable[tuple[float, float]] | np.ndarray, resolution: int = 64) -> None:
        points = np.asarray(list(coordinates) if not isinstance(coordinates, np.ndarray) else coordinates, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError("coordinates must be an Nx2 array-like")

        if len(points) >= 2 and np.allclose(points[0], points[-1]):
            points = points[:-1]

        if len(points) < 3:
            raise ValueError("a polygon ring needs at least 3 distinct vertices")

        self._points = np.ascontiguousarray(points, dtype=np.float64)
        self._handle = _LIB.zp_polygon_create(
            ctypes.cast(self._points.ctypes.data, ctypes.POINTER(_Point)),
            self._points.shape[0],
            int(resolution),
        )
        if not self._handle:
            raise RuntimeError("failed to create prepared polygon")

    def close(self) -> None:
        if self._handle:
            _LIB.zp_polygon_destroy(self._handle)
            self._handle = None

    def __del__(self) -> None:
        self.close()

    def contains_xy(self, x: float, y: float) -> bool:
        if not self._handle:
            raise RuntimeError("prepared polygon handle is closed")

        result = _LIB.zp_polygon_contains(self._handle, float(x), float(y))
        if result < 0:
            raise RuntimeError("point query failed")
        return bool(result)

    def contains_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        if not self._handle:
            raise RuntimeError("prepared polygon handle is closed")

        xs_array = np.ascontiguousarray(xs, dtype=np.float64)
        ys_array = np.ascontiguousarray(ys, dtype=np.float64)
        if xs_array.shape != ys_array.shape:
            raise ValueError("xs and ys must have the same shape")

        out = np.empty(xs_array.shape, dtype=np.bool_)
        status = _LIB.zp_polygon_contains_many(
            self._handle,
            xs_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ys_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            xs_array.size,
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        )
        if status != 0:
            raise RuntimeError("batch point query failed")

        return out

    def contains_indexed(self, xs: np.ndarray, ys: np.ndarray, indices: np.ndarray) -> np.ndarray:
        if not self._handle:
            raise RuntimeError("prepared polygon handle is closed")

        xs_array = np.ascontiguousarray(xs, dtype=np.float64)
        ys_array = np.ascontiguousarray(ys, dtype=np.float64)
        idx_array = np.ascontiguousarray(indices, dtype=np.uintp)
        if xs_array.shape != ys_array.shape:
            raise ValueError("xs and ys must have the same shape")

        out = np.empty(idx_array.shape, dtype=np.bool_)
        status = _LIB.zp_polygon_contains_indexed(
            self._handle,
            xs_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ys_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            idx_array.ctypes.data_as(ctypes.POINTER(ctypes.c_size_t)),
            idx_array.size,
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        )
        if status != 0:
            raise RuntimeError("indexed point query failed")

        return out
