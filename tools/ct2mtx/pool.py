# SPDX-License-Identifier: MPL-2.0
"""A small pool of alternate drum sounds, synthesised here (deterministic, no recordings: free to ship), for the
samples a conversion leaves out (too long, or past the bank's room). Each a short one-shot at 22050 Hz.

category(name) guesses what a Circuit sample is from its name ("Std Kick", "909 OH", "Clap 2"); the pool's sound of
that category stands in for it."""
import math

SR = 22050
CATEGORIES = ("kick", "snare", "clap", "hat", "openhat", "tom", "rim", "cowbell", "shaker", "cymbal", "perc")
_WORDS = [("openhat", ("oh", "open", "ohh", "o-hat", "ohat")), ("hat", ("hh", "hat", "ch", "chh", "hihat", "hi-hat")),
          ("kick", ("kick", "bd", "bass drum", "kck", "kik")), ("snare", ("snare", "sd", "snr")),
          ("clap", ("clap", "cp", "clp")), ("tom", ("tom", "conga", "bongo")), ("rim", ("rim", "rs", "stick", "click")),
          ("cowbell", ("cow", "bell", "agogo")), ("shaker", ("shak", "tamb", "maraca", "cabasa", "shk")),
          ("cymbal", ("crash", "ride", "cym", "splash", "china"))]


def category(name):
    n = " " + name.lower().replace("_", " ").replace("-", " ") + " "
    for cat, words in _WORDS:
        for w in words:
            if (" " + w + " ") in n or (len(w) > 3 and w in n) or n.strip().startswith(w + " ") or \
                    n.strip().endswith(" " + w) or n.strip() == w:
                return cat
    return None


class _Rng:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def __call__(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s / 2147483648.0 - 1.0


def _env(i, n, attack=0.002, curve=6.0):
    t = i / SR
    a = min(1.0, t / attack) if attack > 0 else 1.0
    return a * math.exp(-curve * i / n)


def _hp(x, hz):
    a = math.exp(-2 * math.pi * hz / SR)
    y, px, out = 0.0, 0.0, []
    for v in x:
        y = a * (y + v - px)
        px = v
        out.append(y)
    return out


def _bp(x, hz, q):
    f = 2 * math.sin(math.pi * min(hz, SR * 0.16) / SR)   # (the state-variable filter is stable well under SR / 6)
    lo = bp = 0.0
    out = []
    for v in x:
        hi = v - lo - bp / q
        bp += f * hi
        lo += f * bp
        out.append(bp)
    return out


def _norm(x, peak=0.9):
    m = max(1e-9, max(abs(v) for v in x))
    return [v * peak / m for v in x]


def make(cat):
    """the pool's sound of a category, mono floats at SR"""
    r = _Rng(sum(map(ord, cat)) * 7919)
    if cat == "kick":
        n = int(0.38 * SR)
        ph, out = 0.0, []
        for i in range(n):
            f = 48 + 110 * math.exp(-i / (0.03 * SR))
            ph += 2 * math.pi * f / SR
            out.append(math.sin(ph) * _env(i, n, 0.001, 5.5) + (r() * 0.25 if i < 60 else 0))
        return _norm(out)
    if cat == "snare":
        n = int(0.24 * SR)
        ph, out = 0.0, []
        for i in range(n):
            ph += 2 * math.pi * (185 + 40 * math.exp(-i / 400)) / SR
            out.append(0.55 * math.sin(ph) * _env(i, n, 0.001, 9) + 0.75 * r() * _env(i, n, 0.001, 6))
        return _norm(_hp(out, 150))
    if cat == "clap":
        n = int(0.26 * SR)
        noise = [r() for _ in range(n)]
        out = []
        for i in range(n):
            t = i / SR
            bursts = sum(math.exp(-(t - k * 0.011) * 180) for k in range(3) if t >= k * 0.011)
            tail = math.exp(-(t - 0.033) * 14) * 0.6 if t > 0.033 else 0
            out.append(noise[i] * (bursts + tail))
        return _norm(_bp(out, 1150, 1.4))
    if cat in ("hat", "openhat"):
        n = int((0.07 if cat == "hat" else 0.42) * SR)
        freqs = (263, 400, 421, 474, 587, 845)
        phs = [0.0] * 6
        out = []
        for i in range(n):
            m = 0.0
            for k, f in enumerate(freqs):
                phs[k] += f * 3.1 / SR
                m += 1.0 if (phs[k] % 1.0) < 0.5 else -1.0
            out.append((m / 6 * 0.6 + r() * 0.4) * _env(i, n, 0.0005, 5 if cat == "hat" else 4))
        return _norm(_hp(_hp(out, 5000), 7000))
    if cat == "tom":
        n = int(0.35 * SR)
        ph, out = 0.0, []
        for i in range(n):
            ph += 2 * math.pi * (95 + 60 * math.exp(-i / (0.05 * SR))) / SR
            out.append(math.sin(ph) * _env(i, n, 0.001, 5))
        return _norm(out)
    if cat == "rim":
        n = int(0.06 * SR)
        out = [(math.sin(2 * math.pi * 1700 * i / SR) * 0.7 + r() * 0.3) * _env(i, n, 0.0002, 9) for i in range(n)]
        return _norm(_hp(out, 500))
    if cat == "cowbell":
        n = int(0.3 * SR)
        out = []
        for i in range(n):
            a = 1.0 if (i * 540 / SR) % 1.0 < 0.5 else -1.0
            b = 1.0 if (i * 800 / SR) % 1.0 < 0.5 else -1.0
            out.append((a + b) * 0.5 * _env(i, n, 0.0005, 7))
        return _norm(_bp(out, 2600, 1.2))
    if cat == "shaker":
        n = int(0.12 * SR)
        out = [r() * math.sin(math.pi * i / n) ** 2 for i in range(n)]
        return _norm(_hp(out, 4500), 0.7)
    if cat == "cymbal":
        n = int(0.8 * SR)
        out = [r() * _env(i, n, 0.001, 3.5) for i in range(n)]
        return _norm(_hp(_hp(out, 3000), 5000), 0.7)
    # perc: a short tuned blip
    n = int(0.15 * SR)
    return _norm([math.sin(2 * math.pi * 520 * i / SR) * _env(i, n, 0.001, 8) for i in range(n)])
