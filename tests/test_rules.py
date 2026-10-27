import copy
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rules import DT, Enemy, Game, Gem, Weapon, wave, weapon_stats  # noqa: E402

CFG = json.load(open(os.path.join(ROOT, "data", "game.json"), encoding="utf-8"))
CENTER_X = CFG["world"]["screen_w"] / 2.0
CENTER_Y = CFG["world"]["screen_h"] / 2.0
BAT = CFG["enemies"]["bat"]
GROWTH = CFG["growth"]


def quiet_game(**changes):
    """A game with no spawning and no weapons, for testing one thing at a time."""
    cfg = copy.deepcopy(CFG)
    cfg["spawn"]["table"] = []
    for part, values in changes.items():
        cfg[part].update(values)
    return Game(cfg)


def tick(game, seconds, target=None):
    for _ in range(int(seconds / DT)):
        game.step(target)


def add_enemy(game, kind, x, y, hp=None):
    e = Enemy(x, y, kind, game.config["enemies"][kind])
    if hp is not None:
        e.hp = hp
    game.enemies.append(e)
    return e


def add_bat(game, x, y, hp=None):
    return add_enemy(game, "bat", x, y, hp)


def immortal(game):
    game.hero.hp = 1e9
    game.hero.max_hp = 1e9
    return game


class TestCore(unittest.TestCase):
    def test_bats_spawn_on_a_circle_around_the_hero(self):
        game = Game(CFG)
        game.hero.weapons = []
        self.assertEqual(len(game.enemies), 0)
        tick(game, 1.05)  # just after the first 1 s spawn beat
        sp = CFG["spawn"]
        self.assertGreater(len(game.enemies), 0)
        self.assertLessEqual(len(game.enemies), sp["max_per_tick"])
        for e in game.enemies:
            self.assertEqual(e.kind, "bat")
            d = ((e.x - game.hero.x) ** 2 + (e.y - game.hero.y) ** 2) ** 0.5
            self.assertLessEqual(d, sp["circle_radius"])
            self.assertGreater(d, sp["circle_radius"] - 20)  # they only just started

    def test_spawn_fills_up_to_minimum(self):
        game = Game(CFG)
        game.hero.weapons = []  # nothing dies, so we can count the spawns
        tick(game, 3.2)
        self.assertEqual(len(game.enemies), CFG["spawn"]["table"][0]["min_alive"])

    def test_hero_walks_to_target(self):
        game = Game(CFG)
        before_x = game.hero.x
        tick(game, 0.5, (CENTER_X + 100, CENTER_Y))
        self.assertGreater(game.hero.x, before_x)

    def test_hero_stops_in_deadzone(self):
        game = Game(CFG)
        x, y = game.hero.x, game.hero.y
        tick(game, 0.5, (x, y))
        self.assertAlmostEqual(game.hero.x, x, places=6)
        self.assertAlmostEqual(game.hero.y, y, places=6)

    def test_contact_damage_has_a_half_second_cooldown(self):
        game = quiet_game()
        game.hero.weapons = []  # nothing shoots, so only contact hurts the hero
        add_bat(game, game.hero.x, game.hero.y, hp=1000.0)
        hp0 = game.hero.hp
        tick(game, 0.4)
        self.assertEqual(game.hero.hp, hp0 - BAT["damage"])
        tick(game, 0.2)  # 0.6 s after the first hit
        self.assertEqual(game.hero.hp, hp0 - 2 * BAT["damage"])

    def test_game_over_when_hp_reaches_zero(self):
        game = quiet_game()
        game.hero.hp = BAT["damage"]
        add_bat(game, game.hero.x, game.hero.y, hp=1000.0)
        tick(game, 0.1)
        self.assertTrue(game.dead)
        self.assertEqual(game.hero.hp, 0)

    def test_restart_after_death(self):
        game = Game(CFG)
        game.hero.hp = 0.0
        game.dead = True
        tick(game, 0.5)
        self.assertEqual(game.time, 0.0)
        game.reset()
        self.assertFalse(game.dead)
        self.assertEqual(game.hero.hp, CFG["hero"]["max_hp"])
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(game.hero.level, 1)


class TestWeaponLevels(unittest.TestCase):
    def test_spark_wand_numbers_per_level(self):
        base = weapon_stats(CFG, "spark_wand", 1)
        self.assertEqual(base["damage"], CFG["weapons"]["spark_wand"]["base"]["damage"])
        self.assertEqual(base["count"], 1)
        level3 = weapon_stats(CFG, "spark_wand", 3)
        per = CFG["weapons"]["spark_wand"]["per_level"]
        self.assertEqual(level3["damage"], base["damage"] + 2 * per["damage"])
        self.assertAlmostEqual(level3["cooldown"],
                               base["cooldown"] + 2 * per["cooldown"])
        self.assertEqual(level3["count"], 2)  # +1 spark at level 3
        self.assertEqual(weapon_stats(CFG, "spark_wand", 5)["count"], 3)  # and at 5

    def test_spin_blades_count_per_level(self):
        self.assertEqual(weapon_stats(CFG, "spin_blades", 1)["count"], 2)
        self.assertEqual(weapon_stats(CFG, "spin_blades", 2)["count"], 3)
        self.assertEqual(weapon_stats(CFG, "spin_blades", 4)["count"], 4)
        self.assertEqual(weapon_stats(CFG, "spin_blades", 5)["count"], 4)

    def test_holy_ring_grows_with_levels(self):
        base = CFG["weapons"]["holy_ring"]["base"]
        one = weapon_stats(CFG, "holy_ring", 1)
        two = weapon_stats(CFG, "holy_ring", 2)
        self.assertEqual(one["radius"], base["radius"])
        self.assertEqual(two["radius"], base["radius"] + 10)
        self.assertEqual(two["damage"], base["damage"] + 2)

    def test_spark_travels_at_the_speed_from_the_data(self):
        game = quiet_game()
        add_bat(game, game.hero.x + 300, game.hero.y)
        tick(game, 2 * DT)  # one tick to fire, one tick to move
        p = game.projectiles[0]
        moved = ((p.x - game.hero.x) ** 2 + (p.y - game.hero.y) ** 2) ** 0.5
        speed = CFG["weapons"]["spark_wand"]["base"]["speed"]
        self.assertAlmostEqual(moved, speed * DT, places=6)

    def test_a_dead_bat_drops_a_gem_worth_its_xp(self):
        game = quiet_game()
        add_bat(game, game.hero.x + 300, game.hero.y)
        tick(game, 1.0)  # (300 - hit distance) / (400 + 100) is about 0.6 s
        self.assertEqual(game.kills, 1)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(len(game.gems), 1)  # far away, so it is not picked up yet
        gem = game.gems[0]
        self.assertEqual(gem.xp, BAT["xp"])
        self.assertGreater(abs(gem.x - game.hero.x), CFG["hero"]["magnet_radius"])
        self.assertEqual(game.hero.xp, 0)

    def test_spin_blades_hit_once_per_half_second_per_blade(self):
        game = quiet_game()
        game.hero.weapons = [Weapon("spin_blades", 1)]
        stats = weapon_stats(CFG, "spin_blades", 1)
        game.hero.weapons[0].angle = 0.0
        bat = add_bat(game, game.hero.x + stats["orbit_radius"], game.hero.y,
                      hp=1000.0)
        tick(game, 0.3)  # blade 1 sweeps over it once, blade 2 is on the far side
        self.assertEqual(bat.hp, 1000.0 - stats["damage"])

    def test_holy_ring_hurts_everything_inside_its_circle(self):
        game = quiet_game()
        game.hero.weapons = [Weapon("holy_ring", 1)]
        stats = weapon_stats(CFG, "holy_ring", 1)
        near = add_bat(game, game.hero.x + 30, game.hero.y, hp=1000.0)
        far = add_bat(game, game.hero.x + 300, game.hero.y, hp=1000.0)
        tick(game, 0.1)
        self.assertEqual(near.hp, 1000.0 - stats["damage"])
        self.assertEqual(far.hp, 1000.0)  # outside the ring
        tick(game, 0.4)  # still inside the 0.5 s cooldown
        self.assertEqual(near.hp, 1000.0 - stats["damage"])


class TestGemsAndXp(unittest.TestCase):
    def test_xp_curve_is_5_then_3_more_each_level(self):
        game = quiet_game()
        self.assertEqual(game.xp_needed(), GROWTH["xp_first"])
        game.hero.level = 2
        self.assertEqual(game.xp_needed(), GROWTH["xp_first"] + GROWTH["xp_step"])
        game.hero.level = 5
        self.assertEqual(game.xp_needed(),
                         GROWTH["xp_first"] + 4 * GROWTH["xp_step"])

    def test_gem_still_outside_the_magnet_and_flies_inside_it(self):
        game = quiet_game()
        magnet = CFG["hero"]["magnet_radius"]
        far = game.config["spawn"]["circle_radius"]
        game.gems = [Gem(game.hero.x + far, game.hero.y, 1),
                     Gem(game.hero.x + magnet - 5, game.hero.y, 1)]
        tick(game, 2 * DT)
        speed = GROWTH["gem_speed"]
        self.assertAlmostEqual(game.gems[0].x, game.hero.x + far, places=6)
        moved = magnet - 5 - (game.gems[1].x - game.hero.x)
        self.assertAlmostEqual(moved, speed * 2 * DT, places=4)

    def test_a_gem_reaching_the_hero_gives_xp(self):
        game = quiet_game()
        game.gems = [Gem(game.hero.x, game.hero.y, BAT["xp"])]
        tick(game, DT)
        self.assertEqual(game.hero.xp, BAT["xp"])
        self.assertEqual(len(game.gems), 0)

    def test_level_up_pauses_and_shows_three_cards(self):
        game = quiet_game()
        game.hero.xp = GROWTH["xp_first"] - 1
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        self.assertEqual(game.hero.level, 2)
        self.assertTrue(game.choosing)
        self.assertEqual(len(game.cards), GROWTH["cards"])
        time_now = game.time
        tick(game, 0.5)  # the game is paused while you choose
        self.assertAlmostEqual(game.time, time_now, places=10)

    def test_no_card_offers_a_level_that_is_too_high(self):
        game = quiet_game()
        game.hero.weapons = [Weapon(k, GROWTH["max_level"]) for k in CFG["weapons"]]
        game.hero.passives = {k: GROWTH["max_level"] for k in CFG["passives"]}
        game.hero.xp = GROWTH["xp_first"]
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        self.assertTrue(game.choosing)
        for card in game.cards:
            self.assertEqual(card["type"], "heal")
            self.assertIsNone(card["kind"])

    def test_you_cannot_get_more_than_three_weapons(self):
        game = quiet_game()
        game.hero.weapons = [Weapon(k, 1) for k in CFG["weapons"]]
        game.hero.xp = GROWTH["xp_first"]
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        for card in game.cards:
            self.assertNotEqual(card["type"], "new")

    def test_choosing_a_card_applies_it_and_unpauses(self):
        game = quiet_game()
        # only one thing left to offer, so the first card is always Swift Boots
        game.hero.weapons = [Weapon(k, GROWTH["max_level"]) for k in CFG["weapons"]]
        game.hero.passives = {k: GROWTH["max_level"] for k in CFG["passives"]
                              if k != "swift_boots"}
        game.hero.xp = GROWTH["xp_first"]
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        self.assertEqual(game.cards[0]["kind"], "swift_boots")
        self.assertEqual(game.cards[0]["level"], 1)
        self.assertTrue(game.choose(0))
        self.assertFalse(game.choosing)
        self.assertEqual(game.hero.passives["swift_boots"], 1)
        per = CFG["passives"]["swift_boots"]["per_level"]["speed_pct"]
        self.assertAlmostEqual(game.hero.speed, CFG["hero"]["speed"] * (1 + per))

    def test_passive_items_change_the_hero(self):
        game = quiet_game()
        game.hero.hp = 50
        game.hero.passives = {"big_heart": 2, "magnet": 3}
        game.hero.apply_passives(CFG["passives"])
        self.assertEqual(game.hero.max_hp,
                         CFG["hero"]["max_hp"] + 2 * CFG["passives"]["big_heart"]["per_level"]["max_hp"])
        self.assertEqual(game.hero.hp, 50)  # max HP never heals by itself
        self.assertEqual(game.hero.magnet_radius,
                         CFG["hero"]["magnet_radius"] + 3 * CFG["passives"]["magnet"]["per_level"]["magnet_radius"])

    def test_big_heart_heals_when_you_pick_it(self):
        game = quiet_game()
        game.hero.hp = 40
        game.hero.weapons = [Weapon(k, GROWTH["max_level"]) for k in CFG["weapons"]]
        game.hero.passives = {k: GROWTH["max_level"] for k in CFG["passives"]
                              if k != "big_heart"}
        game.hero.xp = GROWTH["xp_first"]
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        index = next(i for i, c in enumerate(game.cards) if c["kind"] == "big_heart")
        game.choose(index)
        self.assertEqual(game.hero.max_hp, CFG["hero"]["max_hp"] + CFG["passives"]["big_heart"]["per_level"]["max_hp"])
        self.assertEqual(game.hero.hp, 40 + CFG["passives"]["big_heart"]["pick_heal"])

    def test_heal_card_gives_hp_back(self):
        game = quiet_game()
        game.hero.weapons = [Weapon(k, GROWTH["max_level"]) for k in CFG["weapons"]]
        game.hero.passives = {k: GROWTH["max_level"] for k in CFG["passives"]}
        game.hero.hp = 10
        game.hero.xp = GROWTH["xp_first"]
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        game.choose(0)
        self.assertEqual(game.hero.hp, 10 + GROWTH["heal_card_hp"])

    def test_two_level_ups_show_cards_twice(self):
        game = quiet_game()
        # one gem that lands exactly on the second level (5 + 8 XP)
        game.hero.xp = game.xp_needed() + (GROWTH["xp_first"] + GROWTH["xp_step"]) - 1
        game.gems = [Gem(game.hero.x, game.hero.y, 1)]
        tick(game, 2 * DT)
        self.assertEqual(game.hero.level, 3)
        self.assertEqual(game.pending_levels, 2)
        game.choose(0)
        self.assertTrue(game.choosing)  # the second level-up is still waiting
        self.assertEqual(game.pending_levels, 1)
        game.choose(0)
        self.assertFalse(game.choosing)


class TestWaves(unittest.TestCase):
    def test_every_row_of_the_table_is_used_at_its_time(self):
        rows = CFG["spawn"]["table"]
        for i, row in enumerate(rows):
            now = wave(CFG, row["from_s"])
            self.assertEqual(now["types"], row["types"])
            self.assertEqual(now["min_alive"], row["min_alive"])
            if i:
                before = wave(CFG, row["from_s"] - 0.1)
                self.assertEqual(before["types"], rows[i - 1]["types"])
                self.assertEqual(before["min_alive"], rows[i - 1]["min_alive"])
        self.assertEqual(wave(CFG, 119.0)["min_alive"], 75)

    def test_only_the_current_types_appear(self):
        game = immortal(Game(copy.deepcopy(CFG)))
        game.hero.weapons = []
        kinds = set()
        for _ in range(int(40.0 / DT)):
            game.step(None)
            kinds.update(e.kind for e in game.enemies)
            self.assertTrue(kinds <= {"bat", "slime"})  # no ghosts before 0:45
        self.assertIn("slime", kinds)
        self.assertIn("bat", kinds)

    def test_the_boss_appears_once_and_keeps_its_numbers(self):
        game = immortal(Game(copy.deepcopy(CFG)))
        game.hero.weapons = []
        tick(game, 91.0)
        demons = [e for e in game.enemies if e.kind == "demon"]
        self.assertEqual(len(demons), 1)
        self.assertEqual(demons[0].max_hp, CFG["enemies"]["demon"]["hp"])
        self.assertTrue(demons[0].boss)
        tick(game, 12.0)
        self.assertEqual(len([e for e in game.enemies if e.boss]), 1)

    def test_the_boss_is_never_removed_but_is_pulled_back(self):
        game = quiet_game()
        demon = add_enemy(game, "demon", game.hero.x + 900, game.hero.y)
        tick(game, 2 * DT)
        self.assertIn(demon, game.enemies)
        # it lands somewhere on the spawn circle and then walks in a little
        d = math.dist((demon.x, demon.y), (game.hero.x, game.hero.y))
        self.assertLessEqual(d, CFG["spawn"]["circle_radius"])
        self.assertGreater(d, CFG["spawn"]["circle_radius"] - 10)

    def test_a_normal_enemy_too_far_away_is_removed(self):
        game = quiet_game()
        bat = add_bat(game, game.hero.x + 900, game.hero.y)
        tick(game, DT)
        self.assertNotIn(bat, game.enemies)

    def test_never_more_than_the_cap_alive(self):
        cfg = copy.deepcopy(CFG)
        cfg["spawn"]["alive_cap"] = 10
        game = immortal(Game(cfg))
        game.hero.weapons = []
        for _ in range(int(6.0 / DT)):
            game.step(None)
            self.assertLessEqual(len(game.enemies), 10)

    def test_the_boss_drops_no_gem(self):
        game = quiet_game()
        game.hero.weapons = [Weapon("holy_ring", CFG["growth"]["max_level"])]
        add_enemy(game, "demon", game.hero.x + 10, game.hero.y, hp=5.0)
        tick(game, 0.6)
        self.assertEqual(game.kills, 1)
        self.assertEqual(game.gems, [])

    def test_a_slime_drops_a_two_xp_gem(self):
        game = quiet_game()
        add_enemy(game, "slime", game.hero.x + 300, game.hero.y, hp=1.0)
        tick(game, 1.0)
        self.assertEqual(game.kills, 1)
        self.assertEqual([g.xp for g in game.gems], [CFG["enemies"]["slime"]["xp"]])

    def test_ghosts_are_faster_than_the_hero(self):
        self.assertGreater(CFG["enemies"]["ghost"]["speed"], CFG["hero"]["speed"])

    def test_victory_at_the_goal_time(self):
        game = quiet_game()
        game.time = CFG["win_time"] - DT
        tick(game, 2 * DT)
        self.assertTrue(game.won)
        self.assertEqual(game.time, CFG["win_time"])
        after = (game.hero.x, game.hero.y, len(game.enemies))
        tick(game, 2.0)  # nothing moves any more
        self.assertEqual((game.hero.x, game.hero.y, len(game.enemies)), after)

    def test_a_full_run_from_zero_to_two_minutes(self):
        game = immortal(Game(copy.deepcopy(CFG)))
        game.hero.weapons = []
        for _ in range(int(121.0 / DT)):
            game.step(None)
            if game.won:
                break
        self.assertTrue(game.won)
        self.assertLessEqual(len(game.enemies), CFG["spawn"]["alive_cap"])
        self.assertTrue(any(e.boss for e in game.enemies))


class TestFeel(unittest.TestCase):
    """Damage numbers, the death flash, the screen shake and the sound events."""

    def ring_game(self, hp=1000.0):
        """One quiet game with a Holy Ring and a bat that cannot run away."""
        game = immortal(quiet_game())
        game.hero.weapons = [Weapon("holy_ring", 1)]
        add_bat(game, game.hero.x + 30, game.hero.y, hp=hp)
        return game

    def test_a_hit_leaves_a_damage_number_that_goes_away(self):
        game = self.ring_game()
        damage = CFG["weapons"]["holy_ring"]["base"]["damage"]
        tick(game, DT)  # the ring is ready at once, so this is its first hit
        self.assertIn(str(int(damage)), [n.text for n in game.numbers])
        game.hero.weapons = []  # stop the hits so we can watch one number
        tick(game, CFG["feel"]["number_lifetime"] + DT)
        self.assertEqual(game.numbers, [])

    def test_the_numbers_do_not_flood_the_screen(self):
        game = self.ring_game()
        game.config["feel"]["number_max"] = 3
        tick(game, 3.0)
        self.assertLessEqual(len(game.numbers), 3)

    def test_a_dead_enemy_leaves_a_flash(self):
        game = self.ring_game(hp=1.0)
        tick(game, DT)
        self.assertEqual(game.kills, 1)
        self.assertEqual(len(game.pops), 1)
        self.assertEqual(game.pops[0].radius, CFG["enemies"]["bat"]["hit_radius"])
        game.hero.weapons = []
        tick(game, CFG["feel"]["flash_lifetime"] + DT)
        self.assertEqual(game.pops, [])

    def test_being_hurt_shakes_the_screen_and_it_stops(self):
        game = quiet_game()
        game.hero.weapons = []
        add_bat(game, game.hero.x + 10, game.hero.y)
        self.assertEqual(game.shake, 0.0)
        tick(game, DT)
        # the shake starts full and one tick has already run out
        self.assertAlmostEqual(game.shake,
                               CFG["feel"]["hurt_shake_s"] - DT)
        tick(game, CFG["feel"]["hurt_shake_s"] + 2 * DT)
        self.assertEqual(game.shake, 0.0)

    def test_the_shake_does_not_move_the_camera_back(self):
        game = quiet_game()
        game.hero.weapons = []
        add_bat(game, game.hero.x + 10, game.hero.y)
        tick(game, 0.5)
        self.assertAlmostEqual(game.cam_x,
                               game.hero.x - CFG["world"]["screen_w"] / 2.0)

    def test_a_hit_a_gem_and_a_level_up_make_their_sounds(self):
        game = self.ring_game(hp=1.0)
        tick(game, CFG["weapons"]["holy_ring"]["base"]["cooldown"] + 2 * DT)
        self.assertIn("hit", game.take_events())
        game.hero.xp = GROWTH["xp_first"] - 1
        game.gems.append(Gem(game.hero.x, game.hero.y, 1))
        tick(game, 2 * DT)
        events = game.take_events()
        self.assertIn("gem", events)
        self.assertIn("level", events)
        self.assertEqual(game.take_events(), [])  # they are only said once

    def test_getting_hurt_and_losing_make_their_sounds(self):
        game = quiet_game()
        game.hero.weapons = []
        game.hero.hp = 2 * CFG["enemies"]["bat"]["damage"]  # one more bite kills
        add_bat(game, game.hero.x + 10, game.hero.y)
        tick(game, DT)
        self.assertEqual(game.take_events(), ["hurt"])
        add_bat(game, game.hero.x + 10, game.hero.y)
        tick(game, CFG["contact_cooldown"] + 2 * DT)
        self.assertTrue(game.dead)
        self.assertEqual(game.take_events(), ["hurt", "lose"])

    def test_winning_makes_its_sound_once(self):
        game = immortal(quiet_game())
        game.config["win_time"] = 0.5
        tick(game, 1.0)
        self.assertTrue(game.won)
        self.assertEqual(game.take_events(), ["win"])
        tick(game, 0.5)
        self.assertEqual(game.take_events(), [])


if __name__ == "__main__":
    unittest.main()
