"""
Tests for game/rules.py — the most critical module.
Covers trump ranking, non-trump ranking, legal move computation, and trick winners.
"""

import pytest

from twentyfive.cards.card import ACE_OF_HEARTS, Card, Rank, Suit
from twentyfive.game.rules import (
    card_global_rank,
    get_legal_cards,
    get_legal_rob_moves,
    get_renegeable_cards,
    non_trump_rank,
    trick_winner,
    trump_rank,
)
from twentyfive.game.state import PassRob, Rob, TrickPlay

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def c(rank: Rank, suit: Suit) -> Card:
    return Card(rank, suit)


def play(player: str, rank: Rank, suit: Suit) -> TrickPlay:
    return TrickPlay(player_name=player, card=Card(rank, suit))


# ---------------------------------------------------------------------------
# Trump rank table
# ---------------------------------------------------------------------------


class TestTrumpRank:
    def test_five_is_highest_for_all_trumps(self) -> None:
        for suit in Suit:
            five = Card(Rank.FIVE, suit)
            jack = Card(Rank.JACK, suit)
            assert trump_rank(five, suit) > trump_rank(jack, suit)

    def test_jack_beats_ace_of_hearts(self) -> None:
        for suit in Suit:
            jack = Card(Rank.JACK, suit)
            assert trump_rank(jack, suit) > trump_rank(ACE_OF_HEARTS, suit)

    def test_ace_of_hearts_beats_ace_of_non_hearts_trump(self) -> None:
        for suit in [Suit.CLUBS, Suit.DIAMONDS, Suit.SPADES]:
            ace_trump = Card(Rank.ACE, suit)
            assert trump_rank(ACE_OF_HEARTS, suit) > trump_rank(ace_trump, suit)

    def test_hearts_trump_has_no_ace_of_trump_at_rank_11(self) -> None:
        # When hearts is trump, A♥ serves as both the "ace of trumps" and the A♥ constant.
        # There should be no separate rank-11 entry — only rank-12 for A♥.
        from twentyfive.game.rules import _TRUMP_RANKS

        hearts_entries = {
            card: rank for (suit, card), rank in _TRUMP_RANKS.items() if suit == Suit.HEARTS
        }
        # A♥ should appear exactly once for hearts trump
        ace_hearts_ranks = [r for c, r in hearts_entries.items() if c == ACE_OF_HEARTS]
        assert len(ace_hearts_ranks) == 1
        assert ace_hearts_ranks[0] == 12

    def test_hearts_trump_table_has_13_entries(self) -> None:
        from twentyfive.game.rules import _TRUMP_RANKS

        hearts_entries = [
            (card, rank) for (suit, card), rank in _TRUMP_RANKS.items() if suit == Suit.HEARTS
        ]
        assert len(hearts_entries) == 13

    def test_non_hearts_trump_table_has_14_entries(self) -> None:
        from twentyfive.game.rules import _TRUMP_RANKS

        for suit in [Suit.CLUBS, Suit.DIAMONDS, Suit.SPADES]:
            entries = [(card, rank) for (s, card), rank in _TRUMP_RANKS.items() if s == suit]
            assert len(entries) == 14, f"Expected 14 trump entries for {suit}, got {len(entries)}"

    def test_king_beats_queen_of_trump(self) -> None:
        for suit in Suit:
            king = Card(Rank.KING, suit)
            queen = Card(Rank.QUEEN, suit)
            assert trump_rank(king, suit) > trump_rank(queen, suit)

    def test_black_trump_low_numerics_beat_high(self) -> None:
        # For black suits: 2 is stronger than 10 among lower trumps
        for suit in [Suit.CLUBS, Suit.SPADES]:
            two = Card(Rank.TWO, suit)
            ten = Card(Rank.TEN, suit)
            msg = f"2{suit.symbol} should beat 10{suit.symbol}"
            assert trump_rank(two, suit) > trump_rank(ten, suit), msg

    def test_red_trump_high_numerics_beat_low(self) -> None:
        # For red suits: 10 is stronger than 2 among lower trumps
        for suit in [Suit.HEARTS, Suit.DIAMONDS]:
            ten = Card(Rank.TEN, suit)
            two = Card(Rank.TWO, suit)
            msg = f"10{suit.symbol} should beat 2{suit.symbol}"
            assert trump_rank(ten, suit) > trump_rank(two, suit), msg

    def test_ace_of_hearts_trump_rank_for_each_trump_suit(self) -> None:
        # A♥ should have rank 12 for all trump suits
        for suit in Suit:
            assert trump_rank(ACE_OF_HEARTS, suit) == 12

    def test_non_trump_card_raises(self) -> None:
        # K♥ is not trump when clubs is trump
        with pytest.raises(KeyError):
            trump_rank(Card(Rank.KING, Suit.HEARTS), Suit.CLUBS)

    def test_clubs_trump_full_order(self) -> None:
        """Verify the complete ordering for clubs trump matches RULES.md."""
        trump = Suit.CLUBS
        expected_order = [
            Card(Rank.FIVE, Suit.CLUBS),   # 14
            Card(Rank.JACK, Suit.CLUBS),   # 13
            ACE_OF_HEARTS,                 # 12
            Card(Rank.ACE, Suit.CLUBS),    # 11
            Card(Rank.KING, Suit.CLUBS),   # 10
            Card(Rank.QUEEN, Suit.CLUBS),  # 9
            Card(Rank.TWO, Suit.CLUBS),    # 8
            Card(Rank.THREE, Suit.CLUBS),  # 7
            Card(Rank.FOUR, Suit.CLUBS),   # 6
            Card(Rank.SIX, Suit.CLUBS),    # 5
            Card(Rank.SEVEN, Suit.CLUBS),  # 4
            Card(Rank.EIGHT, Suit.CLUBS),  # 3
            Card(Rank.NINE, Suit.CLUBS),   # 2
            Card(Rank.TEN, Suit.CLUBS),    # 1
        ]
        ranks = [trump_rank(card, trump) for card in expected_order]
        assert ranks == sorted(ranks, reverse=True), "Clubs trump ordering is wrong"

    def test_hearts_trump_full_order(self) -> None:
        """Verify the complete ordering for hearts trump matches RULES.md."""
        trump = Suit.HEARTS
        expected_order = [
            Card(Rank.FIVE, Suit.HEARTS),   # 14
            Card(Rank.JACK, Suit.HEARTS),   # 13
            ACE_OF_HEARTS,                  # 12 — no separate rank-11 Ace for hearts
            Card(Rank.KING, Suit.HEARTS),   # 10
            Card(Rank.QUEEN, Suit.HEARTS),  # 9
            Card(Rank.TEN, Suit.HEARTS),    # 8
            Card(Rank.NINE, Suit.HEARTS),   # 7
            Card(Rank.EIGHT, Suit.HEARTS),  # 6
            Card(Rank.SEVEN, Suit.HEARTS),  # 5
            Card(Rank.SIX, Suit.HEARTS),    # 4
            Card(Rank.FOUR, Suit.HEARTS),   # 3
            Card(Rank.THREE, Suit.HEARTS),  # 2
            Card(Rank.TWO, Suit.HEARTS),    # 1
        ]
        ranks = [trump_rank(card, trump) for card in expected_order]
        assert ranks == sorted(ranks, reverse=True), "Hearts trump ordering is wrong"


# ---------------------------------------------------------------------------
# Non-trump rank
# ---------------------------------------------------------------------------


class TestNonTrumpRank:
    def test_red_king_is_highest(self) -> None:
        for suit in [Suit.HEARTS, Suit.DIAMONDS]:
            assert non_trump_rank(Card(Rank.KING, suit)) == 13

    def test_red_ace_is_lowest(self) -> None:
        assert non_trump_rank(Card(Rank.ACE, Suit.DIAMONDS)) == 1
        # A♥ is never non-trump, so we only test diamonds ace here

    def test_black_king_is_highest(self) -> None:
        for suit in [Suit.CLUBS, Suit.SPADES]:
            assert non_trump_rank(Card(Rank.KING, suit)) == 13

    def test_black_ace_beats_numerics(self) -> None:
        # In black suits, Ace ranks 4th (above 2)
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.CLUBS)
        ten = Card(Rank.TEN, Suit.CLUBS)
        assert non_trump_rank(ace) > non_trump_rank(two)
        assert non_trump_rank(ace) > non_trump_rank(ten)

    def test_black_ten_is_lowest(self) -> None:
        assert non_trump_rank(Card(Rank.TEN, Suit.CLUBS)) == 1
        assert non_trump_rank(Card(Rank.TEN, Suit.SPADES)) == 1

    def test_red_natural_order(self) -> None:
        # K > Q > J > 10 for red suits
        suits = [Suit.DIAMONDS]  # hearts 10 is fine since non-trump context
        for suit in suits:
            assert non_trump_rank(Card(Rank.KING, suit)) > non_trump_rank(Card(Rank.QUEEN, suit))
            assert non_trump_rank(Card(Rank.QUEEN, suit)) > non_trump_rank(Card(Rank.JACK, suit))
            assert non_trump_rank(Card(Rank.JACK, suit)) > non_trump_rank(Card(Rank.TEN, suit))


# ---------------------------------------------------------------------------
# get_legal_cards — leading
# ---------------------------------------------------------------------------


class TestGetLegalCardsLead:
    def test_leader_can_play_any_card(self) -> None:
        hand = [Card(Rank.KING, Suit.HEARTS), Card(Rank.TWO, Suit.CLUBS), ACE_OF_HEARTS]
        legal = get_legal_cards(hand, None, Suit.CLUBS)
        assert set(legal) == set(hand)


# ---------------------------------------------------------------------------
# get_legal_cards — non-trump lead
# ---------------------------------------------------------------------------


class TestGetLegalCardsNonTrumpLead:
    def test_must_follow_suit_or_may_trump(self) -> None:
        # Led: 3♥ (hearts non-trump), trump: clubs — K♥ follows suit; A♣ is trump (may-trump)
        hand = [
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.QUEEN, Suit.DIAMONDS),
        ]
        led = Card(Rank.THREE, Suit.HEARTS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        # May-trump: K♥ (follows suit) and A♣ (trump) both legal; Q♦ (neither) is not
        assert set(legal) == {Card(Rank.KING, Suit.HEARTS), Card(Rank.ACE, Suit.CLUBS)}

    def test_void_in_led_suit_any_card_legal(self) -> None:
        # Led: 3♦ (diamonds non-trump), trump: clubs — void in diamonds → any card legal
        hand = [ACE_OF_HEARTS, Card(Rank.QUEEN, Suit.SPADES)]
        led = Card(Rank.THREE, Suit.DIAMONDS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        # Void in led suit → any card legal (trumping is optional)
        assert set(legal) == set(hand)

    def test_void_in_led_suit_plays_freely(self) -> None:
        # Led: 3♥ (hearts non-trump), trump: clubs — hand has only diamonds
        hand = [Card(Rank.KING, Suit.DIAMONDS), Card(Rank.TWO, Suit.DIAMONDS)]
        led = Card(Rank.THREE, Suit.HEARTS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        assert set(legal) == set(hand)

    def test_may_trump_when_holding_led_suit_and_trump(self) -> None:
        # Player holds both led suit and a trump — both are legal (may-trump rule)
        hand = [Card(Rank.KING, Suit.HEARTS), Card(Rank.TWO, Suit.CLUBS)]
        led = Card(Rank.THREE, Suit.HEARTS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        # May-trump: K♥ (follows suit) and 2♣ (trump) both legal
        assert set(legal) == {Card(Rank.KING, Suit.HEARTS), Card(Rank.TWO, Suit.CLUBS)}

    def test_void_in_led_suit_trump_is_optional(self) -> None:
        # Hand has only trumps, void in led suit — all cards legal (trump not forced)
        hand = [Card(Rank.TWO, Suit.CLUBS), Card(Rank.KING, Suit.CLUBS)]
        led = Card(Rank.THREE, Suit.HEARTS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        assert set(legal) == set(hand)

    def test_ace_of_hearts_follows_suit_when_hearts_led(self) -> None:
        # Led: 3♥ (non-trump, clubs trump) — A♥ has suit hearts, counts as following suit
        hand = [ACE_OF_HEARTS, Card(Rank.KING, Suit.SPADES)]
        led = Card(Rank.THREE, Suit.HEARTS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        # A♥ is hearts-suited → follows suit. K♠ is neither → not legal.
        assert set(legal) == {ACE_OF_HEARTS}

    def test_void_in_non_hearts_led_suit_ace_of_hearts_optional(self) -> None:
        # Led: 3♦ (diamonds non-trump, clubs trump) — void in diamonds → any card legal
        hand = [ACE_OF_HEARTS, Card(Rank.KING, Suit.SPADES)]
        led = Card(Rank.THREE, Suit.DIAMONDS)
        legal = get_legal_cards(hand, led, Suit.CLUBS)
        # Void in diamonds → all cards legal; A♥ is optional, not forced
        assert set(legal) == set(hand)


# ---------------------------------------------------------------------------
# get_legal_cards — trump lead + reneging
# ---------------------------------------------------------------------------


class TestGetLegalCardsTrumpLead:
    def test_five_leads_nothing_can_be_reneged(self) -> None:
        # 5♣ leads → all players must follow trump; no card outranks it
        trump = Suit.CLUBS
        hand = [Card(Rank.JACK, trump), ACE_OF_HEARTS, Card(Rank.KING, trump)]
        led = Card(Rank.FIVE, trump)
        legal = get_legal_cards(hand, led, trump)
        # All are trumps and all have lower rank than 5 — all forced
        assert set(legal) == set(hand)

    def test_jack_leads_only_five_can_be_reneged(self) -> None:
        # J♣ leads (rank 13) → 5♣ (rank 14) may be reneged; A♥ (rank 12) is forced
        trump = Suit.CLUBS
        hand = [Card(Rank.FIVE, trump), ACE_OF_HEARTS, Card(Rank.KING, trump)]
        led = Card(Rank.JACK, trump)
        legal = get_legal_cards(hand, led, trump)
        # A♥ (rank 12) <= 13 → forced. K♣ (rank 10) <= 13 → forced.
        # Since forced is non-empty, all trumps are legal (including renegeable 5♣)
        assert set(legal) == set(hand)

    def test_ace_of_hearts_leads_five_and_jack_can_be_reneged(self) -> None:
        # A♥ leads (rank 12) → 5♣ (rank 14) and J♣ (rank 13) may be reneged
        trump = Suit.CLUBS
        hand = [Card(Rank.FIVE, trump), Card(Rank.JACK, trump), Card(Rank.KING, trump)]
        led = ACE_OF_HEARTS
        legal = get_legal_cards(hand, led, trump)
        # K♣ (rank 10) <= 12 → forced. Since forced non-empty, all trumps legal.
        assert set(legal) == set(hand)

    def test_renege_entirely_when_holding_only_top3(self) -> None:
        # Lower trump leads; player holds only 5 and Jack (both renegeable)
        trump = Suit.CLUBS
        hand = [Card(Rank.FIVE, trump), Card(Rank.JACK, trump), Card(Rank.QUEEN, Suit.HEARTS)]
        led = Card(Rank.KING, trump)  # rank 10
        legal = get_legal_cards(hand, led, trump)
        # 5♣ rank 14 > 10 → renegeable. J♣ rank 13 > 10 → renegeable.
        # forced = [] → any card is legal
        assert set(legal) == set(hand)

    def test_forced_trump_with_renegeable_also_present(self) -> None:
        # K♣ leads (rank 10); hand has 5♣ (renegeable, rank 14) and Q♣ (forced, rank 9)
        trump = Suit.CLUBS
        hand = [Card(Rank.FIVE, trump), Card(Rank.QUEEN, trump)]
        led = Card(Rank.KING, trump)  # rank 10
        legal = get_legal_cards(hand, led, trump)
        # Q♣ rank 9 <= 10 → forced. Since forced non-empty, legal = all trumps = both cards
        assert set(legal) == set(hand)

    def test_no_trumps_in_hand_when_trump_led(self) -> None:
        trump = Suit.CLUBS
        hand = [Card(Rank.KING, Suit.HEARTS), Card(Rank.QUEEN, Suit.DIAMONDS)]
        led = Card(Rank.THREE, trump)
        legal = get_legal_cards(hand, led, trump)
        assert set(legal) == set(hand)

    def test_lower_trump_leads_higher_trump_must_be_played(self) -> None:
        # Q♣ leads (rank 9); hand has K♣ (rank 10) and a non-trump
        trump = Suit.CLUBS
        hand = [Card(Rank.KING, trump), Card(Rank.FIVE, Suit.HEARTS)]
        led = Card(Rank.QUEEN, trump)
        legal = get_legal_cards(hand, led, trump)
        # K♣ is not in top-3, so it is FORCED even though its rank (10) > led rank (9).
        # forced = [K♣] → must play trump → legal = {K♣} only
        assert set(legal) == {Card(Rank.KING, trump)}

    def test_ace_of_hearts_in_hand_trump_led_non_hearts_suit(self) -> None:
        # A♥ is trump when clubs is trump; a trump lead forces it unless it's renegeable
        trump = Suit.CLUBS
        hand = [ACE_OF_HEARTS, Card(Rank.TWO, Suit.DIAMONDS)]
        led = Card(Rank.QUEEN, trump)  # rank 9
        # A♥ trump_rank = 12 > 9 → renegeable. forced = []. Legal = all cards.
        legal = get_legal_cards(hand, led, trump)
        assert set(legal) == set(hand)


# ---------------------------------------------------------------------------
# get_renegeable_cards
# ---------------------------------------------------------------------------


class TestGetRenegeable:
    def test_no_led_card_returns_empty(self) -> None:
        hand = [Card(Rank.FIVE, Suit.CLUBS), Card(Rank.JACK, Suit.CLUBS)]
        assert get_renegeable_cards(hand, None, Suit.CLUBS) == frozenset()

    def test_non_trump_led_returns_empty(self) -> None:
        hand = [Card(Rank.FIVE, Suit.CLUBS), Card(Rank.JACK, Suit.CLUBS)]
        led = Card(Rank.KING, Suit.HEARTS)
        assert get_renegeable_cards(hand, led, Suit.CLUBS) == frozenset()

    def test_forced_only_returns_empty(self) -> None:
        # Led J♣ (rank 13); hand has only K♣ (rank 10) — forced, nothing renegeable
        trump = Suit.CLUBS
        hand = [Card(Rank.KING, trump)]
        led = Card(Rank.JACK, trump)
        assert get_renegeable_cards(hand, led, trump) == frozenset()

    def test_mixed_forced_and_renegeable(self) -> None:
        # Led K♣ (rank 10); 5♣ (rank 14) renegeable, Q♣ (rank 9) forced
        trump = Suit.CLUBS
        five = Card(Rank.FIVE, trump)
        queen = Card(Rank.QUEEN, trump)
        hand = [five, queen]
        led = Card(Rank.KING, trump)  # rank 10
        result = get_renegeable_cards(hand, led, trump)
        assert result == frozenset({five})

    def test_top3_renegeable_non_top3_is_not(self) -> None:
        # Led 8♦ (rank 6); player has 5♦(14), J♦(13), 9♦(7) — all outrank led trump
        # Bug case from game be2fc7ce R2T1: only top-3 cards (5♦, J♦) are renegeable;
        # 9♦ outranks led but is NOT top-3 so it is forced, not renegeable.
        trump = Suit.DIAMONDS
        five = Card(Rank.FIVE, trump)
        jack = Card(Rank.JACK, trump)
        nine = Card(Rank.NINE, trump)
        hand = [five, jack, nine, Card(Rank.NINE, Suit.CLUBS), Card(Rank.EIGHT, Suit.HEARTS)]
        led = Card(Rank.EIGHT, trump)  # rank 6
        result = get_renegeable_cards(hand, led, trump)
        assert result == frozenset({five, jack})

    def test_five_leads_nothing_renegeable(self) -> None:
        # 5♣ (rank 14) is the highest trump — nothing outranks it
        trump = Suit.CLUBS
        hand = [Card(Rank.JACK, trump), ACE_OF_HEARTS, Card(Rank.KING, trump)]
        led = Card(Rank.FIVE, trump)
        assert get_renegeable_cards(hand, led, trump) == frozenset()

    def test_non_top3_trump_is_forced_even_when_above_led(self) -> None:
        # Exact bug scenario: 8♦ led (rank 6), player has 5♦(14), J♦(13), 9♦(7)
        # 9♦ outranks 8♦ by rank, but is NOT top-3 → forced.
        # legal = all trumps {5♦, J♦, 9♦}; renege labels only on {5♦, J♦}
        trump = Suit.DIAMONDS
        five = Card(Rank.FIVE, trump)
        jack = Card(Rank.JACK, trump)
        nine = Card(Rank.NINE, trump)
        other = Card(Rank.NINE, Suit.CLUBS)
        hand = [five, jack, nine, other]
        led = Card(Rank.EIGHT, trump)  # rank 6
        # Legal: nine is forced → must play trump → all trumps available
        assert set(get_legal_cards(hand, led, trump)) == {five, jack, nine}
        # Renege labels: only top-3 cards that outrank led
        assert get_renegeable_cards(hand, led, trump) == frozenset({five, jack})


# ---------------------------------------------------------------------------
# get_legal_rob_moves
# ---------------------------------------------------------------------------


class TestGetLegalRobMoves:
    def test_non_dealer_with_ace_of_trump_is_eligible(self) -> None:
        trump = Suit.CLUBS
        face_up = Card(Rank.KING, trump)
        hand = [Card(Rank.ACE, trump), Card(Rank.QUEEN, Suit.HEARTS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=False)
        assert PassRob() in moves
        # Discard options are from current hand only (not the face-up card)
        rob_discards = {m.discard for m in moves if isinstance(m, Rob)}
        assert rob_discards == set(hand)

    def test_non_dealer_without_ace_of_trump_is_not_eligible(self) -> None:
        trump = Suit.CLUBS
        face_up = Card(Rank.KING, trump)
        hand = [Card(Rank.QUEEN, Suit.HEARTS), Card(Rank.TEN, Suit.DIAMONDS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=False)
        assert moves == [PassRob()]

    def test_dealer_eligible_when_face_up_is_ace_of_trump(self) -> None:
        trump = Suit.CLUBS
        face_up = Card(Rank.ACE, trump)
        hand = [Card(Rank.KING, Suit.HEARTS), Card(Rank.TWO, Suit.DIAMONDS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=True)
        assert PassRob() in moves
        # Discard from current hand only — cannot discard the ace you are taking
        rob_discards = {m.discard for m in moves if isinstance(m, Rob)}
        assert rob_discards == set(hand)

    def test_dealer_not_eligible_when_face_up_is_not_ace(self) -> None:
        trump = Suit.CLUBS
        face_up = Card(Rank.KING, trump)
        hand = [Card(Rank.QUEEN, Suit.HEARTS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=True)
        assert moves == [PassRob()]

    def test_hearts_trump_ace_of_hearts_as_face_up_dealer_eligible(self) -> None:
        # When trump is hearts, A♥ is the Ace of trumps — dealer may rob it
        trump = Suit.HEARTS
        face_up = ACE_OF_HEARTS
        hand = [Card(Rank.KING, Suit.CLUBS), Card(Rank.TWO, Suit.DIAMONDS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=True)
        assert any(isinstance(m, Rob) for m in moves)

    def test_rob_discard_excludes_face_up_card(self) -> None:
        # Player discards from their hand BEFORE taking; cannot discard the face-up card
        trump = Suit.CLUBS
        face_up = Card(Rank.KING, trump)
        hand = [Card(Rank.ACE, trump), Card(Rank.QUEEN, Suit.HEARTS)]
        moves = get_legal_rob_moves(hand, face_up, trump, is_dealer=False)
        assert Rob(discard=face_up) not in moves


# ---------------------------------------------------------------------------
# trick_winner
# ---------------------------------------------------------------------------


class TestTrickWinner:
    def test_highest_card_of_led_suit_wins_when_no_trump(self) -> None:
        plays = [
            TrickPlay("A", Card(Rank.KING, Suit.HEARTS)),
            TrickPlay("B", Card(Rank.JACK, Suit.HEARTS)),
            TrickPlay("C", Card(Rank.TWO, Suit.HEARTS)),
        ]
        winner = trick_winner(plays, Suit.HEARTS, Suit.CLUBS)
        assert winner.player_name == "A"

    def test_trump_beats_led_suit(self) -> None:
        plays = [
            TrickPlay("A", Card(Rank.KING, Suit.HEARTS)),
            TrickPlay("B", Card(Rank.TWO, Suit.CLUBS)),
        ]
        winner = trick_winner(plays, Suit.HEARTS, Suit.CLUBS)
        assert winner.player_name == "B"

    def test_highest_trump_wins_among_multiple_trumps(self) -> None:
        trump = Suit.CLUBS
        plays = [
            TrickPlay("A", Card(Rank.KING, trump)),   # rank 10
            TrickPlay("B", Card(Rank.QUEEN, trump)),  # rank 9
            TrickPlay("C", Card(Rank.ACE, trump)),    # rank 11
        ]
        winner = trick_winner(plays, trump, trump)
        assert winner.player_name == "C"

    def test_ace_of_hearts_beats_king_of_hearts_when_non_hearts_trump(self) -> None:
        # A♥ is trump (clubs trump); K♥ is non-trump. A♥ wins.
        plays = [
            TrickPlay("A", Card(Rank.KING, Suit.HEARTS)),
            TrickPlay("B", ACE_OF_HEARTS),
        ]
        winner = trick_winner(plays, Suit.HEARTS, Suit.CLUBS)
        assert winner.player_name == "B"

    def test_off_suit_non_trump_cannot_win(self) -> None:
        # Led hearts, clubs trump — B plays K♦ which cannot win
        plays = [
            TrickPlay("A", Card(Rank.FIVE, Suit.HEARTS)),
            TrickPlay("B", Card(Rank.KING, Suit.DIAMONDS)),
            TrickPlay("C", Card(Rank.THREE, Suit.HEARTS)),
        ]
        winner = trick_winner(plays, Suit.HEARTS, Suit.CLUBS)
        assert winner.player_name == "A"

    def test_five_of_trumps_beats_everything(self) -> None:
        trump = Suit.SPADES
        plays = [
            TrickPlay("A", Card(Rank.FIVE, trump)),
            TrickPlay("B", Card(Rank.JACK, trump)),
            TrickPlay("C", ACE_OF_HEARTS),
        ]
        winner = trick_winner(plays, trump, trump)
        assert winner.player_name == "A"

    def test_jack_of_trumps_beats_ace_of_hearts(self) -> None:
        trump = Suit.DIAMONDS
        plays = [
            TrickPlay("A", Card(Rank.JACK, trump)),
            TrickPlay("B", ACE_OF_HEARTS),
        ]
        winner = trick_winner(plays, trump, trump)
        assert winner.player_name == "A"

    def test_led_suit_winner_when_multiple_led_suit_played(self) -> None:
        # No trump played; multiple hearts played
        plays = [
            TrickPlay("A", Card(Rank.SEVEN, Suit.HEARTS)),
            TrickPlay("B", Card(Rank.QUEEN, Suit.HEARTS)),
            TrickPlay("C", Card(Rank.FOUR, Suit.HEARTS)),
        ]
        winner = trick_winner(plays, Suit.HEARTS, Suit.CLUBS)
        assert winner.player_name == "B"

    def test_black_suit_non_trump_rank_ordering(self) -> None:
        # In black suits, Ace beats numerics but Jack > Ace
        plays = [
            TrickPlay("A", Card(Rank.ACE, Suit.SPADES)),
            TrickPlay("B", Card(Rank.JACK, Suit.SPADES)),
        ]
        winner = trick_winner(plays, Suit.SPADES, Suit.CLUBS)
        assert winner.player_name == "B"

    def test_black_suit_ace_beats_ten(self) -> None:
        plays = [
            TrickPlay("A", Card(Rank.ACE, Suit.CLUBS)),
            TrickPlay("B", Card(Rank.TEN, Suit.CLUBS)),
        ]
        winner = trick_winner(plays, Suit.CLUBS, Suit.HEARTS)
        assert winner.player_name == "A"


# ---------------------------------------------------------------------------
# card_global_rank
# ---------------------------------------------------------------------------


class TestCardGlobalRank:
    def test_five_of_trump_is_rank_1(self) -> None:
        for suit in Suit:
            assert card_global_rank(Card(Rank.FIVE, suit), suit) == 1

    def test_jack_of_trump_is_rank_2(self) -> None:
        for suit in Suit:
            assert card_global_rank(Card(Rank.JACK, suit), suit) == 2

    def test_ace_of_hearts_is_rank_3(self) -> None:
        for suit in Suit:
            assert card_global_rank(ACE_OF_HEARTS, suit) == 3

    def test_ace_of_trump_is_rank_4_for_non_hearts_trump(self) -> None:
        for suit in (Suit.CLUBS, Suit.DIAMONDS, Suit.SPADES):
            assert card_global_rank(Card(Rank.ACE, suit), suit) == 4

    def test_trump_always_ranks_above_non_trump(self) -> None:
        trump = Suit.CLUBS
        weakest_trump = Card(Rank.TEN, trump)   # 10♣ has trump_rank 1 = last trump
        best_non_trump = Card(Rank.KING, Suit.HEARTS)
        assert card_global_rank(weakest_trump, trump) < card_global_rank(best_non_trump, trump)

    def test_rank_changes_with_trump_suit(self) -> None:
        # 5♣ is rank 1 under clubs trump, but not under spades trump
        five_clubs = Card(Rank.FIVE, Suit.CLUBS)
        assert card_global_rank(five_clubs, Suit.CLUBS) == 1
        assert card_global_rank(five_clubs, Suit.SPADES) > 1

    def test_all_52_cards_have_unique_rank_per_trump(self) -> None:
        for trump_suit in Suit:
            all_cards = [Card(r, s) for s in Suit for r in Rank]
            ranks = [card_global_rank(c, trump_suit) for c in all_cards]
            assert sorted(ranks) == list(range(1, 53))
