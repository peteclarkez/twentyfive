
class Player:

    def __init__(self, name: str):
        self.hand = []
        self.name = name

    def __str__(self):
        return self.name

    def pickup(self,card):
        self.hand.append(card)

    def putdown(self,card):
        self.hand.remove(card)

    def printHand(self):
        print("Player {} is holding [ ".format(self.name))
        for card in self.hand:                        
            print("   {} ".format(card))
        print("]\n")
        