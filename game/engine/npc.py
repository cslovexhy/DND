"""NPC: a stationary quest-giver (pure; no pygame)."""
from game.engine.entities import Entity


class NPC(Entity):
    """A quest-giving NPC. Inherits all combat/entity attributes but doesn't fight by default.
    role: None (quests only), "trainer" (teaches skill levels to heroes of class `trains`) or "vendor" (sells the
    goods of shop `shop`: content/shop.SHOPS)."""
    def __init__(self, world, name, x, y, npc_id, gender="male", level=1, sprite=None, role=None, trains=None,
                 shop=None):
        # NPC has minimal combat stats (hp=5 gives 250 HP, ac=10 no armor, speed=0 stationary)
        super().__init__(name, x, y, hp=5, ac=10, speed=0)
        self.world = world
        self.npc_id = npc_id  # matches the quests' giver / turn_in / reward_npc
        self.gender = gender  # "male" or "female" — used for TTS voice
        self.level = level
        self.sprite = sprite
        self.interact_range = 80  # pixels — how close hero must be to interact
        self.role, self.trains, self.shop = role, trains, shop

    @property
    def title(self):
        """The "<...>" line under the name: what this NPC does for you."""
        if self.role == "trainer":
            return f"{self.trains} Trainer"
        if self.role == "vendor":
            from game.content.shop import SHOP_TITLES
            return SHOP_TITLES.get(self.shop, "Vendor")
        return ""

    def can_deal_with(self, hx, hy):
        """Close enough to buy / train (a little more slack than starting a conversation)."""
        r = self.interact_range * 1.5
        return (self.x - hx) ** 2 + (self.y - hy) ** 2 <= r * r

    def has_available_quest(self, player=None):
        """Does this NPC have a quest to offer this player (default player 0)?"""
        player = player or self.world.players[0]
        return len(player.quests.available_for_npc(self.npc_id, player.hero.level)) > 0

    def has_turn_in(self, player=None):
        """Does this NPC have a quest ready to turn in for this player (default player 0)?"""
        player = player or self.world.players[0]
        quests = player.quests
        return bool(quests.turn_ins_for_npc(self.npc_id) or quests.rewards_for_npc(self.npc_id))

    def is_in_range(self, hx, hy):
        dx = self.x - hx
        dy = self.y - hy
        return (dx*dx + dy*dy) <= self.interact_range * self.interact_range
