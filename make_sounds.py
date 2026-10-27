"""Make the short sound files in sounds/ using only the standard library.

Run this on your computer:  python make_sounds.py
It writes plain .wav files (one second of numbers, nothing clever), and main.py
only loads the finished files.
"""

import math
import os
import random
import struct
import wave

RATE = 22050          # samples per second
AMPLITUDE = 0.5       # how loud the files are; 1.0 would be the loudest
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sounds")


def count(seconds):
    """How many samples one length of time is."""
    return int(RATE * seconds)


def tone(freq, seconds, amp=1.0, fade=5.0, glide=0.0):
    """One note that gets quieter. glide moves the pitch while it plays."""
    out = []
    phase = 0.0
    n = count(seconds)
    for i in range(n):
        part = i / n
        # a very short soft start, so the note does not click
        start = 1.0 - math.exp(-900.0 * part)
        phase += 2.0 * math.pi * freq * (1.0 + glide * part) / RATE
        out.append(amp * start * math.exp(-fade * part) * math.sin(phase))
    return out


def noise(seconds, amp=1.0, fade=14.0):
    """A short hiss, for the small 'tick' of a hit."""
    out = []
    last = 0.0
    n = count(seconds)
    for i in range(n):
        part = i / n
        last = 0.6 * last + 0.4 * random.uniform(-1.0, 1.0)
        out.append(amp * math.exp(-fade * part) * last * 2.5)
    return out


def notes(freqs, each, fade=5.0, amp=1.0):
    """The same note played one after another, as one long sound."""
    out = []
    for freq in freqs:
        out += tone(freq, each, amp, fade)
    return out


def place(track, part, at=0.0):
    """Add `part` into `track` starting at `at` seconds, making it longer if needed."""
    start = count(at)
    if len(track) < start + len(part):
        track.extend([0.0] * (start + len(part) - len(track)))
    for i, value in enumerate(part):
        track[start + i] += value
    return track


def save(name, track):
    """Write one mono 16-bit .wav, with the loudest point set to AMPLITUDE."""
    peak = max((abs(v) for v in track), default=0.0) or 1.0
    scale = AMPLITUDE / peak
    packed = [int(max(-1.0, min(1.0, v * scale)) * 32767) for v in track]
    path = os.path.join(OUT, name)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(struct.pack("<%dh" % len(packed), *packed))
    print("%-11s %4.0f ms" % (name, 1000.0 * len(track) / RATE))


# ---- the six sounds of the game -------------------------------------------

def hit():
    """A small tick: something hurt an enemy."""
    track = []
    place(track, noise(0.045, 1.0, fade=26.0))
    place(track, tone(760, 0.05, 0.6, fade=16.0, glide=-0.5), 0.0)
    return track


def gem():
    """A bright ping, going up."""
    track = []
    place(track, tone(880, 0.06, 1.0, fade=9.0))
    place(track, tone(1320, 0.09, 0.9, fade=9.0), 0.05)
    return track


def level():
    """Three rising notes: a card is waiting."""
    return notes([523.25, 659.25, 880.0], 0.09, fade=6.0)


def hurt():
    """A low thud with a little grit: the hero was hit."""
    track = tone(180, 0.16, 1.0, fade=7.0, glide=-0.45)
    place(track, noise(0.06, 0.5, fade=20.0))
    return track


def win():
    """Four notes up and one long one: you made it to 2:00."""
    track = notes([523.25, 659.25, 783.99, 1046.5], 0.11, fade=5.0)
    place(track, tone(1046.5, 0.5, 0.8, fade=3.5), 0.44)
    place(track, tone(1318.5, 0.5, 0.5, fade=3.5), 0.44)
    return track


def lose():
    """Three notes down: game over."""
    return notes([392.0, 311.13, 233.09], 0.19, fade=4.5)


SOUNDS = (hit, gem, level, hurt, win, lose)


if __name__ == "__main__":
    random.seed(7)  # the same sounds every time you run this
    os.makedirs(OUT, exist_ok=True)
    for make in SOUNDS:
        save(make.__name__ + ".wav", make())
    print("wrote %d sounds to %s" % (len(SOUNDS), OUT))
