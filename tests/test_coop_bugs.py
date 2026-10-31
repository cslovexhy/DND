"""Regression tests for bugs seen in a real co-op session (two windows, Heskan + Quinn):
heroes walking into walls, a dead hero still playing on autopilot, and companions in co-op."""
import random
import unittest
from collections import deque

from game import saves
from game.engine import commands as C
from game.engine.bootstrap import create_world, join_player
from game.engine.pathfinding import astar
from game.engine.world_map import WorldMap, TILE_SIZE

MAP = "data/maps/northshire.json"
DT = 1 / 30


def reachable_and_islands(wm):
    sx, sy = wm.get_start_pos()
    st = (int(sx // TILE_SIZE), int(sy // TILE_SIZE))
    seen, q = {st}, deque([st])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in seen and wm.is_floor(*n):
                seen.add(n)
                q.append(n)
    islands = [(x, y) for y in range(wm.height) for x in range(wm.width) if wm.is_floor(x, y) and (x, y) not in seen]
    return st, seen, islands


def center(t):
    return t[0] * TILE_SIZE + TILE_SIZE // 2, t[1] * TILE_SIZE + TILE_SIZE // 2


class PathfindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wm = WorldMap.load(MAP)
        cls.start, cls.reachable, cls.islands = reachable_and_islands(cls.wm)

    def test_far_reachable_target_gets_a_real_path_on_floor(self):
        far = max(self.reachable, key=lambda t: abs(t[0] - self.start[0]) + abs(t[1] - self.start[1]))
        sx, sy = self.wm.get_start_pos()
        path = astar(self.wm, sx, sy, *center(far), max_steps=None, fallback_direct=False)
        self.assertGreater(len(path), 5)
        self.assertTrue(all(not self.wm.is_wall(x, y) for x, y in path))

    def test_unreachable_target_gives_no_path_for_heroes(self):
        self.assertTrue(self.islands, "northshire has enclosed floor tiles")
        sx, sy = self.wm.get_start_pos()
        self.assertEqual(astar(self.wm, sx, sy, *center(self.islands[0]), max_steps=None, fallback_direct=False), [])

    def test_monster_style_callers_keep_the_old_fallback(self):
        sx, sy = self.wm.get_start_pos()
        self.assertEqual(len(astar(self.wm, sx, sy, *center(self.islands[0]))), 1)


class NeverInsideAWallTest(unittest.TestCase):
    def test_clicking_unreachable_spots_never_puts_the_hero_in_a_wall(self):
        random.seed(1)
        world, p = create_world(MAP, saves.blank_character("quinn", "Cleric"))
        world.game_state.monsters.clear()
        _, _, islands = reachable_and_islands(world.world_map)
        for target in islands[::20][:10]:
            world.submit(C.MoveTo(*center(target)), 0)
            for _ in range(60):
                world.step(DT)
                self.assertFalse(world.is_wall(p.hero.x, p.hero.y), f"hero in a wall heading to {target}")

    def test_bad_path_is_stopped_at_the_wall(self):
        random.seed(1)
        world, p = create_world(MAP, saves.blank_character("quinn", "Cleric"))
        world.game_state.monsters.clear()
        _, _, islands = reachable_and_islands(world.world_map)
        p.move_path = [center(islands[0])]            # force a straight line through walls
        for _ in range(30 * 20):
            world.step(DT)
            self.assertFalse(world.is_wall(p.hero.x, p.hero.y))

    def test_coop_autopilot_never_inside_walls(self):
        random.seed(1)
        world, host = create_world(MAP, saves.blank_character("heskan", "Wizard"), autopilot=True)
        join_player(world, 1, saves.blank_character("quinn", "Cleric"), MAP, autopilot=True)
        for _ in range(30 * 45):
            world.step(DT)
            world.events.clear()
            for h in world.player_heroes:
                if h.alive:
                    self.assertFalse(world.is_wall(h.x, h.y), f"{h.name} inside a wall")


class RespawnTest(unittest.TestCase):
    """No game over: a fallen player respawns at the start point with 10% HP; autopilot rests to 80% first."""

    def setUp(self):
        random.seed(2)
        self.world, self.host = create_world(MAP, saves.blank_character("heskan", "Wizard"), autopilot=True)
        self.quinn = join_player(self.world, 1, saves.blank_character("quinn", "Cleric"), MAP, autopilot=True)
        for _ in range(60):
            self.world.step(DT)

    def kill(self, player):
        h = player.hero
        h.apply_condition(__import__("game.engine.entities", fromlist=["Condition"]).Condition.POISONED, 30, tick_damage=5)
        h.buffs["Renew"] = {"remaining": 5.0, "hot_per_sec": 1.0}
        h.take_damage(10 ** 6, ignore_armor=True)

    def test_respawn_at_start_with_10_percent_and_clean_slate(self):
        h = self.host.hero
        h.x += 500
        self.kill(self.host)
        self.world.step(DT)
        self.assertTrue(h.alive)
        self.assertEqual((h.x, h.y), self.world.world_map.get_start_pos())
        self.assertAlmostEqual(h.hp / h.max_hp, 0.10, delta=0.02)   # 10% (+ a frame of regen)
        self.assertEqual(h.conditions, [])
        self.assertEqual(h.buffs, {})
        self.assertEqual(h.deaths, 1)
        self.assertEqual(self.host.move_path, [])
        self.assertIsNone(self.host.selected_target)
        self.assertFalse(self.world.game_state.adventure_failed)

    def test_monsters_stop_chasing_the_fallen_hero(self):
        h = self.host.hero
        m = self.world.game_state.monsters[0]
        from game.engine.ai import aggro_monster, AggroState
        aggro_monster(m, h, self.world.game_state.monsters)
        self.kill(self.host)
        self.world.step(DT)
        self.assertIsNot(getattr(m, "aggro_target", None), h)   # may go after the other player, not the respawned one

    def test_solo_monsters_give_up_after_the_hero_falls(self):
        from game.engine.ai import aggro_monster, AggroState
        random.seed(4)
        world, p = create_world(MAP, saves.blank_character("solo", "Fighter"))
        m = world.game_state.monsters[0]
        aggro_monster(m, p.hero, world.game_state.monsters)
        p.hero.take_damage(10 ** 6, ignore_armor=True)
        world.step(DT)
        self.assertIsNone(getattr(m, "aggro_target", None))
        self.assertNotEqual(m.aggro_state, AggroState.AGGROED)

    def test_autopilot_rests_at_spawn_until_80_percent(self):
        world, h = self.world, self.host.hero
        for m in world.game_state.monsters:            # nobody nearby to start a fight
            m.x, m.y = m.x + 5000, m.y + 5000
        self.kill(self.host)
        world.step(DT)
        start = (h.x, h.y)
        for _ in range(30 * 120):
            if h.hp >= h.max_hp * 0.8:
                break
            world.step(DT)
            world.events.clear()
            self.assertLess(((h.x - start[0]) ** 2 + (h.y - start[1]) ** 2) ** 0.5, 5, "moved while resting")
        self.assertGreaterEqual(h.hp, h.max_hp * 0.8)

    def test_solo_never_ends(self):
        random.seed(3)
        world, p = create_world(MAP, saves.blank_character("solo", "Rogue"), autopilot=True)
        for i in range(3):
            p.hero.take_damage(10 ** 6, ignore_armor=True)
            world.step(DT)
            self.assertTrue(p.hero.alive)
        self.assertEqual(p.hero.deaths, 3)
        self.assertFalse(world.game_state.adventure_failed)

    def test_dead_hero_acts_no_more_within_the_frame(self):
        """Between dying and the end-of-frame respawn, a dead hero's commands are ignored."""
        h = self.host.hero
        h.take_damage(10 ** 6, ignore_armor=True)
        self.host.handle(C.UsePotion())
        self.assertEqual(self.host.potions, 3)


class NoCompanionsInCoopTest(unittest.TestCase):
    def test_host_refuses_companions(self):
        from game.net.server import HostServer
        srv = HostServer(MAP, port=0, local_host=True, auto_companion=True)   # even if asked to
        try:
            self.assertFalse(srv.world.companions_enabled)
            self.assertEqual(srv.world.companions, [])
            srv.world.submit(C.ToggleCompanion("Fighter"), 0)
            srv.world.step(DT)
            self.assertEqual(srv.world.companions, [])
        finally:
            srv.listener.close()

    def test_solo_still_has_companions(self):
        random.seed(1)
        world, _ = create_world(MAP, saves.blank_character("me", "Wizard"))
        world.submit(C.ToggleCompanion("Fighter"), 0)
        world.step(DT)
        self.assertEqual(len(world.companions), 1)


if __name__ == "__main__":
    unittest.main()
