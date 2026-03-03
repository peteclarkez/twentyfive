"""
Tests for EnhancedHeuristicPlayer.

Covers all seven enhancements:
  1. Card tracking  — leads from dominant suit when available
  2. Endgame        — commits trump in tricks 4–5 without a danger player
  3. Multi-opponent — score leader at >= 15 pts treated as dangerous
  4. Rob quality    — prefers singleton non-trump discard (goes void)
  5. Don't over-trump — non-trump winner preferred over trump winner
  6. Let safe player win — disabled by default (_e6_enabled=False); tests set the flag
  7. Weak trump lead — late game only (tricks 4–5); prefer non-trump over weak trump
"""

from __future__ import annotations

import random

from twentyfive.ai.enhanced_heuristic import EnhancedHeuristicPlayer
from twentyfive.cards.card import Card, Rank, Suit, is_trump
from twentyfive.game.engine import GameEngine
from twentyfive.game.rules import card_global_rank
from twentyfive.game.state import (
    ConfirmRoundEnd,
    GameState,
    PassRob,
    Phase,
    PlayCard,
    PlayerSnapshot,
    Rob,
    TrickPlay,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRUMP = Suit.HEARTS


def make_engine(n: int = 3, seed: int = 42) -> GameEngine:
    random.seed(seed)
    return GameEngine(player_names=[f"P{i+1}" for i in range(n)], audit_dir=None)


def advance_past_rob(engine: GameEngine) -> None:
    while not engine.is_game_over:
        state = engine.get_state()
        if state.phase != Phase.ROB:
            break
        engine.apply_move(PassRob())


def advance_to_round_end(engine: GameEngine, *, max_moves: int = 200) -> None:
    advance_past_rob(engine)
    moves = 0
    while not engine.is_game_over and moves < max_moves:
        state = engine.get_state()
        if state.phase == Phase.ROUND_END:
            return
        engine.apply_move(state.legal_moves[0])
        moves += 1


def find_engine_in_rob_phase(n: int = 3) -> GameEngine:
    for seed in range(500):
        random.seed(seed)
        engine = GameEngine([f"P{i+1}" for i in range(n)], audit_dir=None)
        if engine.get_state().phase == Phase.ROB:
            return engine
    raise RuntimeError("Could not find a seed with a rob phase")  # pragma: no cover


def make_state(
    *,
    phase: Phase = Phase.TRICK,
    hand: tuple[Card, ...],
    score: int = 0,
    trump_suit: Suit = TRUMP,
    current_trick: tuple[TrickPlay, ...] = (),
    completed_tricks: tuple[tuple[TrickPlay, ...], ...] = (),
    trick_number: int = 1,
    opponents: tuple[tuple[str, int], ...] = (("P2", 0), ("P3", 0)),
    legal_moves: tuple | None = None,
    face_up_card: Card | None = None,
) -> GameState:
    """Build a minimal GameState for focused unit tests."""
    me = PlayerSnapshot(
        name="P1",
        score=score,
        tricks_won_this_round=0,
        hand_size=len(hand),
        hand=hand,
    )
    others = tuple(
        PlayerSnapshot(name=n, score=s, tricks_won_this_round=0, hand_size=5, hand=())
        for n, s in opponents
    )
    players = (me,) + others

    if legal_moves is None:
        legal_moves = tuple(PlayCard(card=c) for c in hand)

    return GameState(
        phase=phase,
        players=players,
        current_player_index=0,
        dealer_index=1,
        trump_suit=trump_suit,
        face_up_card=face_up_card,
        current_trick=current_trick,
        completed_tricks=completed_tricks,
        trick_number=trick_number,
        round_number=1,
        game_id="test",
        legal_moves=legal_moves,
    )


# ---------------------------------------------------------------------------
# Enhancement 4: Rob discard quality
# ---------------------------------------------------------------------------


class TestEnhancedRob:
    def test_prefers_singleton_non_trump_discard(self) -> None:
        """Should discard the singleton non-trump card to go void in that suit."""
        # Hand: 3 non-trumps across 3 suits — one singleton per suit
        # Only one card per non-trump suit → any of them is a singleton
        # We hold exactly one card in each of Clubs, Diamonds, and Spades.
        # The "weakest" singleton (highest global rank) should be chosen.
        trump_suit = Suit.CLUBS
        hand = (
            Card(Rank.TWO, Suit.DIAMONDS),   # non-trump singleton in Diamonds
            Card(Rank.THREE, Suit.SPADES),    # non-trump singleton in Spades
            Card(Rank.KING, Suit.HEARTS),     # non-trump (Hearts, not trump when trump=Clubs)
        )
        # A♥ is always trump; K♥ is not trump when trump=Clubs
        assert not is_trump(Card(Rank.KING, Suit.HEARTS), trump_suit)

        legal_moves = tuple(Rob(discard=c) for c in hand) + (PassRob(),)
        state = make_state(
            phase=Phase.ROB,
            hand=hand,
            trump_suit=trump_suit,
            legal_moves=legal_moves,
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, Rob)
        # All three are singletons; should pick the weakest (highest global rank)
        singleton_non_trumps = [c for c in hand if not is_trump(c, trump_suit)]
        worst_rank = max(card_global_rank(c, trump_suit) for c in singleton_non_trumps)
        assert card_global_rank(move.discard, trump_suit) == worst_rank

    def test_singleton_preferred_over_multi_non_trump(self) -> None:
        """Singleton non-trump is discarded over a multi-card non-trump suit."""
        trump_suit = Suit.CLUBS
        hand = (
            Card(Rank.TWO, Suit.DIAMONDS),   # singleton in Diamonds
            Card(Rank.THREE, Suit.HEARTS),    # Hearts non-trump when trump=Clubs
            Card(Rank.FOUR, Suit.HEARTS),     # same suit → Hearts now has 2 cards (not singleton)
        )
        legal_moves = tuple(Rob(discard=c) for c in hand) + (PassRob(),)
        state = make_state(
            phase=Phase.ROB,
            hand=hand,
            trump_suit=trump_suit,
            legal_moves=legal_moves,
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, Rob)
        # Only 2♦ is a singleton non-trump
        assert move.discard == Card(Rank.TWO, Suit.DIAMONDS)

    def test_falls_back_to_any_non_trump_when_no_singleton(self) -> None:
        """With no singleton, discards the weakest non-trump from those available."""
        trump_suit = Suit.CLUBS
        hand = (
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.DIAMONDS),  # same suit → no singleton
        )
        legal_moves = tuple(Rob(discard=c) for c in hand) + (PassRob(),)
        state = make_state(
            phase=Phase.ROB,
            hand=hand,
            trump_suit=trump_suit,
            legal_moves=legal_moves,
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, Rob)
        # Falls back to weakest non-trump (highest global rank)
        non_trumps = [c for c in hand if not is_trump(c, trump_suit)]
        worst_rank = max(card_global_rank(c, trump_suit) for c in non_trumps)
        assert card_global_rank(move.discard, trump_suit) == worst_rank

    def test_pass_rob_when_ineligible(self) -> None:
        """Returns PassRob() when legal_moves contains only PassRob."""
        state = make_state(
            phase=Phase.ROB,
            hand=(Card(Rank.TWO, Suit.CLUBS),),
            trump_suit=Suit.HEARTS,
            legal_moves=(PassRob(),),
        )
        player = EnhancedHeuristicPlayer()
        assert isinstance(player.choose_move(state), PassRob)

    def test_robs_via_engine(self) -> None:
        """Integration: EnhancedHeuristicPlayer always robs when eligible."""
        engine = find_engine_in_rob_phase()
        state = engine.get_state()
        rob_available = any(isinstance(m, Rob) for m in state.legal_moves)

        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)

        if rob_available:
            assert isinstance(move, Rob)
        else:
            assert isinstance(move, PassRob)


# ---------------------------------------------------------------------------
# Enhancement 3: Multi-opponent awareness
# ---------------------------------------------------------------------------


class TestEnhancedMultiOpponent:
    def test_leader_at_15_triggers_danger(self) -> None:
        """Score leader at exactly 15 pts should be treated as a danger player."""
        trump_suit = Suit.CLUBS
        five = Card(Rank.FIVE, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (five, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            opponents=(("P2", 15), ("P3", 0)),  # P2 is leader at 15
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # With a danger player, should lead strongest trump (the Five)
        assert is_trump(move.card, trump_suit)
        assert card_global_rank(move.card, trump_suit) == min(
            card_global_rank(c, trump_suit) for c in hand if is_trump(c, trump_suit)
        )

    def test_leader_at_14_not_danger(self) -> None:
        """Score leader at 14 pts should NOT trigger danger behaviour."""
        trump_suit = Suit.CLUBS
        five = Card(Rank.FIVE, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (five, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            opponents=(("P2", 14), ("P3", 0)),  # below threshold
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # No danger player → conservative lead (weakest non-trump), not trump
        # (unless card tracking finds a dominant trump — but trump can't be dominant
        # in non-trump lead sense; dominance only applies to non-trumps)
        # The non-trump K♦ should be played over Five in this scenario
        assert not is_trump(move.card, trump_suit)

    def test_two_danger_players_at_20(self) -> None:
        """Both players at >= 20 should be in the danger set (existing behaviour)."""
        trump_suit = Suit.CLUBS
        five = Card(Rank.FIVE, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (five, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            opponents=(("P2", 20), ("P3", 21)),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        assert is_trump(move.card, trump_suit)


# ---------------------------------------------------------------------------
# Enhancement 2: Endgame awareness
# ---------------------------------------------------------------------------


class TestEnhancedEndgame:
    def test_leads_trump_in_trick_4_without_danger(self) -> None:
        """In trick 4 with no danger player, leads strongest trump."""
        trump_suit = Suit.CLUBS
        five = Card(Rank.FIVE, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (five, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            trick_number=4,
            opponents=(("P2", 0), ("P3", 0)),  # no danger
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        assert is_trump(move.card, trump_suit)

    def test_leads_trump_in_trick_5_without_danger(self) -> None:
        """In trick 5 with no danger player, leads strongest trump."""
        trump_suit = Suit.CLUBS
        jack = Card(Rank.JACK, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (jack, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            trick_number=5,
            opponents=(("P2", 0), ("P3", 0)),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        assert is_trump(move.card, trump_suit)

    def test_no_endgame_lead_trump_in_trick_3(self) -> None:
        """Trick 3 is not endgame — without danger, leads weakest non-trump."""
        trump_suit = Suit.CLUBS
        five = Card(Rank.FIVE, trump_suit)
        non_trump = Card(Rank.KING, Suit.DIAMONDS)

        hand = (five, non_trump)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            trick_number=3,
            opponents=(("P2", 0), ("P3", 0)),
            # No completed tricks → no card tracking dominance either
            completed_tricks=(),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # Should lead non-trump (conservative fallback or dominant — K♦ is dominant
        # in fresh state since no diamonds played and K♦ is the highest diamond possible
        # after Q/J... wait, K♦ is the strongest non-trump diamond so it IS dominant)
        # Either way, not trump
        assert not is_trump(move.card, trump_suit)


# ---------------------------------------------------------------------------
# Enhancement 5: Don't over-trump
# ---------------------------------------------------------------------------


class TestEnhancedDontOverTrump:
    def test_plays_non_trump_winner_before_trump(self) -> None:
        """When I can win with a non-trump card, should NOT burn trump."""
        trump_suit = Suit.CLUBS
        # Trick: P2 led 2♦ (non-trump)
        led_card = Card(Rank.TWO, Suit.DIAMONDS)
        current_trick = (TrickPlay("P2", led_card),)

        # My hand: K♦ (wins non-trump) and J♣ (trump winner too)
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)
        jack_clubs = Card(Rank.JACK, trump_suit)

        hand = (king_diamonds, jack_clubs)
        legal_moves = (PlayCard(card=king_diamonds), PlayCard(card=jack_clubs))
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=legal_moves,
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # Should use the non-trump winner, not the trump
        assert move.card == king_diamonds

    def test_uses_trump_when_only_trump_wins(self) -> None:
        """Falls back to trump winner when no non-trump winner exists."""
        trump_suit = Suit.CLUBS
        # P2 led K♦ — the highest non-trump diamond (rank 13 in red non-trump table)
        led_card = Card(Rank.KING, Suit.DIAMONDS)
        current_trick = (TrickPlay("P2", led_card),)

        # My hand: 2♦ (can't beat K♦ — rank 2 vs 13) and 2♣ (trump — can win)
        two_diamonds = Card(Rank.TWO, Suit.DIAMONDS)
        two_clubs = Card(Rank.TWO, trump_suit)  # trump, wins

        hand = (two_diamonds, two_clubs)
        legal_moves = (PlayCard(card=two_diamonds), PlayCard(card=two_clubs))
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=legal_moves,
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # Non-trump 2♦ can't beat K♦; trump 2♣ can win
        # No danger player, trick isn't last play, so uses weakest trump winner
        assert is_trump(move.card, trump_suit)


# ---------------------------------------------------------------------------
# Enhancement 1: Card tracking / dominant lead
# ---------------------------------------------------------------------------


class TestEnhancedCardTracking:
    def test_leads_dominant_card(self) -> None:
        """Should lead from a suit where I hold the highest remaining card."""
        trump_suit = Suit.CLUBS
        # K♦ is the highest non-trump diamond that exists
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)
        two_spades = Card(Rank.TWO, Suit.SPADES)  # weak non-trump

        hand = (king_diamonds, two_spades)

        # All higher-ranked diamonds (none exist — K is the highest non-trump diamond)
        # so king_diamonds is automatically dominant; it is the best non-trump in ♦
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            completed_tricks=(),   # nothing played yet
            trick_number=1,
            opponents=(("P2", 0), ("P3", 0)),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # K♦ is dominant (it's the best diamond possible); should lead it
        assert move.card == king_diamonds

    def test_does_not_lead_dominated_card(self) -> None:
        """Should NOT lead a card if higher cards of the suit are still unplayed."""
        trump_suit = Suit.CLUBS
        # 2♦ is a weak diamond — K♦, Q♦, etc. still unplayed
        two_diamonds = Card(Rank.TWO, Suit.DIAMONDS)
        three_spades = Card(Rank.THREE, Suit.SPADES)

        hand = (two_diamonds, three_spades)
        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            completed_tricks=(),
            trick_number=1,
            opponents=(("P2", 0), ("P3", 0)),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # Neither card is dominant — fall back to weakest non-trump
        # Both are non-trump; pick the weakest
        non_trumps = [c for c in hand if not is_trump(c, trump_suit)]
        worst_rank = max(card_global_rank(c, trump_suit) for c in non_trumps)
        assert card_global_rank(move.card, trump_suit) == worst_rank

    def test_becomes_dominant_after_higher_cards_played(self) -> None:
        """After K♦ is played, Q♦ should become dominant in diamonds."""
        trump_suit = Suit.CLUBS
        queen_diamonds = Card(Rank.QUEEN, Suit.DIAMONDS)
        two_spades = Card(Rank.TWO, Suit.SPADES)

        hand = (queen_diamonds, two_spades)

        # Simulate K♦ having been played in a previous trick
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)
        completed_tricks = ((TrickPlay("P2", king_diamonds),),)

        state = make_state(
            hand=hand,
            trump_suit=trump_suit,
            completed_tricks=completed_tricks,
            trick_number=2,
            opponents=(("P2", 0), ("P3", 0)),
        )
        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # Q♦ is now dominant (K♦ was the only card above it, now played)
        assert move.card == queen_diamonds


# ---------------------------------------------------------------------------
# Round-end
# ---------------------------------------------------------------------------


class TestEnhancedRoundEnd:
    def test_confirm_round_end(self) -> None:
        engine = make_engine()
        advance_to_round_end(engine)
        state = engine.get_state()
        assert state.phase == Phase.ROUND_END

        player = EnhancedHeuristicPlayer()
        move = player.choose_move(state)
        assert isinstance(move, ConfirmRoundEnd)


# ---------------------------------------------------------------------------
# Legality: always returns a legal move
# ---------------------------------------------------------------------------


class TestEnhancedLegality:
    def test_move_is_always_legal_throughout_game(self) -> None:
        """EnhancedHeuristicPlayer must return a legal move in every state."""
        for seed in range(50):
            random.seed(seed)
            engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
            ai = EnhancedHeuristicPlayer()
            moves_played = 0
            while not engine.is_game_over and moves_played < 100:
                state = engine.get_state()
                move = ai.choose_move(state)
                assert move in state.legal_moves, (
                    f"Seed {seed}: AI returned {move!r} not in legal_moves"
                )
                engine.apply_move(move)
                moves_played += 1

    def test_game_reaches_game_over(self) -> None:
        """A full game with all EnhancedHeuristicPlayers must reach GAME_OVER."""
        random.seed(0)
        engine = GameEngine(["P1", "P2", "P3"], audit_dir=None)
        ai = EnhancedHeuristicPlayer()
        moves = 0
        while not engine.is_game_over and moves < 500:
            state = engine.get_state()
            engine.apply_move(ai.choose_move(state))
            moves += 1
        assert engine.is_game_over, "Game did not reach GAME_OVER"


# ---------------------------------------------------------------------------
# Enhancement 6: Let the safe player win
# ---------------------------------------------------------------------------


class TestEnhancedLetSafePlayerWin:
    def test_discards_when_danger_player_losing_and_only_trump_wins(self) -> None:
        """E6: danger player played and is losing; winning requires trump → discard."""
        trump_suit = Suit.CLUBS
        # P2 (danger, 20 pts) led 2♦ and is losing to P3's K♣ (trump)
        current_trick = (
            TrickPlay("P2", Card(Rank.TWO, Suit.DIAMONDS)),
            TrickPlay("P3", Card(Rank.KING, trump_suit)),  # K♣ currently winning
        )
        jack_clubs = Card(Rank.JACK, trump_suit)    # trump winner (rank 13)
        seven_diamonds = Card(Rank.SEVEN, Suit.DIAMONDS)  # non-trump loser

        state = make_state(
            hand=(jack_clubs, seven_diamonds),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(jack_clubs), PlayCard(seven_diamonds)),
            opponents=(("P2", 20), ("P3", 5)),
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # P2 (danger) is already losing — J♣ is too valuable to spend here; discard 7♦
        assert move.card == seven_diamonds

    def test_uses_non_trump_winner_when_danger_player_losing(self) -> None:
        """E6: danger player losing — take the trick with non-trump winner, not trump."""
        trump_suit = Suit.CLUBS
        # P2 (danger, 20 pts) led 2♦, P3 (safe) played 3♦ — P3 currently winning
        current_trick = (
            TrickPlay("P2", Card(Rank.TWO, Suit.DIAMONDS)),
            TrickPlay("P3", Card(Rank.THREE, Suit.DIAMONDS)),  # 3♦ > 2♦ in red non-trump
        )
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)  # non-trump winner
        five_clubs = Card(Rank.FIVE, trump_suit)        # trump winner (Five)

        state = make_state(
            hand=(king_diamonds, five_clubs),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(king_diamonds), PlayCard(five_clubs)),
            opponents=(("P2", 20), ("P3", 5)),
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # P2 (danger) is losing — non-trump K♦ wins cheaply; save the Five
        assert move.card == king_diamonds

    def test_still_wins_when_danger_player_not_yet_played(self) -> None:
        """E6: danger player hasn't played yet — E6 guard prevents passivity."""
        trump_suit = Suit.CLUBS
        # Only P3 (safe) has played so far; P2 (danger) hasn't acted
        current_trick = (TrickPlay("P3", Card(Rank.TWO, Suit.DIAMONDS)),)

        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)  # non-trump winner
        jack_clubs = Card(Rank.JACK, trump_suit)         # trump winner

        state = make_state(
            hand=(king_diamonds, jack_clubs),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(king_diamonds), PlayCard(jack_clubs)),
            opponents=(("P2", 20), ("P3", 5)),
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # E6 does not fire (P2 hasn't played). Enhancement 5 applies: non-trump winner first.
        assert move.card == king_diamonds

    def test_stops_danger_player_who_is_winning(self) -> None:
        """E6 must not suppress action when the danger player IS currently winning."""
        trump_suit = Suit.CLUBS
        # P2 (danger) led K♦ and is currently winning
        current_trick = (TrickPlay("P2", Card(Rank.KING, Suit.DIAMONDS)),)

        ace_diamonds = Card(Rank.ACE, Suit.DIAMONDS)  # red non-trump: A=rank 1 (weakest)
        jack_clubs = Card(Rank.JACK, trump_suit)       # trump winner

        state = make_state(
            hand=(ace_diamonds, jack_clubs),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(ace_diamonds), PlayCard(jack_clubs)),
            opponents=(("P2", 20), ("P3", 5)),
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # P2 is winning — E6 guard (not danger_winning) prevents passivity; play J♣
        assert move.card == jack_clubs

    def test_self_scoring_exception_bypasses_e6(self) -> None:
        """E6 must not fire when I am at >= 15 pts (play for myself instead)."""
        trump_suit = Suit.CLUBS
        # P2 (danger, 20 pts) played 2♦ and is losing to P3's K♣
        current_trick = (
            TrickPlay("P2", Card(Rank.TWO, Suit.DIAMONDS)),
            TrickPlay("P3", Card(Rank.KING, trump_suit)),
        )
        jack_clubs = Card(Rank.JACK, trump_suit)
        seven_diamonds = Card(Rank.SEVEN, Suit.DIAMONDS)

        state = make_state(
            score=15,   # I'm close to winning — should play for myself
            hand=(jack_clubs, seven_diamonds),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(jack_clubs), PlayCard(seven_diamonds)),
            opponents=(("P2", 20), ("P3", 5)),
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # At 15 pts myself, E6 is bypassed (my_score < 15 fails) — take trick with J♣
        assert move.card == jack_clubs

    def test_e6_does_not_fire_for_15pt_danger_only(self) -> None:
        """E6 must not fire when the only 'danger' player is a 15 pt score leader (not ≥20)."""
        trump_suit = Suit.CLUBS
        # P2 at 15 pts is flagged as danger by Enhancement 3 but NOT hard_danger
        current_trick = (
            TrickPlay("P2", Card(Rank.TWO, Suit.DIAMONDS)),
            TrickPlay("P3", Card(Rank.KING, trump_suit)),
        )
        jack_clubs = Card(Rank.JACK, trump_suit)
        seven_diamonds = Card(Rank.SEVEN, Suit.DIAMONDS)

        state = make_state(
            hand=(jack_clubs, seven_diamonds),
            trump_suit=trump_suit,
            current_trick=current_trick,
            legal_moves=(PlayCard(jack_clubs), PlayCard(seven_diamonds)),
            opponents=(("P2", 15), ("P3", 5)),   # P2 only at 15 pts, not 20
        )
        player = EnhancedHeuristicPlayer()
        player._e6_enabled = True
        move = player.choose_move(state)
        assert isinstance(move, PlayCard)
        # E6 doesn't fire (hard_danger empty — P2 only at 15 pts) — normal logic wins with J♣
        assert move.card == jack_clubs


# ---------------------------------------------------------------------------
# Enhancement 7: Avoid leading a weak trump against a danger player
# ---------------------------------------------------------------------------


class TestEnhancedWeakTrumpLead:
    def test_leads_non_trump_with_weak_trump_and_danger_player(self) -> None:
        """E7: best trump is below Q rank (rank < 9) → lead non-trump instead."""
        trump_suit = Suit.CLUBS
        # 8♣ has trump_rank 3 in clubs (well below the Q threshold of 9)
        eight_clubs = Card(Rank.EIGHT, trump_suit)
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        state = make_state(
            hand=(eight_clubs, king_diamonds),
            trump_suit=trump_suit,
            trick_number=4,   # E7 only fires in endgame (tricks 4–5)
            opponents=(("P2", 20), ("P3", 5)),
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        assert not is_trump(move.card, trump_suit), (
            f"Expected non-trump lead, got {move.card!r} (weak trump should be withheld)"
        )

    def test_leads_strong_trump_at_queen_threshold(self) -> None:
        """E7: trump at exactly Q rank (rank == 9) IS strong enough to lead."""
        trump_suit = Suit.CLUBS
        # Q♣ has trump_rank 9 — right at the threshold
        queen_clubs = Card(Rank.QUEEN, trump_suit)
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        state = make_state(
            hand=(queen_clubs, king_diamonds),
            trump_suit=trump_suit,
            trick_number=4,   # E7 only fires in endgame (tricks 4–5)
            opponents=(("P2", 20), ("P3", 5)),
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        assert move.card == queen_clubs, (
            f"Q♣ (rank 9) should trigger trump lead, got {move.card!r}"
        )

    def test_threshold_below_queen_prefers_non_trump(self) -> None:
        """E7: 2♣ has trump_rank 8 (just below Q) — should prefer non-trump lead."""
        trump_suit = Suit.CLUBS
        # 2♣ is the strongest numeric club (rank 8) but still below the Q threshold
        two_clubs = Card(Rank.TWO, trump_suit)
        seven_hearts = Card(Rank.SEVEN, Suit.HEARTS)  # non-trump (Hearts when trump=Clubs)

        state = make_state(
            hand=(two_clubs, seven_hearts),
            trump_suit=trump_suit,
            trick_number=4,   # E7 only fires in endgame (tricks 4–5)
            opponents=(("P2", 20), ("P3", 5)),
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        assert not is_trump(move.card, trump_suit), (
            f"2♣ rank 8 < 9 threshold — should lead non-trump, got {move.card!r}"
        )

    def test_leads_weak_trump_when_no_non_trump_available(self) -> None:
        """E7: only trumps in hand — forced to lead trump even if weak."""
        trump_suit = Suit.CLUBS
        eight_clubs = Card(Rank.EIGHT, trump_suit)  # rank 3
        nine_clubs = Card(Rank.NINE, trump_suit)    # rank 2

        state = make_state(
            hand=(eight_clubs, nine_clubs),
            trump_suit=trump_suit,
            trick_number=4,   # E7 only fires in endgame; test the no-non-trump fallback
            opponents=(("P2", 20), ("P3", 5)),
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        # Only trumps available — must lead trump regardless of weakness
        assert is_trump(move.card, trump_suit)

    def test_no_restriction_without_danger_player(self) -> None:
        """E7 only applies when a danger player is present; no danger → normal logic."""
        trump_suit = Suit.CLUBS
        eight_clubs = Card(Rank.EIGHT, trump_suit)
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        state = make_state(
            hand=(eight_clubs, king_diamonds),
            trump_suit=trump_suit,
            opponents=(("P2", 5), ("P3", 0)),   # no danger player
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        # No danger player: normal conservative fallback or card tracking.
        # K♦ is dominant (highest diamond) → leads K♦ anyway; either way non-trump
        assert not is_trump(move.card, trump_suit)

    def test_self_scoring_exception_bypasses_e7(self) -> None:
        """E7 must not fire when I am at >= 15 pts (play aggressively for myself)."""
        trump_suit = Suit.CLUBS
        eight_clubs = Card(Rank.EIGHT, trump_suit)   # rank 3 — would normally be suppressed
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        state = make_state(
            score=15,   # close to winning — bypass E7
            hand=(eight_clubs, king_diamonds),
            trump_suit=trump_suit,
            trick_number=4,   # endgame, so E7 would fire absent the self-scoring exception
            opponents=(("P2", 20), ("P3", 5)),
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        # At 15 pts myself, E7 is bypassed — lead strongest trump (8♣) to score
        assert move.card == eight_clubs

    def test_e7_does_not_fire_for_15pt_danger_only(self) -> None:
        """E7 must not fire when the only 'danger' is a 15 pt score leader (not ≥20)."""
        trump_suit = Suit.CLUBS
        eight_clubs = Card(Rank.EIGHT, trump_suit)   # rank 3
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        state = make_state(
            hand=(eight_clubs, king_diamonds),
            trump_suit=trump_suit,
            trick_number=4,   # endgame, so E7 would fire if hard_danger were set
            opponents=(("P2", 15), ("P3", 5)),   # P2 only at 15 pts, not 20
        )
        move = EnhancedHeuristicPlayer().choose_move(state)
        assert isinstance(move, PlayCard)
        # P2 not in hard_danger → E7 inactive; enhancement 3 danger → leads trump
        assert move.card == eight_clubs

    def test_e7_inactive_in_early_tricks(self) -> None:
        """E7 only fires in tricks 4–5; early tricks lead trump normally against danger."""
        trump_suit = Suit.CLUBS
        # 8♣ rank 3 — weak trump that E7 would suppress in endgame
        eight_clubs = Card(Rank.EIGHT, trump_suit)
        king_diamonds = Card(Rank.KING, Suit.DIAMONDS)

        for trick_number in (1, 2, 3):
            state = make_state(
                hand=(eight_clubs, king_diamonds),
                trump_suit=trump_suit,
                trick_number=trick_number,
                opponents=(("P2", 20), ("P3", 5)),
            )
            move = EnhancedHeuristicPlayer().choose_move(state)
            assert isinstance(move, PlayCard)
            assert is_trump(move.card, trump_suit), (
                f"Trick {trick_number}: E7 should be inactive; "
                f"expected trump lead, got {move.card!r}"
            )
