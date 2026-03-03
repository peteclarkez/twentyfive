from __future__ import annotations

import copy
import uuid
from pathlib import Path

from twentyfive.cards.card import Card, Rank, Suit
from twentyfive.cards.deck import Deck
from twentyfive.game.audit import GameAudit
from twentyfive.game.player import Player
from twentyfive.game.rules import get_legal_cards, get_legal_rob_moves, trick_winner
from twentyfive.game.state import (
    ConfirmRoundEnd,
    GameState,
    Move,
    Phase,
    PlayCard,
    Rob,
    TrickPlay,
)


class GameEngine:
    """
    The Twenty-Five game state machine.

    Public API:
        get_state()      — read-only snapshot of current game state
        apply_move(move) — validate and apply a player move
        is_game_over     — True once a player has reached 25 points
    """

    def __init__(
        self,
        player_names: list[str],
        *,
        audit_dir: Path | None = Path("logs"),
        initial_dealer: int = 0,
    ) -> None:
        if not 2 <= len(player_names) <= 6:
            raise ValueError(f"Twenty-Five requires 2–6 players, got {len(player_names)}")
        if len(set(player_names)) != len(player_names):
            raise ValueError("Player names must be unique")
        if not 0 <= initial_dealer < len(player_names):
            raise ValueError(
                f"initial_dealer {initial_dealer} out of range for {len(player_names)} players"
            )

        self._game_id: str = str(uuid.uuid4())
        self._players: list[Player] = [Player(name=n) for n in player_names]
        self._dealer_index: int = initial_dealer
        self._round_number: int = 1

        # These are set by _start_round()
        self._trump_suit: Suit = Suit.CLUBS  # placeholder; overwritten immediately
        self._face_up_card: Card | None = None
        self._phase: Phase = Phase.ROB
        self._current_player_index: int = 0
        self._current_trick: list[TrickPlay] = []
        self._completed_tricks_this_round: list[tuple[TrickPlay, ...]] = []
        self._trick_number: int = 1
        self._rob_queue: list[int] = []  # indices of players still to act in rob phase
        self._rob_this_round: tuple[str, Card] | None = None  # public: (player_name, card_taken)

        self._audit: GameAudit | None = (
            GameAudit(self._game_id, audit_dir) if audit_dir is not None else None
        )

        self._start_round()

        if self._audit:
            self._audit.record_deal(
                self._players,
                self._round_number,
                self._dealer_index,
                self._trump_suit.name,
                self._face_up_card,
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_state(self) -> GameState:
        """Return a complete, immutable snapshot of the current game state."""
        snapshots = tuple(p.snapshot() for p in self._players)
        legal = tuple(self._compute_legal_moves())
        return GameState(
            phase=self._phase,
            players=snapshots,
            current_player_index=self._current_player_index,
            dealer_index=self._dealer_index,
            trump_suit=self._trump_suit,
            face_up_card=self._face_up_card,
            current_trick=tuple(self._current_trick),
            completed_tricks=tuple(self._completed_tricks_this_round),
            trick_number=self._trick_number,
            round_number=self._round_number,
            game_id=self._game_id,
            legal_moves=legal,
            rob_this_round=self._rob_this_round,
        )

    def apply_move(self, move: Move) -> None:
        """
        Apply a validated move for the current player.
        Raises ValueError if the move is not legal in the current state.
        """
        legal = self._compute_legal_moves()
        if move not in legal:
            raise ValueError(f"Illegal move {move!r}. Legal moves: {legal}")

        # Capture pre-move context for audit
        pre_round = self._round_number
        pre_trick = self._trick_number
        pre_phase = self._phase
        pre_completed_count = len(self._completed_tricks_this_round)
        player = self._players[self._current_player_index]
        player_idx = self._current_player_index

        match self._phase:
            case Phase.ROB:
                self._apply_rob_move(move)
            case Phase.TRICK:
                self._apply_trick_move(move)
            case Phase.ROUND_END:
                self._apply_confirm_round_end()
            case Phase.GAME_OVER:
                raise ValueError("Game is over; no moves can be applied")

        if self._audit:
            # ConfirmRoundEnd is a UI acknowledgment — not a game decision; skip recording
            if pre_phase != Phase.ROUND_END:
                self._audit.record_move(
                    pre_round, pre_trick, player.name, player_idx, move, legal,
                    trump_suit=self._trump_suit,
                )

            # Trick just resolved? (completed_tricks grew)
            if len(self._completed_tricks_this_round) > pre_completed_count:
                last_trick = self._completed_tricks_this_round[-1]
                led_suit = last_trick[0].card.suit
                winning_play = trick_winner(list(last_trick), led_suit, self._trump_suit)
                winner_idx = next(
                    i for i, p in enumerate(self._players)
                    if p.name == winning_play.player_name
                )
                self._audit.record_trick_result(
                    round_number=pre_round,
                    trick_number=pre_trick,
                    plays=list(last_trick),
                    winner_name=winning_play.player_name,
                    winner_index=winner_idx,
                )

            # Game just ended?
            if self._phase == Phase.GAME_OVER and pre_phase != Phase.GAME_OVER:
                winner = self._players[self._current_player_index]
                self._audit.record_game_result(
                    winner_name=winner.name,
                    players=self._players,
                )
            # Round just ended (5th trick → ROUND_END)?
            elif self._phase == Phase.ROUND_END and pre_phase != Phase.ROUND_END:
                self._audit.record_hand_result(
                    round_number=pre_round,
                    players=self._players,
                )
            # New round started (ConfirmRoundEnd applied)?
            elif self._round_number != pre_round:
                self._audit.record_deal(
                    self._players,
                    self._round_number,
                    self._dealer_index,
                    self._trump_suit.name,
                    self._face_up_card,
                )

    def record_game_start(self, player_types: dict[str, str]) -> None:
        """Record a game_start audit event with player names and types."""
        if self._audit:
            self._audit.record_game_start(self._players, player_types)

    def clone(self) -> GameEngine:
        """
        Return a deep copy of this engine with audit disabled.

        Used by MCTSPlayer to create isolated simulation environments without
        affecting the real game state or writing to the audit log.
        """
        audit = self._audit
        self._audit = None
        try:
            cloned = copy.deepcopy(self)
        finally:
            self._audit = audit
        return cloned

    @property
    def is_game_over(self) -> bool:
        return self._phase == Phase.GAME_OVER

    # ------------------------------------------------------------------
    # Round setup
    # ------------------------------------------------------------------

    def _start_round(self) -> None:
        """Shuffle, deal, turn up trump, compute rob queue, set phase."""
        self._completed_tricks_this_round = []
        self._rob_this_round = None

        for player in self._players:
            player.clear_hand()
            player.reset_round_stats()

        deck = Deck()
        deck.shuffle()

        n = len(self._players)
        left_of_dealer = (self._dealer_index + 1) % n

        # Deal 3 cards then 2 cards, starting left of dealer, going clockwise
        for batch in (3, 2):
            for offset in range(n):
                idx = (left_of_dealer + offset) % n
                for card in deck.deal(batch):
                    self._players[idx].add_card(card)

        self._face_up_card = deck.turn_up()
        self._trump_suit = self._face_up_card.suit
        self._current_trick = []
        self._trick_number = 1

        # Build rob queue: eligible players in seat order starting left of dealer
        self._rob_queue = []
        ace_of_trump = Card(Rank.ACE, self._trump_suit)
        for offset in range(n):
            idx = (left_of_dealer + offset) % n
            player = self._players[idx]
            is_dealer = idx == self._dealer_index
            if is_dealer:
                if self._face_up_card == ace_of_trump:
                    self._rob_queue.append(idx)
            else:
                if ace_of_trump in player.hand:
                    self._rob_queue.append(idx)

        if self._rob_queue:
            self._phase = Phase.ROB
            self._current_player_index = self._rob_queue[0]
        else:
            self._phase = Phase.TRICK
            self._current_player_index = left_of_dealer

    # ------------------------------------------------------------------
    # Legal move computation
    # ------------------------------------------------------------------

    def _compute_legal_moves(self) -> list[Move]:
        if self._phase == Phase.GAME_OVER:
            return []

        if self._phase == Phase.ROUND_END:
            return [ConfirmRoundEnd()]

        if self._phase == Phase.ROB:
            player = self._players[self._current_player_index]
            is_dealer = self._current_player_index == self._dealer_index
            assert self._face_up_card is not None
            return get_legal_rob_moves(
                hand=player.hand,
                face_up_card=self._face_up_card,
                trump_suit=self._trump_suit,
                is_dealer=is_dealer,
            )

        # TRICK phase
        player = self._players[self._current_player_index]
        led_card = self._current_trick[0].card if self._current_trick else None
        legal_cards = get_legal_cards(
            hand=player.hand,
            led_card=led_card,
            trump_suit=self._trump_suit,
        )
        return [PlayCard(card=c) for c in legal_cards]

    # ------------------------------------------------------------------
    # Move application
    # ------------------------------------------------------------------

    def _apply_rob_move(self, move: Move) -> None:
        assert self._face_up_card is not None
        player = self._players[self._current_player_index]

        if isinstance(move, Rob):
            player.remove_card(move.discard)
            self._rob_this_round = (player.name, self._face_up_card)
            player.add_card(self._face_up_card)
            self._face_up_card = None
            # Only one rob per round — clear remaining queue
            self._rob_queue.clear()
        else:
            # PassRob — advance to the next eligible player
            self._rob_queue.pop(0)

        self._advance_rob_phase()

    def _advance_rob_phase(self) -> None:
        """Move to the next player in the rob queue, or transition to TRICK."""
        if self._rob_queue:
            self._current_player_index = self._rob_queue[0]
        else:
            n = len(self._players)
            self._phase = Phase.TRICK
            self._current_player_index = (self._dealer_index + 1) % n

    def _apply_trick_move(self, move: Move) -> None:
        assert isinstance(move, PlayCard)
        player = self._players[self._current_player_index]
        player.remove_card(move.card)
        self._current_trick.append(TrickPlay(player_name=player.name, card=move.card))

        n = len(self._players)
        if len(self._current_trick) < n:
            # Trick still in progress — next player clockwise
            self._current_player_index = (self._current_player_index + 1) % n
        else:
            # All players have played — resolve the trick
            self._resolve_trick()

    def _resolve_trick(self) -> None:
        led_suit = self._current_trick[0].card.suit
        winning_play = trick_winner(self._current_trick, led_suit, self._trump_suit)

        # Find the winning player
        winner_idx = next(
            i for i, p in enumerate(self._players) if p.name == winning_play.player_name
        )
        winner = self._players[winner_idx]
        winner.score += 5
        winner.tricks_won_this_round += 1

        # Save the completed trick before clearing
        self._completed_tricks_this_round.append(tuple(self._current_trick))

        # Win condition: first to 25 (GAME-28 — checked after every trick)
        if winner.score >= 25:
            self._current_trick = []  # already saved in completed_tricks above
            self._phase = Phase.GAME_OVER
            self._current_player_index = winner_idx
            return

        self._trick_number += 1
        self._current_trick = []
        self._current_player_index = winner_idx

        if self._trick_number > 5:
            # Round complete — pause for acknowledgment before dealing next hand
            self._phase = Phase.ROUND_END

    def _apply_confirm_round_end(self) -> None:
        """Start the next round after the player acknowledges the round end."""
        n = len(self._players)
        self._dealer_index = (self._dealer_index + 1) % n
        self._round_number += 1
        self._start_round()
