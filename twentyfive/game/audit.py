"""
Game audit log — records every player decision to newline-delimited JSON.

One file per game: logs/game_<id8>_<YYYYMMDD_HHMMSS>.jsonl

Event types
-----------
deal         — emitted at the start of each round (full hands + trump)
play_card    — a card played during the trick phase
rob          — player robs the face-up trump card
pass_rob     — player declines to rob
trick_result — outcome of a completed trick (winner + plays)
hand_result  — round summary: tricks won and cumulative scores per player
game_result  — final result: winner and all scores
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from twentyfive.cards.card import Card
from twentyfive.game.state import Move, PlayCard, Rob, TrickPlay

if TYPE_CHECKING:
    from twentyfive.game.player import Player


class GameAudit:
    def __init__(self, game_id: str, audit_dir: Path) -> None:
        audit_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = audit_dir / f"game_{game_id[:8]}_{ts}.jsonl"
        self._game_id = game_id
        self._file = path.open("a", encoding="utf-8")

    def record_deal(
        self,
        players: list[Player],
        round_number: int,
        dealer_index: int,
        trump_suit_name: str,
        face_up_card: Card | None,
    ) -> None:
        self._write({
            "event_type": "deal",
            "game_id": self._game_id,
            "timestamp": _now(),
            "round_number": round_number,
            "dealer_index": dealer_index,
            "trump_suit": trump_suit_name,
            "face_up_card": str(face_up_card) if face_up_card else None,
            "hands": {p.name: [str(c) for c in p.hand] for p in players},
        })

    def record_move(
        self,
        round_number: int,
        trick_number: int,
        player_name: str,
        player_index: int,
        move: Move,
        legal_moves: list[Move],
    ) -> None:
        event: dict = {
            "event_type": _move_type(move),
            "game_id": self._game_id,
            "timestamp": _now(),
            "round_number": round_number,
            "trick_number": trick_number,
            "player_name": player_name,
            "player_index": player_index,
            "legal_moves": [_move_repr(m) for m in legal_moves],
        }
        if isinstance(move, PlayCard):
            event["card"] = str(move.card)
        elif isinstance(move, Rob):
            event["discard"] = str(move.discard)
        self._write(event)

    def record_trick_result(
        self,
        round_number: int,
        trick_number: int,
        plays: list[TrickPlay],
        winner_name: str,
        winner_index: int,
    ) -> None:
        self._write({
            "event_type": "trick_result",
            "game_id": self._game_id,
            "timestamp": _now(),
            "round_number": round_number,
            "trick_number": trick_number,
            "plays": [{"player_name": tp.player_name, "card": str(tp.card)} for tp in plays],
            "winner_name": winner_name,
            "winner_index": winner_index,
        })

    def record_hand_result(
        self,
        round_number: int,
        players: list[Player],
    ) -> None:
        self._write({
            "event_type": "hand_result",
            "game_id": self._game_id,
            "timestamp": _now(),
            "round_number": round_number,
            "tricks_won": {p.name: p.tricks_won_this_round for p in players},
            "scores": {p.name: p.score for p in players},
        })

    def record_game_result(
        self,
        winner_name: str,
        players: list[Player],
    ) -> None:
        self._write({
            "event_type": "game_result",
            "game_id": self._game_id,
            "timestamp": _now(),
            "winner_name": winner_name,
            "final_scores": {p.name: p.score for p in players},
        })

    def _write(self, event: dict) -> None:
        self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._file.flush()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _move_type(move: Move) -> str:
    if isinstance(move, PlayCard):
        return "play_card"
    if isinstance(move, Rob):
        return "rob"
    return "pass_rob"


def _move_repr(move: Move) -> str:
    if isinstance(move, PlayCard):
        return str(move.card)
    if isinstance(move, Rob):
        return f"rob:{move.discard}"
    return "pass_rob"
