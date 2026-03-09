"""
Card physics and bezier flight animations.
"""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from twentyfive.cards.card import Card, Suit


# ---------------------------------------------------------------------------
# Floating card physics — per-slot bob + mouse-reactive tilt
# ---------------------------------------------------------------------------


class FloatingCard:
    """Per-card animated display state: sine-wave bobbing + mouse-reactive tilt with lerp."""

    BOB_SPEED = 0.003  # radians per millisecond
    LERP = 0.12  # smoothing factor per frame

    def __init__(self, slot_idx: int) -> None:
        self._phase = slot_idx * 0.8  # stagger so cards don't sync
        self._bob_y: float = 0.0
        self.scale: float = 1.0
        self.rotation: float = 0.0
        self._target_scale: float = 1.0
        self._target_rot: float = 0.0

    def update(
        self,
        ticks_ms: int,
        mouse: tuple[int, int],
        rect: pygame.Rect,
        hovering: bool,
    ) -> None:
        t = ticks_ms * self.BOB_SPEED
        self._bob_y = math.sin(t + self._phase) * 5.0
        if hovering:
            self._target_scale = 1.10
            dx = mouse[0] - rect.centerx
            self._target_rot = max(-15.0, min(15.0, dx * 0.05))
        else:
            self._target_scale = 1.0
            self._target_rot = 0.0
        self.scale += (self._target_scale - self.scale) * self.LERP
        self.rotation += (self._target_rot - self.rotation) * self.LERP

    @property
    def bob_y(self) -> float:
        return self._bob_y


# ---------------------------------------------------------------------------
# Bezier card-flight animation
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _CardAnim:
    card: "Card"
    p0: tuple[float, float]  # start centre
    p1: tuple[float, float]  # control point (arcs above mid)
    p2: tuple[float, float]  # end centre (arena slot)
    start_ms: int
    duration_ms: int = 500
    trump: "Suit | None" = None


def _bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
        u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
    )


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2
