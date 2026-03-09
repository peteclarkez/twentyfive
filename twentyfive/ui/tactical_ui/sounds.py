"""
SoundManager — procedurally synthesised sound effects for the Tactical UI.

All sounds are generated at construction time using only Python's stdlib ``array``
module and ``pygame.mixer``.  No audio files or numpy are required.

Sounds are initialised lazily-safe: if ``pygame.mixer`` has not been initialised yet
the constructor calls ``pygame.mixer.init()`` itself.

Usage::

    sounds = SoundManager()         # generate all sounds
    sounds.play_card_play()         # fire and forget
    sounds.toggle_mute()            # mute / unmute
"""

from __future__ import annotations

import array
import math
import random


# ---------------------------------------------------------------------------
# Synthesis helpers
# ---------------------------------------------------------------------------

_SAMPLE_RATE = 22050
_MAX_AMP = 32767


def _sine(
    freq: float,
    duration: float,
    amplitude: float = 0.4,
    attack: float = 0.005,
    decay: float = 8.0,
) -> array.array:
    """
    Single sine-wave tone with an optional exponential-decay envelope.

    *decay* controls how quickly the tone fades (higher = faster).  Set to 0 for
    no decay (sustain).
    """
    n = int(_SAMPLE_RATE * duration)
    buf: list[int] = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        env = amplitude * math.exp(-decay * t)
        # Tiny linear attack to avoid click at onset
        if t < attack:
            env *= t / attack
        sample = env * _MAX_AMP * math.sin(2.0 * math.pi * freq * t)
        buf.append(max(-_MAX_AMP, min(_MAX_AMP, int(sample))))
    return array.array("h", buf)


def _noise_burst(
    duration: float,
    amplitude: float = 0.35,
    decay: float = 20.0,
) -> array.array:
    """Short white-noise burst with exponential decay — percussive thwack."""
    n = int(_SAMPLE_RATE * duration)
    rng = random.Random(0)
    buf: list[int] = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        env = amplitude * math.exp(-decay * t)
        sample = env * _MAX_AMP * (rng.random() * 2.0 - 1.0)
        buf.append(max(-_MAX_AMP, min(_MAX_AMP, int(sample))))
    return array.array("h", buf)


def _mix(*parts: array.array) -> array.array:
    """Mix (sum + clip) several same-length PCM buffers."""
    n = max(len(p) for p in parts)
    buf: list[int] = []
    for i in range(n):
        total = sum(p[i] if i < len(p) else 0 for p in parts)
        buf.append(max(-_MAX_AMP, min(_MAX_AMP, total)))
    return array.array("h", buf)


def _concat(*parts: array.array) -> array.array:
    """Concatenate PCM buffers sequentially."""
    result: array.array = array.array("h")
    for p in parts:
        result.extend(p)
    return result


def _silence(duration: float) -> array.array:
    return array.array("h", [0] * int(_SAMPLE_RATE * duration))


def _to_sound(buf: array.array) -> "pygame.mixer.Sound":  # type: ignore[name-defined]
    import pygame

    return pygame.mixer.Sound(buffer=buf)


# ---------------------------------------------------------------------------
# Procedural sound definitions
# ---------------------------------------------------------------------------


def _make_card_play() -> array.array:
    """Short swish: white noise with a smooth hat envelope + faint high-freq shimmer."""
    duration = 0.10
    n = int(_SAMPLE_RATE * duration)
    rng = random.Random(1)
    buf: list[int] = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        # Hat envelope: rises to peak at midpoint then falls back to 0 (no hard attack)
        env = math.sin(math.pi * t / duration)
        noise_sample = env * 0.40 * _MAX_AMP * (rng.random() * 2.0 - 1.0)
        # Faint high-freq shimmer gives it the airy "s" in swish
        shimmer = env * 0.08 * _MAX_AMP * math.sin(2.0 * math.pi * 5500 * t)
        buf.append(max(-_MAX_AMP, min(_MAX_AMP, int(noise_sample + shimmer))))
    return array.array("h", buf)


def _make_trick_win() -> array.array:
    """3-note ascending arpeggio — C5, E5, G5."""
    notes = [523, 659, 784]  # C5, E5, G5 Hz
    parts = [
        _silence(i * 0.10) + _sine(f, 0.22, amplitude=0.40, decay=6.0) for i, f in enumerate(notes)
    ]
    # Pad to same length then concatenate
    total = int(_SAMPLE_RATE * 0.50)
    result: array.array = array.array("h", [0] * total)
    for part in parts:
        for j, v in enumerate(part):
            if j < total:
                result[j] = max(-_MAX_AMP, min(_MAX_AMP, result[j] + v))
    return result


def _make_round_end() -> array.array:
    """4-note chord swell: C4–E4–G4–C5 in quick succession then held."""
    notes = [262, 330, 392, 523]  # C4, E4, G4, C5
    gaps = [0.0, 0.07, 0.14, 0.21]
    total_s = 0.80
    total = int(_SAMPLE_RATE * total_s)
    result: array.array = array.array("h", [0] * total)
    for freq, gap in zip(notes, gaps):
        offset = int(_SAMPLE_RATE * gap)
        tone = _sine(freq, total_s - gap, amplitude=0.28, decay=2.5)
        for j, v in enumerate(tone):
            idx = offset + j
            if idx < total:
                result[idx] = max(-_MAX_AMP, min(_MAX_AMP, result[idx] + v))
    return result


def _make_game_win() -> array.array:
    """5-note ascending fanfare: C5, E5, G5, C6, E6."""
    notes = [523, 659, 784, 1047, 1319]
    gaps = [0.0, 0.09, 0.18, 0.27, 0.36]
    total_s = 1.00
    total = int(_SAMPLE_RATE * total_s)
    result: array.array = array.array("h", [0] * total)
    for freq, gap in zip(notes, gaps):
        offset = int(_SAMPLE_RATE * gap)
        tone = _sine(freq, total_s - gap, amplitude=0.26, decay=2.0)
        for j, v in enumerate(tone):
            idx = offset + j
            if idx < total:
                result[idx] = max(-_MAX_AMP, min(_MAX_AMP, result[idx] + v))
    return result


def _make_game_lose() -> array.array:
    """3-note descending resolve: G4, E4, C4."""
    notes = [392, 330, 262]
    gaps = [0.0, 0.12, 0.24]
    total_s = 0.75
    total = int(_SAMPLE_RATE * total_s)
    result: array.array = array.array("h", [0] * total)
    for freq, gap in zip(notes, gaps):
        offset = int(_SAMPLE_RATE * gap)
        tone = _sine(freq, total_s - gap, amplitude=0.32, decay=3.5)
        for j, v in enumerate(tone):
            idx = offset + j
            if idx < total:
                result[idx] = max(-_MAX_AMP, min(_MAX_AMP, result[idx] + v))
    return result


def _make_rob() -> array.array:
    """Low dramatic 'whump' — descending sine sweep 220→110 Hz."""
    duration = 0.30
    n = int(_SAMPLE_RATE * duration)
    buf: list[int] = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        freq = 220.0 * math.exp(-t * 2.5)  # descends from 220 to ~110
        env = 0.50 * math.exp(-t * 5.0)
        sample = env * _MAX_AMP * math.sin(2.0 * math.pi * freq * t)
        buf.append(max(-_MAX_AMP, min(_MAX_AMP, int(sample))))
    return array.array("h", buf)


def _make_error() -> array.array:
    """Short buzzer — dissonant mix of 200 + 267 Hz (tritone-ish)."""
    a = _sine(200, 0.18, amplitude=0.30, decay=10.0)
    b = _sine(267, 0.18, amplitude=0.25, decay=10.0)
    return _mix(a, b)


def _make_button_click() -> array.array:
    """Very short tick — 50 ms sine at 1000 Hz."""
    return _sine(1000, 0.05, amplitude=0.25, decay=40.0)


# ---------------------------------------------------------------------------
# SoundManager
# ---------------------------------------------------------------------------


class SoundManager:
    """
    Generates and plays all game sound effects.

    Call ``toggle_mute()`` to silence/restore sounds.
    All ``play_*()`` methods are no-ops when muted.
    """

    def __init__(self, volume: float = 0.7) -> None:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=_SAMPLE_RATE, size=-16, channels=1, buffer=512)

        self._muted = False
        self._volume = max(0.0, min(1.0, volume))

        # Build all sounds up front so there is no hitch during gameplay
        self._card_play = _to_sound(_make_card_play())
        self._trick_win = _to_sound(_make_trick_win())
        self._round_end = _to_sound(_make_round_end())
        self._game_win = _to_sound(_make_game_win())
        self._game_lose = _to_sound(_make_game_lose())
        self._rob = _to_sound(_make_rob())
        self._error = _to_sound(_make_error())
        self._button_click = _to_sound(_make_button_click())

        self._set_volumes()

    # ------------------------------------------------------------------
    # Mute / volume
    # ------------------------------------------------------------------

    @property
    def muted(self) -> bool:
        return self._muted

    def toggle_mute(self) -> None:
        self._muted = not self._muted

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._set_volumes()

    def _set_volumes(self) -> None:
        for snd in (
            self._card_play,
            self._trick_win,
            self._round_end,
            self._game_win,
            self._game_lose,
            self._rob,
            self._error,
            self._button_click,
        ):
            snd.set_volume(self._volume)

    # ------------------------------------------------------------------
    # Play methods
    # ------------------------------------------------------------------

    def _play(self, sound: "pygame.mixer.Sound") -> None:  # type: ignore[name-defined]
        if not self._muted:
            sound.play()

    def play_card_play(self) -> None:
        """Card committed to the trick (human or AI)."""
        self._play(self._card_play)

    def play_trick_win(self) -> None:
        """Trick just completed."""
        self._play(self._trick_win)

    def play_round_end(self) -> None:
        """Round-end overlay fires."""
        self._play(self._round_end)

    def play_game_win(self) -> None:
        """Game over — this player (or spectator) won."""
        self._play(self._game_win)

    def play_game_lose(self) -> None:
        """Game over — this player did not win."""
        self._play(self._game_lose)

    def play_rob(self) -> None:
        """Rob action taken."""
        self._play(self._rob)

    def play_error(self) -> None:
        """Illegal move or invalid discard attempt."""
        self._play(self._error)

    def play_button_click(self) -> None:
        """Any interactive button pressed."""
        self._play(self._button_click)
