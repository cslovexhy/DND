"""Trading items between two players (pure; no pygame). Lives in the World (host side), driven by commands.

Flow: player A targets player B and opens a trade (TradeOpen) -> both see the trade window. Each side offers items
one at a time from their backpack (TradeOffer: 1 of the item in a backpack slot) and can take one back (TradeTake).
Any change to an offer clears both "accepted" ticks. When both have accepted (TradeAccept) the swap happens - but
only if the two heroes are within TRADE_RANGE and both backpacks have room; otherwise both get a message and the
ticks are cleared. TradeCancel (or a player leaving) ends it for both. Companions can't trade.

Offered items stay in the backpack until the trade completes; they are checked again at that moment.
"""

TRADE_RANGE = 200          # px between the two heroes to complete a trade
TOO_FAR = "Need to be closer to complete trade"


class Trade:
    def __init__(self, a, b):
        self.players = (a, b)                       # PlayerState x2
        self.offers = {a.player_id: {}, b.player_id: {}}       # player_id -> {item: count}
        self.accepted = {a.player_id: False, b.player_id: False}
        self.message = ""                            # last problem, shown in both windows

    def partner(self, player):
        a, b = self.players
        return b if player is a else a

    def offered(self, player, item):
        return self.offers[player.player_id].get(item, 0)

    def _changed(self):
        for pid in self.accepted:
            self.accepted[pid] = False
        self.message = ""

    def offer(self, player, slot):
        """Offer 1 more of the item in this backpack slot (as long as the backpack has more than already offered)."""
        item = player.inventory.item_at(slot)
        if item is None or player.inventory.count(item) <= self.offered(player, item):
            return
        self.offers[player.player_id][item] = self.offered(player, item) + 1
        self._changed()

    def take(self, player, item):
        """Take 1 of `item` back out of the offer."""
        n = self.offered(player, item)
        if n <= 0:
            return
        if n == 1:
            del self.offers[player.player_id][item]
        else:
            self.offers[player.player_id][item] = n - 1
        self._changed()

    def accept(self, player):
        """Tick "accept"; when both have, try to complete. Returns True if the trade happened."""
        self.accepted[player.player_id] = True
        if not all(self.accepted.values()):
            return False
        return self._complete()

    def _complete(self):
        a, b = self.players
        if a.hero.distance_to(b.hero) > TRADE_RANGE:
            return self._fail(TOO_FAR)
        for p in (a, b):
            for item, n in self.offers[p.player_id].items():
                if p.inventory.count(item) < n:
                    return self._fail(f"{p.hero.name} no longer has {n} x {item}")
        # do it on copies first: both backpacks must have room for what they receive
        inv = {a.player_id: a.inventory.copy(), b.player_id: b.inventory.copy()}
        for giver in (a, b):
            for item, n in self.offers[giver.player_id].items():
                inv[giver.player_id].take(item, n)
        for giver in (a, b):
            getter = self.partner(giver)
            for item, n in self.offers[giver.player_id].items():
                if not inv[getter.player_id].add(item, n):
                    return self._fail(f"{getter.hero.name}'s backpack is full")
        a.inventory.slots = inv[a.player_id].slots
        b.inventory.slots = inv[b.player_id].slots
        return True

    def _fail(self, message):
        self.message = message
        for pid in self.accepted:
            self.accepted[pid] = False
        return False

    def view(self, player):
        """What `player`'s client shows (snapshot data)."""
        other = self.partner(player)
        return {"partner_id": other.player_id, "partner_name": other.hero.name,
                "partner_hero_id": other.hero.eid,
                "mine": [{"item": i, "count": n} for i, n in sorted(self.offers[player.player_id].items())],
                "theirs": [{"item": i, "count": n} for i, n in sorted(self.offers[other.player_id].items())],
                "my_accept": self.accepted[player.player_id], "their_accept": self.accepted[other.player_id],
                "message": self.message}
