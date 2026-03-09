"""
Procedural background — value-noise lava-lamp animation.
"""

from __future__ import annotations

import math

import pygame

from .constants import _W, _H


# ---------------------------------------------------------------------------
# Utility: pulse factor in [0, 1] driven by elapsed time
# ---------------------------------------------------------------------------


def _pulse(t: float, speed: float = 2.5) -> float:
    """Return a value in [0.0, 1.0] that oscillates with the given speed (Hz)."""
    return (math.sin(t * speed * math.pi * 2) + 1) / 2


# ---------------------------------------------------------------------------
# Procedural background — value-noise lava-lamp
# ---------------------------------------------------------------------------

_BG_NOISE_PALETTE: list[tuple[int, int, int]] = [
    (10, 26, 18),  # 0.0 — Slate
    (19, 58, 42),  # 0.5 — Deep Teal
    (80, 200, 120),  # 1.0 — Emerald Green
]


def _noise_colour(v: float) -> tuple[int, int, int]:
    """Map noise value v ∈ [0,1] to an RGB colour via a two-segment gradient."""
    if v <= 0.5:
        t = v * 2.0
        a, b = _BG_NOISE_PALETTE[0], _BG_NOISE_PALETTE[1]
    else:
        t = (v - 0.5) * 2.0
        a, b = _BG_NOISE_PALETTE[1], _BG_NOISE_PALETTE[2]
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class ProceduralBackground:
    """
    Low-resolution value-noise background with an animated lava-lamp flow.

    A 128×128 tile is baked once at startup using an 8×8 control grid and
    bilinear + smoothstep interpolation.  Each frame a 64×64 window is sampled
    from that tile at an offset driven by math.sin / math.cos, then upscaled
    to fill the window.
    """

    _GRID = 8  # coarse control-grid resolution
    _TILE = 128  # baked tile size (must be ≥ 2 × SIZE)
    _SIZE = 64  # displayed sample window size

    def __init__(self, w: int, h: int, seed: int = 42) -> None:
        self._w, self._h = w, h
        self._tile = self._bake_tile(seed)

    def _bake_tile(self, seed: int) -> pygame.Surface:
        import random

        rng = random.Random(seed)
        G = self._GRID
        N = self._TILE
        # Control grid: (G+1)×(G+1) so tiling wraps cleanly
        grid = [[rng.random() for _ in range(G + 1)] for _ in range(G + 1)]
        surf = pygame.Surface((N, N))
        pa = pygame.PixelArray(surf)
        for py in range(N):
            for px in range(N):
                gx = (px / N) * G
                gy = (py / N) * G
                ix, iy = int(gx), int(gy)
                fx, fy = gx - ix, gy - iy
                # Smoothstep for smoother blobs
                sx = fx * fx * (3 - 2 * fx)
                sy = fy * fy * (3 - 2 * fy)
                v = (
                    grid[iy][ix] * (1 - sx) * (1 - sy)
                    + grid[iy][ix + 1] * sx * (1 - sy)
                    + grid[iy + 1][ix] * (1 - sx) * sy
                    + grid[iy + 1][ix + 1] * sx * sy
                )
                r, g, b = _noise_colour(v)
                pa[px][py] = surf.map_rgb(r, g, b)
        del pa
        return surf

    def draw(self, screen: pygame.Surface, t: float) -> None:
        amplitude = 28.0
        ox_f = (math.sin(t * 0.12) * amplitude) % self._SIZE
        oy_f = (math.cos(t * 0.08) * amplitude) % self._SIZE
        ox_i = int(ox_f)
        oy_i = int(oy_f)
        frac_x = ox_f - ox_i  # fractional tile-pixel remainder [0, 1)
        frac_y = oy_f - oy_i

        # Sample one extra pixel each way so the fractional shift has data to blend into.
        # ox_i max = SIZE-1, so ox_i + SIZE + 1 <= TILE is always safe.
        sample = self._tile.subsurface(pygame.Rect(ox_i, oy_i, self._SIZE + 1, self._SIZE + 1))

        # Upscale with one tile-pixel of headroom to absorb the fractional offset.
        px_w = self._w / self._SIZE  # screen pixels per tile pixel (≈18.75)
        px_h = self._h / self._SIZE  # screen pixels per tile pixel (≈12.5)
        bg = pygame.transform.smoothscale(
            sample, (int(self._w + px_w + 1), int(self._h + px_h + 1))
        )

        # Shift by the sub-pixel fraction: moves 1 screen-px at a time instead of 19.
        screen.blit(bg, (-int(frac_x * px_w), -int(frac_y * px_h)))
