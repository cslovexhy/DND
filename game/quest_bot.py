"""Quest bot (pure sim; no pygame): plays a character through a map's quests on top of the normal autopilot.

Priorities, re-checked every step:
  1. a quest is complete -> walk to its NPC and turn it in;
  2. an NPC offers a quest for our level -> walk there and accept it (quests in SKIP are never taken);
  3. otherwise fight: the autopilot goes for the mobs our active quests still need (any mob if none).
While monsters are fighting us the autopilot always handles the fight first (walking to an NPC waits).

Used by tools/early_class_bench.py (time from level 1 to level N per class) and tests/test_quest_bot.py.
"""
from game.engine.ai import AggroState
from game.engine.commands import InteractNpc

SKIP = {"bounty_on_garrick_padfoot"}   # a named elite: not part of the baseline


class QuestBot:
    def __init__(self, world, player, skip=SKIP):
        self.world = world
        self.player = player
        self.skip = set(skip)
        self.player.ai_enabled = True
        self._next_talk = 0.0           # game time of the next InteractNpc (don't send one every frame)
        self.goal = None                # (kind, npc) we're walking to, for reports/debugging

    # --- what to do ---
    def _in_combat(self):
        hero = self.player.hero
        return any(m.alive and m.aggro_state == AggroState.AGGROED and (m.aggro_target is hero or hero in m.hate)
                   for m in self.world.game_state.monsters)

    def _npc_goal(self):
        ql, hero = self.player.quests, self.player.hero
        turn_ins = [n for n in self.world.npcs if ql.turn_ins_for_npc(n.npc_id)]
        if turn_ins:
            return "turn in", min(turn_ins, key=hero.distance_to)
        offers = [n for n in self.world.npcs
                  if [q for q in ql.available_for_npc(n.npc_id, hero.level) if q not in self.skip]]
        if offers:
            return "accept", min(offers, key=hero.distance_to)
        return None

    def quest_targets(self):
        """Monster names the active quests still need."""
        need = set()
        for q in self.player.quests.active_objects():
            for obj in q.objectives:
                if q.progress.get(obj["target"], 0) < obj["count"]:
                    need.add(obj["target"])
        return need

    # --- one step ---
    def step(self):
        p, world = self.player, self.world
        self.goal = None if self._in_combat() else self._npc_goal()
        if self.goal is not None:
            _, npc = self.goal
            p.ai_enabled = False                              # walk to the NPC ourselves
            now = world.game_state.game_time
            if now >= self._next_talk or npc.is_in_range(p.hero.x, p.hero.y):
                world.submit(InteractNpc(npc.eid), p.player_id)   # walks there, or talks when in range
                self._next_talk = now + 1.0
            return
        p.ai_enabled = True
        need = self.quest_targets()
        p.hero_ai.target_filter = (lambda m: m.name in need) if need else None
