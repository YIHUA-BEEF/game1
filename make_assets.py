"""Run this on your computer:  python make_assets.py

It makes assets/<name>.png: 3x bigger copies of every picture in raw_art/
with NEAREST (blocky pixel art, no blurring), plus two bright crystal gems
coloured from raw_art/gem.png: blue for XP 1, pink for XP 2.
raw_art/ is never changed. main.py only reads the finished files in assets/.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "raw_art")
OUT = os.path.join(HERE, "assets")
SCALE = 3

# file name -> (bright colour at the top, deeper colour at the bottom)
GEMS = {
    "gem_blue.png": ((120, 200, 255), (30, 80, 210)),   # XP 1
    "gem_pink.png": ((255, 160, 230), (205, 35, 150)),  # XP 2
}


def upscale(im):
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST)


def recolour(base, top, bottom):
    """Keep the shape and the shading of `base`, but paint it in two tones."""
    px = base.load()
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dst = out.load()
    for y in range(base.height):
        t = y / max(1, base.height - 1)
        band = [int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)]
        for x in range(base.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            light = 0.45 + 0.85 * ((r + g + b) / (3 * 255.0))
            colour = tuple(min(255, int(band[i] * light)) for i in range(3))
            dst[x, y] = colour + (a,)
    return out


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("raw_art/ not found next to this script")
    os.makedirs(OUT, exist_ok=True)

    for name in sorted(os.listdir(SRC)):
        if not name.lower().endswith(".png"):
            continue
        im = Image.open(os.path.join(SRC, name)).convert("RGBA")
        big = upscale(im)
        big.save(os.path.join(OUT, name))
        print("%-14s %s -> %s" % (name, im.size, big.size))

    gem = Image.open(os.path.join(SRC, "gem.png")).convert("RGBA")
    for name, (top, bottom) in sorted(GEMS.items()):
        big = upscale(recolour(gem, top, bottom))
        big.save(os.path.join(OUT, name))
        print("%-14s %s -> %s (from gem.png)" % (name, gem.size, big.size))

    print("done: pictures are in", OUT)


if __name__ == "__main__":
    main()
