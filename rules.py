"""Night Survivors rules with a fixed time step. No pygame here."""

import math
import random

DT = 1.0 / 60.0

# how a passive item changes the hero
ADDITIVE = ("max_hp", "magnet_radius")
MULTIPLICATIVE = ("speed_pct",)


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def weapon_stats(config, kind, level):
    """The numbers for one weapon at one level, worked out from the data file."""
    spec = config["weapons"][kind]
    stats = dict(spec["base"])
    for field, per in spec.get("per_level", {}).items():
        stats[field] = stats.get(field, 0) + per * (level - 1)
    if "count" in stats:
        stats["count"] += sum(1 for lv in spec.get("extra_count_at_levels", [])
                              if level >= lv)
    stats["mode"] = spec["mode"]
    return stats


def wave(config, t):
    """The spawn row that is in force at time t (the last row that started)."""
    row = None
    for candidate in config["spawn"]["table"]:
        if t >= candidate["from_s"]:
            row = candidate
        else:
            break
    return row or {"types": [], "min_alive": 0}


class Hero:
    def __init__(self, x, y, hcfg):
        self.x = x
        self.y = y
        self.base_speed = hcfg["speed"]
        self.base_max_hp = hcfg["max_hp"]
        self.base_magnet = hcfg["magnet_radius"]
        self.hit_radius = hcfg["hit_radius"]
        self.walk_deadzone = hcfg["walk_deadzone"]
        self.speed = hcfg["speed"]
        self.magnet_radius = hcfg["magnet_radius"]
        self.max_hp = hcfg["max_hp"]
        self.hp = hcfg["max_hp"]
        self.level = 1
        self.xp = 0.0
        self.weapons = []
        self.passives = {}

    def apply_passives(self, passives_cfg):
        """Walking speed, max HP and magnet radius come from the items."""
        speed_mult = 1.0
        adds = dict.fromkeys(ADDITIVE, 0.0)
        for kind, level in self.passives.items():
            for field, per in passives_cfg[kind]["per_level"].items():
                if field in MULTIPLICATIVE:
                    speed_mult += per * level
                else:
                    adds[field] += per * level
        self.speed = self.base_speed * speed_mult
        self.max_hp = self.base_max_hp + adds["max_hp"]
        self.magnet_radius = self.base_magnet + adds["magnet_radius"]
        self.hp = min(self.hp, self.max_hp)


class Enemy:
    def __init__(self, x, y, kind, cfg):
        self.x = x
        self.y = y
        self.kind = kind
        self.boss = bool(cfg.get("boss", False))
        self.hp = cfg["hp"]
        self.max_hp = cfg["hp"]
        self.speed = cfg["speed"]
        self.damage = cfg["damage"]
        self.xp = cfg["xp"]
        self.hit_radius = cfg["hit_radius"]
        self.projectile_radius = cfg["projectile_radius"]
        self.hit_cd = {}  # "contact" or "blade-0" -> seconds before it hits again
        self.dead = False

    def tick_hit_cd(self):
        for key in list(self.hit_cd):
            self.hit_cd[key] -= DT
            if self.hit_cd[key] <= 0.0:
                del self.hit_cd[key]

    def can_be_hit_by(self, key):
        return self.hit_cd.get(key, 0.0) <= 0.0


class Gem:
    def __init__(self, x, y, xp):
        self.x = x
        self.y = y
        self.xp = xp


class Number:
    """A damage figure that floats up and fades away."""

    def __init__(self, x, y, text, life):
        self.x = x
        self.y = y
        self.text = text
        self.life = life


class Pop:
    """The short flash an enemy leaves when it dies."""

    def __init__(self, x, y, radius, life):
        self.x = x
        self.y = y
        self.radius = radius
        self.life = life


class Projectile:
    """vx and vy are already px/s (direction times speed)."""

    def __init__(self, x, y, vx, vy, damage, lifetime, kind, radius):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.remaining = lifetime
        self.kind = kind
        self.radius = radius
        self.dead = False

    def hit_dist(self, enemy):
        return self.radius + enemy.projectile_radius


class Weapon:
    def __init__(self, kind, level=1):
        self.kind = kind
        self.level = level
        self.cd = 0.0
        self.angle = 0.0  # used by the orbiting blades


class Game:
    """Step 5: everything from step 4, plus damage numbers, flashes, shake and sounds."""

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        world = self.config["world"]
        self.hero = Hero(world["screen_w"] / 2.0, world["screen_h"] / 2.0,
                         self.config["hero"])
        self.hero.weapons = [Weapon(k) for k in self.config["hero"]["start_weapons"]]
        self.enemies = []
        self.projectiles = []
        self.gems = []
        self.time = 0.0
        self.spawn_timer = 0.0
        self.kills = 0
        self.dead = False
        self.won = False
        self.boss_alive = False
        self.pending_levels = 0
        self.cards = []
        self.choosing = False
        # step 5: what the screen shows and which sounds to play
        self.numbers = []
        self.pops = []
        self.shake = 0.0
        self.events = []
        # the camera starts so that the hero is in the middle of the screen
        self.cam_x = self.hero.x - world["screen_w"] / 2.0
        self.cam_y = self.hero.y - world["screen_h"] / 2.0

    def take_events(self):
        """The sounds that happened since the last call, as a list of names."""
        events, self.events = self.events, []
        return events

    def step(self, target=None):
        """Advance one fixed tick. target is (screen_x, screen_y) or None."""
        if self.dead or self.won or self.choosing:
            return
        self._move_hero(target)
        self.time += DT
        if self.time >= self.config["win_time"]:
            self.time = self.config["win_time"]
            self.won = True
            self.events.append("win")
            return
        self._spawn()
        self._move_enemies()
        self._move_projectiles()
        self._do_weapons()
        self._move_gems()
        self._tick_feel()
        self._update_camera()
        if self.pending_levels and not self.choosing:
            self._offer_cards()
            self.choosing = True
            self.events.append("level")

    # ---------- hero, camera ----------

    def _move_hero(self, target):
        if target is None:
            return
        tx, ty = target[0] + self.cam_x, target[1] + self.cam_y
        d = _dist(tx, ty, self.hero.x, self.hero.y)
        if d <= self.hero.walk_deadzone:
            return
        step = self.hero.speed * DT
        self.hero.x += (tx - self.hero.x) / d * step
        self.hero.y += (ty - self.hero.y) / d * step

    def _update_camera(self):
        self.cam_x = self.hero.x - self.config["world"]["screen_w"] / 2.0
        self.cam_y = self.hero.y - self.config["world"]["screen_h"] / 2.0

    # ---------- enemies ----------

    def _spawn(self):
        sp = self.config["spawn"]
        self.spawn_timer += DT
        if self.spawn_timer < sp["interval"]:
            return
        self.spawn_timer = 0.0
        row = wave(self.config, self.time)
        if row.get("boss") and not self.boss_alive:
            self._spawn_one(row["boss"])  # the boss appears once
            self.boss_alive = True
        normal = sum(1 for e in self.enemies if not e.boss)
        if not row["types"] or normal >= row["min_alive"]:
            return
        n = min(sp["max_per_tick"], row["min_alive"] - normal,
                sp["alive_cap"] - len(self.enemies))
        for _ in range(n):
            self._spawn_one(random.choice(row["types"]))

    def _spawn_one(self, kind):
        sp = self.config["spawn"]
        angle = random.uniform(0.0, 2.0 * math.pi)
        e = Enemy(self.hero.x + sp["circle_radius"] * math.cos(angle),
                  self.hero.y + sp["circle_radius"] * math.sin(angle),
                  kind, self.config["enemies"][kind])
        self.enemies.append(e)
        return e

    def _move_enemies(self):
        sp = self.config["spawn"]
        keep = []
        for e in self.enemies:
            e.tick_hit_cd()
            d = _dist(self.hero.x, self.hero.y, e.x, e.y)
            if e.boss:
                # the boss is never removed: it comes back to the spawn circle
                if d > sp["boss_return_radius"]:
                    angle = random.uniform(0.0, 2.0 * math.pi)
                    e.x = self.hero.x + sp["circle_radius"] * math.cos(angle)
                    e.y = self.hero.y + sp["circle_radius"] * math.sin(angle)
                    d = sp["circle_radius"]
            elif d > sp["cull_radius"]:
                continue
            if d > 0.0:
                step = e.speed * DT
                e.x += (self.hero.x - e.x) / d * step
                e.y += (self.hero.y - e.y) / d * step
            if d <= self.hero.hit_radius + e.hit_radius and e.can_be_hit_by("contact"):
                e.hit_cd["contact"] = self.config["contact_cooldown"]
                self.hero.hp -= e.damage
                # being hit moves the screen a little and makes a sound
                self.shake = self.config["feel"]["hurt_shake_s"]
                self.events.append("hurt")
            keep.append(e)
        self.enemies = keep
        if self.hero.hp <= 0.0:
            self.hero.hp = 0.0
            self.dead = True
            self.events.append("lose")

    def _damage(self, enemy, amount):
        feel = self.config["feel"]
        enemy.hp -= amount
        self.events.append("hit")
        self.numbers.append(Number(
            enemy.x + random.uniform(-feel["number_jitter"], feel["number_jitter"]),
            enemy.y, str(int(round(amount))), feel["number_lifetime"]))
        while len(self.numbers) > feel["number_max"]:
            self.numbers.pop(0)
        if enemy.hp <= 0.0 and not enemy.dead:
            enemy.dead = True
            self.kills += 1
            self.pops.append(Pop(enemy.x, enemy.y, enemy.hit_radius,
                                 feel["flash_lifetime"]))
            if enemy.xp > 0:
                self.gems.append(Gem(enemy.x, enemy.y, enemy.xp))

    def _tick_feel(self):
        """The damage figures float up, the flashes and the shake run out."""
        feel = self.config["feel"]
        rise = feel["number_rise"] * DT
        for n in self.numbers:
            n.y -= rise
            n.life -= DT
        self.numbers = [n for n in self.numbers if n.life > 0.0]
        for p in self.pops:
            p.life -= DT
        self.pops = [p for p in self.pops if p.life > 0.0]
        self.shake = max(0.0, self.shake - DT)

    def _clear_dead(self):
        self.enemies = [e for e in self.enemies if not e.dead]

    # ---------- weapons ----------

    def _do_weapons(self):
        for w in self.hero.weapons:
            stats = weapon_stats(self.config, w.kind, w.level)
            if stats["mode"] == "projectile":
                self._fire_projectiles(w, stats)
            elif stats["mode"] == "orbit":
                self._spin_blades(w, stats)
            elif stats["mode"] == "ring":
                self._holy_ring(w, stats)
        self._clear_dead()

    def _fire_projectiles(self, w, stats):
        w.cd = max(0.0, w.cd - DT)
        if w.cd > 0.0 or not self.enemies:
            return
        w.cd = stats["cooldown"]
        near = sorted(self.enemies,
                      key=lambda e: _dist(e.x, e.y, self.hero.x, self.hero.y))
        for i in range(stats["count"]):
            e = near[i % len(near)]
            d = _dist(e.x, e.y, self.hero.x, self.hero.y) or 1.0
            speed = stats["speed"]
            self.projectiles.append(Projectile(
                self.hero.x, self.hero.y,
                (e.x - self.hero.x) / d * speed, (e.y - self.hero.y) / d * speed,
                stats["damage"], stats["lifetime"], "spark",
                self.hero.hit_radius + stats["radius_bonus"]))

    def _spin_blades(self, w, stats):
        w.angle = (w.angle + 2.0 * math.pi / stats["turn_s"] * DT) % (2.0 * math.pi)
        for i in range(stats["count"]):
            a = w.angle + i * 2.0 * math.pi / stats["count"]
            bx = self.hero.x + stats["orbit_radius"] * math.cos(a)
            by = self.hero.y + stats["orbit_radius"] * math.sin(a)
            key = "blade-%d" % i
            for e in self.enemies:
                if not e.can_be_hit_by(key):
                    continue
                if _dist(bx, by, e.x, e.y) <= stats["blade_radius"] + e.projectile_radius:
                    e.hit_cd[key] = stats["hit_cooldown"]
                    self._damage(e, stats["damage"])

    def _holy_ring(self, w, stats):
        w.cd = max(0.0, w.cd - DT)
        if w.cd > 0.0:
            return
        w.cd = stats["cooldown"]
        for e in self.enemies:
            if _dist(e.x, e.y, self.hero.x, self.hero.y) <= stats["radius"] + e.hit_radius:
                self._damage(e, stats["damage"])

    def _move_projectiles(self):
        for p in self.projectiles:
            p.x += p.vx * DT
            p.y += p.vy * DT
            p.remaining -= DT
            if p.remaining <= 0.0:
                p.dead = True
                continue
            for e in self.enemies:
                if e.dead:
                    continue
                if _dist(p.x, p.y, e.x, e.y) <= p.hit_dist(e):
                    p.dead = True
                    self._damage(e, p.damage)
                    break
        self.projectiles = [p for p in self.projectiles if not p.dead]
        self._clear_dead()

    # ---------- gems, XP and level-up ----------

    def _move_gems(self):
        g = self.config["growth"]
        keep = []
        for gem in self.gems:
            d = _dist(gem.x, gem.y, self.hero.x, self.hero.y)
            if d <= self.hero.hit_radius + g["gem_radius"]:
                self._gain_xp(gem.xp)
                self.events.append("gem")
                continue
            if d <= self.hero.magnet_radius and d > 0.0:
                step = g["gem_speed"] * DT
                gem.x += (self.hero.x - gem.x) / d * step
                gem.y += (self.hero.y - gem.y) / d * step
            keep.append(gem)
        self.gems = keep

    def xp_needed(self):
        g = self.config["growth"]
        return g["xp_first"] + g["xp_step"] * (self.hero.level - 1)

    def _gain_xp(self, amount):
        self.hero.xp += amount
        while self.hero.xp >= self.xp_needed():
            self.hero.xp -= self.xp_needed()
            self.hero.level += 1
            self.pending_levels += 1

    def _offer_cards(self):
        """3 random cards: a new weapon, a weapon level, a passive, or a heal."""
        growth = self.config["growth"]
        owned = {w.kind: w for w in self.hero.weapons}
        pool = []
        for kind in self.config["weapons"]:
            if kind in owned:
                if owned[kind].level < growth["max_level"]:
                    pool.append(("weapon", kind))
            elif len(owned) < growth["max_weapons"]:
                pool.append(("new", kind))
        for kind in self.config["passives"]:
            if self.hero.passives.get(kind, 0) < growth["max_level"]:
                pool.append(("passive", kind))
        random.shuffle(pool)
        self.cards = [self._make_card(t, k) for t, k in pool[:growth["cards"]]]
        while len(self.cards) < growth["cards"]:
            self.cards.append(self._make_card("heal", None))

    def _make_card(self, kind_type, weapon_kind):
        growth = self.config["growth"]
        if kind_type == "heal":
            return {"type": "heal", "kind": None,
                    "name": growth["heal_card_name"], "level": None,
                    "text": "Heal %d HP" % growth["heal_card_hp"]}
        if kind_type == "new":
            spec = self.config["weapons"][weapon_kind]
            return {"type": "new", "kind": weapon_kind, "name": spec["name"],
                    "level": 1, "text": spec["card_text"]}
        if kind_type == "weapon":
            spec = self.config["weapons"][weapon_kind]
            level = next(w.level for w in self.hero.weapons if w.kind == weapon_kind)
            return {"type": "weapon", "kind": weapon_kind, "name": spec["name"],
                    "level": level + 1, "text": spec["per_level_text"]}
        spec = self.config["passives"][weapon_kind]
        level = self.hero.passives.get(weapon_kind, 0)
        return {"type": "passive", "kind": weapon_kind, "name": spec["name"],
                "level": level + 1, "text": spec["per_level_text"]}

    def choose(self, index):
        """Pick card `index` (0, 1 or 2). Returns False when nothing is open."""
        if not self.choosing or not 0 <= index < len(self.cards):
            return False
        card = self.cards[index]
        if card["type"] == "heal":
            self.hero.hp = min(self.hero.max_hp,
                               self.hero.hp + self.config["growth"]["heal_card_hp"])
        elif card["type"] == "new":
            self.hero.weapons.append(Weapon(card["kind"], 1))
        elif card["type"] == "weapon":
            next(w for w in self.hero.weapons if w.kind == card["kind"]).level += 1
        else:
            self.hero.passives[card["kind"]] = \
                self.hero.passives.get(card["kind"], 0) + 1
            self.hero.apply_passives(self.config["passives"])
            heal = self.config["passives"][card["kind"]].get("pick_heal", 0.0)
            self.hero.hp = min(self.hero.max_hp, self.hero.hp + heal)
        self.pending_levels -= 1
        if self.pending_levels > 0:
            self._offer_cards()
        else:
            self.cards = []
            self.choosing = False
        return True
