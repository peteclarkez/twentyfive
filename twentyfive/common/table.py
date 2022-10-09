import pyCardDeck
from pyCardDeck.cards import PokerCard
from typing import List
from examples.poker import generate_deck
from twentyfive.common.player import Player

class Table:

    def __init__(self, players: List[Player]):

        self.deck = pyCardDeck.Deck(
            cards = self.generate_deck(),
            name='twenty five deck',
            reshuffle=False)        
        self.players = players

        #self.table_cards = []
        
        print("Created a table with {} players".format(len(self.players)))

    
    def generate_deck(self) -> List[PokerCard]:
        """
        Function that generates the deck, instead of writing down 50 cards, we use iteration
        to generate the cards for use

        :return:    List with all 50 poker playing cards
        :rtype:     List[PokerCard]
        """
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = {'A': 'Ace',
                '2': 'Two',
                '3': 'Three',
                '4': 'Four',
                '5': 'Five',
                '6': 'Six',
                '7': 'Seven',
                '8': 'Eight',
                '9': 'Nine',
                '10': 'Ten',
                'J': 'Jack',
                'Q': 'Queen',
                'K': 'King'}
        cards = []
        for suit in suits:
            for rank, name in ranks.items():
                cards.append(PokerCard(suit, rank, name))
        print('Generated deck of cards for the table')
        return cards

    def getPlayers(self):
        return self.players

    def getDeck(self):
        return self.deck