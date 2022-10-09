import pyCardDeck
from pyCardDeck.cards import PokerCard
from typing import List
from twentyfive.common.player import Player
from twentyfive.common.table import Table


class Game:

    def __init__(self, table):

        self.table = table
        print("Created a game with {} players".format(len(self.table.getPlayers())))
        self.table.getDeck().shuffle()
        print("Deck Shuffled")

    def dealCards(self,number):
        """
        Dealer will go through all available players and deal them x number of cards.

        :param number:  How many cards to deal
        :type number:   int
        """    
        for player in self.table.getPlayers():
            for _ in range(0, number):
                deck = self.table.getDeck()
                card = deck.draw()
                player.hand.append(card)
                print("Dealt {} to player {}".format(card, player))
