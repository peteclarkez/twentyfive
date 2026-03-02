from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from twentyfive.cards.card import Card, Suit


class Phase(Enum):
    ROB = auto()
    TRICK = auto()
    GAME_OVER = auto()


# ---------------------------------------------------------------------------
# Move hierarchy — all moves are frozen dataclasses for hashability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """Base class for all player actions."""


@dataclass(frozen=True)
class PlayCard(Move):
    """Play a card during trick phase."""

    card: Card


@dataclass(frozen=True)
class Rob(Move):
    """Take the face-up trump card and discard one card from hand."""

    discard: Card


@dataclass(frozen=True)
class PassRob(Move):
    """Decline to rob (or ineligible — engine auto-applies for ineligible players)."""


# ---------------------------------------------------------------------------
# Immutable snapshots used in GameState
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrickPlay:
    player_name: str
    card: Card


@dataclass(frozen=True)
class PlayerSnapshot:
    name: str
    score: int
    tricks_won_this_round: int
    hand_size: int
    hand: tuple[Card, ...]  # always populated — privacy is a UI concern


# ---------------------------------------------------------------------------
# GameState — the complete read-only snapshot produced by GameEngine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameState:
    phase: Phase
    players: tuple[PlayerSnapshot, ...]
    current_player_index: int
    dealer_index: int
    trump_suit: Suit | None
    face_up_card: Card | None
    current_trick: tuple[TrickPlay, ...]
    trick_number: int  # 1–5 within the current round
    round_number: int
    legal_moves: tuple[Move, ...]

    @property
    def current_player(self) -> PlayerSnapshot:
        return self.players[self.current_player_index]
