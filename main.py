"""Night Survivors - window, drawing and input.

Everything the player sees is here. rules.py decides what happens, this file
draws it. Pictures come from assets/ (made by make_assets.py); when a file is
missing a coloured shape is drawn instead, so the game still runs.
"""

import asyncio
import json
import math
import os
import random
import time

import pygame

from rules import DT, Game, weapon_stats

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "data", "game.json"), encoding="utf-8"))

W = CFG["world"]["screen_w"]
H = CFG["world"]["screen_h"]
TILE = CFG["world"]["tile"]

FLOOR_A = (46, 50, 64)
FLOOR_B = (40, 44, 58)
GRID = (58, 64, 82)
HERO_COLOR = (90, 220, 160)
WAND_COLOR = (250, 210, 90)
BAT_COLOR = (150, 90, 190)
GEM_COLOR = (110, 170, 250)
RING_COLOR = (255, 235, 150)
HP_COLOR = (220, 70, 70)
HP_BACK = (70, 40, 45)
XP_COLOR = (80, 150, 240)
XP_BACK = (35, 50, 80)
TEXT_COLOR = (245, 245, 250)
SHADOW_COLOR = (15, 15, 25)
CARD_COLOR = (38, 42, 60)
CARD_EDGE = (120, 130, 170)
CARD_HOT = (255, 220, 120)
NUMBER_COLOR = (255, 255, 255)

# the three level-up cards
CARD_W = W - 40
CARD_H = 150
CARD_GAP = 16
CARD_TOP = (H - (3 * CARD_H + 2 * CARD_GAP)) // 2


# name -> picture, or None when the file is not there yet
ART = {}


def card_rect(i):
    return pygame.Rect((W - CARD_W) // 2, CARD_TOP + i * (CARD_H + CARD_GAP),
                       CARD_W, CARD_H)


def card_at(pos, count):
    """Which card is under (x, y)? None when the tap missed every card."""
    for i in range(count):
        if card_rect(i).collidepoint(pos):
            return i
    return None


def picture_names():
    names = [CFG["art"]["floor"], CFG["art"]["blades"], CFG["hero"]["picture"]]
    for enemy in CFG["enemies"].values():
        names.append(enemy["picture"])
    for gem in CFG["art"]["gems"]:
        names.append(gem["picture"])
    return names


def gem_picture(xp):
    """Blue crystal for XP 1, pink for XP 2 (the list is sorted big to small)."""
    for entry in CFG["art"]["gems"]:
        if xp >= entry["min_xp"]:
            return entry["picture"]
    return CFG["art"]["gems"][-1]["picture"]


def load_art():
    """Only finished files from assets/ - nothing is made at run time."""
    folder = os.path.join(HERE, CFG["art"]["dir"])
    for name in picture_names():
        path = os.path.join(folder, name)
        try:
            ART[name] = pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error):
            ART[name] = None
            print("no picture for %s (run make_assets.py) - using a shape" % name)


def sound_file(name):
    """sounds/name with .ogg if we have that, then .wav. None when neither is there."""
    folder = os.path.join(HERE, CFG["sounds"]["dir"])
    stem = os.path.splitext(name)[0]
    for ext in (".ogg", ".wav"):
        path = os.path.join(folder, stem + ext)
        if os.path.exists(path):
            return path
    return None


def load_sounds():
    """Only finished files from sounds/ - nothing is made at run time."""
    cfg = CFG["sounds"]
    for key, name in cfg["files"].items():
        path = sound_file(name)
        SOUNDS[key] = None
        if path is None:
            print("no sound for %s (run make_sounds.py)" % key)
            continue
        try:
            sound = pygame.mixer.Sound(path)
        except pygame.error:
            print("cannot read %s" % path)
            continue
        sound.set_volume(cfg["volume"])
        SOUNDS[key] = sound


def play_events(game):
    """Play one sound for each thing that happened in the rules since last time.

    Hits and gems come in crowds, so `gap` in the data file says how long to
    wait before playing that sound again.
    """
    gaps = CFG["sounds"]["gap"]
    for name in game.take_events():
        sound = SOUNDS.get(name)
        if sound is None:
            continue
        gap = gaps.get(name, 0.0)
        since = game.time - last_sound.get(name, -10.0)
        if gap and 0.0 <= since < gap:
            continue
        last_sound[name] = game.time
        sound.play()


def blit_center(surf, image, x, y):
    rect = image.get_rect()
    rect.center = (int(x), int(y))
    surf.blit(image, rect)


def make_fonts():
    return {
        "ui": pygame.font.Font(None, 26),
        "big": pygame.font.Font(None, 64),
        "small": pygame.font.Font(None, 22),
        "number": pygame.font.Font(None, CFG["feel"]["number_size"]),
    }


# name -> pygame.mixer.Sound, or None when the file is not there yet
SOUNDS = {}

# when each sound was last played, so a crowd of hits is not a wall of noise
last_sound = {}


def draw_floor(surf, cam_x, cam_y):
    """One tile repeated forever: the map has no edges."""
    tile = ART.get(CFG["art"]["floor"])
    size = tile.get_width() if tile else TILE
    x0 = int(cam_x // size) * size
    y0 = int(cam_y // size) * size
    col = 0
    y = y0 - size
    while y - cam_y < H:
        row = 0
        x = x0 - size
        while x - cam_x < W:
            sx, sy = int(x - cam_x), int(y - cam_y)
            if tile:
                surf.blit(tile, (sx, sy))
            else:
                color = FLOOR_A if (row + col) % 2 == 0 else FLOOR_B
                pygame.draw.rect(surf, color, (sx, sy, size, size))
                pygame.draw.rect(surf, GRID, (sx, sy, size, size), 1)
            x += size
            row += 1
        y += size
        col += 1


def draw_sprite(surf, spec, fallback_color, x, y, cam_x, cam_y):
    """A picture from assets/ when we have one, a coloured shape when not."""
    sx, sy = x - cam_x, y - cam_y
    image = ART.get(spec["picture"]) if spec.get("picture") else None
    if image:
        size = spec.get("picture_size", CFG["art"]["picture_size"])
        if size != image.get_width():
            image = pygame.transform.scale_by(image, size / image.get_width())
        blit_center(surf, image, sx, sy)
    else:
        pygame.draw.circle(surf, fallback_color, (int(sx), int(sy)),
                           int(spec["hit_radius"]))


def on_screen(x, y, cam_x, cam_y, margin=64):
    sx, sy = x - cam_x, y - cam_y
    return -margin <= sx <= W + margin and -margin <= sy <= H + margin


def draw_gems(surf, game, cx, cy):
    for gem in game.gems:
        if not on_screen(gem.x, gem.y, cx, cy):
            continue
        image = ART.get(gem_picture(gem.xp))
        if image:
            blit_center(surf, image, gem.x - cx, gem.y - cy)
        else:
            pygame.draw.circle(surf, GEM_COLOR, (int(gem.x - cx), int(gem.y - cy)),
                               int(CFG["growth"]["gem_radius"]))


def draw_weapons(surf, game, cx, cy):
    """The holy ring circle and the spinning blades, at their real places."""
    hero = game.hero
    hx, hy = hero.x - cx, hero.y - cy
    for w in hero.weapons:
        stats = weapon_stats(CFG, w.kind, w.level)
        if stats["mode"] == "ring":
            pygame.draw.circle(surf, RING_COLOR, (int(hx), int(hy)),
                               int(stats["radius"]), 2)
        elif stats["mode"] == "orbit":
            image = ART.get(CFG["art"]["blades"])
            for i in range(stats["count"]):
                a = w.angle + i * 2.0 * math.pi / stats["count"]
                bx = hx + stats["orbit_radius"] * math.cos(a)
                by = hy + stats["orbit_radius"] * math.sin(a)
                if image:
                    blit_center(surf, image, bx, by)
                else:
                    pygame.draw.circle(surf, (210, 215, 230), (int(bx), int(by)),
                                       int(stats["blade_radius"]))


def draw_pops(surf, game, cx, cy):
    """The white flash each dead enemy leaves behind."""
    feel = CFG["feel"]
    life = feel["flash_lifetime"]
    color = tuple(feel["flash_color"])
    for pop in game.pops:
        frac = pop.life / life                      # 1 when new, 0 when gone
        radius = int(pop.radius + feel["flash_grow"] * (1.0 - frac))
        sheet = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(sheet, color + (int(180 * frac),),
                           (radius + 2, radius + 2), radius, 2)
        surf.blit(sheet, (int(pop.x - cx) - radius - 2, int(pop.y - cy) - radius - 2))


def draw_numbers(surf, game, font, cx, cy):
    """The damage figures, floating up and fading out."""
    life = CFG["feel"]["number_lifetime"]
    for number in game.numbers:
        sx, sy = number.x - cx, number.y - cy
        if not -40 < sx < W + 40 or not -40 < sy < H + 40:
            continue
        shade = font.render(number.text, True, SHADOW_COLOR)
        shade.set_alpha(int(200 * number.life / life))
        surf.blit(shade, (int(sx) + 1, int(sy) + 1))
        img = font.render(number.text, True, NUMBER_COLOR)
        img.set_alpha(int(255 * number.life / life))
        surf.blit(img, (int(sx), int(sy)))


def shake_offset(game):
    """How many pixels to move the whole picture because the hero was hurt."""
    feel = CFG["feel"]
    if game.shake <= 0.0:
        return 0.0, 0.0
    px = feel["hurt_shake_px"] * game.shake / feel["hurt_shake_s"]
    return random.uniform(-px, px), random.uniform(-px, px)


def draw_entities(surf, game, cx, cy):
    draw_weapons(surf, game, cx, cy)
    draw_pops(surf, game, cx, cy)
    draw_gems(surf, game, cx, cy)
    for e in game.enemies:
        if on_screen(e.x, e.y, cx, cy):
            draw_sprite(surf, CFG["enemies"][e.kind], BAT_COLOR,
                        e.x, e.y, cx, cy)
    for p in game.projectiles:
        if on_screen(p.x, p.y, cx, cy):
            pygame.draw.circle(surf, WAND_COLOR,
                               (int(p.x - cx), int(p.y - cy)), 5)
    draw_sprite(surf, CFG["hero"], HERO_COLOR,
                game.hero.x, game.hero.y, cx, cy)


def inventory_text(game):
    """What you have, for example 'Spark 2  Blades 1  Boots 1'."""
    parts = ["%s %d" % (CFG["weapons"][w.kind]["short"], w.level)
             for w in game.hero.weapons]
    parts += ["%s %d" % (CFG["passives"][k]["short"], v)
              for k, v in sorted(game.hero.passives.items()) if v]
    return "  ".join(parts)


def blit_text(surf, font, text, x, y, right_edge=None):
    """Light text with a dark shadow, so it stays readable on the floor tile."""
    img = font.render(text, True, TEXT_COLOR)
    if right_edge is not None:
        x = right_edge - img.get_width()
    surf.blit(font.render(text, True, SHADOW_COLOR), (x + 1, y + 1))
    surf.blit(img, (x, y))


def clock_text(seconds):
    return "%d:%02d" % (int(seconds // 60), int(seconds % 60))


def draw_hud(surf, fonts, game):
    h = game.hero
    pygame.draw.rect(surf, HP_BACK, (12, 12, 150, 14))
    frac = max(0.0, h.hp / h.max_hp)
    pygame.draw.rect(surf, HP_COLOR, (12, 12, int(150 * frac), 14))
    pygame.draw.rect(surf, (200, 200, 210), (12, 12, 150, 14), 1)
    pygame.draw.rect(surf, XP_BACK, (12, 30, 150, 8))
    xp_frac = min(1.0, h.xp / game.xp_needed())
    pygame.draw.rect(surf, XP_COLOR, (12, 30, int(150 * xp_frac), 8))
    blit_text(surf, fonts["ui"], "Lv %d" % h.level, 12, 42)
    blit_text(surf, fonts["ui"],
              "%s / %s" % (clock_text(game.time), clock_text(CFG["win_time"])),
              0, 12, right_edge=W - 12)
    blit_text(surf, fonts["small"], inventory_text(game),
              12, H - fonts["small"].get_height() - 12)


def draw_cards(surf, fonts, game, mouse):
    """The level-up pause: 3 big cards, click or tap one."""
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((10, 10, 20, 215))
    surf.blit(veil, (0, 0))
    blit_centered_text(surf, fonts["ui"], "Level %d! Choose a card"
                       % game.hero.level, CARD_TOP - 44)
    for i, card in enumerate(game.cards):
        rect = card_rect(i)
        hot = rect.collidepoint(mouse)
        pygame.draw.rect(surf, CARD_COLOR, rect, border_radius=10)
        pygame.draw.rect(surf, CARD_HOT if hot else CARD_EDGE, rect,
                         3, border_radius=10)
        title = card["name"]
        if card["level"] is not None:
            title += "  Lv %d" % card["level"]
        blit_centered_text(surf, fonts["ui"], title, rect.y + 22)
        blit_centered_text(surf, fonts["small"], card["text"], rect.y + 62)


def blit_centered_text(surf, font, text, y):
    blit_text(surf, font, text, W // 2 - font.size(text)[0] // 2, y)


def draw_end(surf, fonts, game):
    """VICTORY or GAME OVER, with the time, the kills and the level."""
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((10, 10, 20, 205))
    surf.blit(veil, (0, 0))
    title = "VICTORY" if game.won else "GAME OVER"
    color = (120, 240, 160) if game.won else (245, 245, 250)
    img = fonts["big"].render(title, True, color)
    surf.blit(fonts["big"].render(title, True, SHADOW_COLOR),
              (W // 2 - img.get_width() // 2 + 2, H // 2 - 62))
    surf.blit(img, (W // 2 - img.get_width() // 2, H // 2 - 64))
    blit_centered_text(surf, fonts["ui"],
                       "%s   kills %d   Lv %d" % (clock_text(game.time),
                                                  game.kills, game.hero.level),
                       H // 2 + 6)
    blit_centered_text(surf, fonts["ui"], "click to play again", H // 2 + 44)


def draw_paused(surf, fonts):
    blit_centered_text(surf, fonts["big"], "PAUSED",
                       H // 2 - fonts["big"].get_height() // 2)


async def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        print("no sound device - the game stays quiet")
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Night Survivors")
    fonts = make_fonts()
    load_art()
    load_sounds()
    clock = pygame.time.Clock()
    game = Game(CFG)

    def tap(pos):
        """One click or one finger touch: choose a card, or play again."""
        if game.choosing:
            index = card_at(pos, len(game.cards))
            if index is not None:
                game.choose(index)
        elif game.dead or game.won:
            game.reset()

    running = True
    paused = False
    touch = None
    used_touch = False
    accumulator = 0.0
    last = time.perf_counter()

    while running:
        now = time.perf_counter()
        accumulator += min(now - last, 0.25)
        last = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                paused = not paused
            elif event.type == pygame.MOUSEBUTTONDOWN:
                tap(event.pos)
            elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
                used_touch = True
                touch = (event.x * W, event.y * H)
                if event.type == pygame.FINGERDOWN:
                    tap(touch)
            elif event.type == pygame.FINGERUP:
                used_touch = True
                touch = None

        if used_touch:
            # phone style: walk toward the finger, stop when it is lifted
            target = touch
        else:
            # computer style: keep walking toward the mouse pointer
            target = pygame.mouse.get_pos()

        while accumulator >= DT and running:
            if not paused and not (game.dead or game.won):
                game.step(target)
            accumulator -= DT

        play_events(game)
        # the whole picture moves a few pixels when the hero is hurt
        ox, oy = shake_offset(game)
        cx, cy = game.cam_x + ox, game.cam_y + oy

        draw_floor(screen, cx, cy)
        draw_entities(screen, game, cx, cy)
        draw_numbers(screen, game, fonts["number"], cx, cy)
        draw_hud(screen, fonts, game)
        mouse = pygame.mouse.get_pos()
        if game.choosing:
            draw_cards(screen, fonts, game, mouse)
        elif game.dead or game.won:
            draw_end(screen, fonts, game)
        elif paused:
            draw_paused(screen, fonts)
        pygame.display.flip()

        clock.tick(60)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
