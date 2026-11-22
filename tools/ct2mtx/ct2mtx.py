#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""ct2mtx: a Novation Circuit Tracks pack (.circuittrackspack) for MiniTraxFM on the M-VAVE FM-1.

    ct2mtx.py PACK.circuittrackspack [-o OUT.mtx] [--projects 1,4,9] [--max-len 1.5] [--fill] [--no-alt] [--wav]

Out: OUT.mtx, a MiniTraxFM backup (fm1-base's backup file: the three project slots, and the sample bank as its
"LSMP" section): restore it from MiniTraxFM's backup page. Beside it OUT.txt, the report: what was converted, what was
approximated, what was left out.

What goes where
  Synth 1, Synth 2, MIDI 1, MIDI 2  -> tracks 1-4, knit voices (Synth 1/2 from the project's own patches; MIDI 1/2,
                                       which played other instruments, a plain knit sound by their register)
  Drum 1-4                          -> tracks 5-8, sample kits: key 1 the track's sample, keys 2-11 the other samples
                                       its steps pick (sample flips), one choke group (a hit cuts the last)
  samples                           -> the bank: only those the converted projects play, at 22050 Hz (4-bit ADPCM:
                                       about 19 s in all), none longer than --max-len (--fill: longer ones too while
                                       there is room, most played first); one left out is replaced by
                                       an alternate from a small synthesised pool by its name's category ("kick",
                                       "OH" ...), unless --no-alt
  patterns, chains, scenes          -> MiniTraxFM patterns (64 steps), scenes and the song: a chain whose patterns
                                       fit 64 steps becomes one pattern; a longer one is laid out in 4-bar blocks
  up to three projects (MiniTraxFM's slots): --projects picks them (pack slots from 1), else the first three with
  notes in them.

Needs the host simulator (./build.sh --host: app/build/host/minitrax_host); it writes the projects with the firmware's
own code (tools/ct2mtx/README.md).
"""
import argparse
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import ctpack  # noqa: E402
import knitmap  # noqa: E402
import pool  # noqa: E402
from consts import TP, DP, tp_drum, DM_SAMPLE, PM_CHOKE1, SC_MULTIPLY, NSTEP, NPATT, NSCENE, NSONG, NDRUM, SN, \
    NSMP_FACT_HOST, TS_HALF, TS_1, TS_2, TS_4, VM  # noqa: E402
import sampleio as sio  # noqa: E402
import loom_samples as ls  # noqa: E402

RATE = 22050
NPROJ = 3
HOST = os.path.join(REPO, "app", "build", "host", "minitrax_host")
TRACK_NAMES = ["synth 1", "synth 2", "midi 1", "midi 2", "drum 1", "drum 2", "drum 3", "drum 4"]
# the Circuit's pattern sync rates (index 0..7) as sixteenths a step, and MiniTraxFM's track scale for each
SYNC_16THS = {0: 1 / 3, 1: 0.5, 2: 2 / 3, 3: 1.0, 4: 4 / 3, 5: 2.0, 6: 8 / 3, 7: 4.0}
SYNC_SCALE = {0: TS_HALF, 1: TS_HALF, 2: TS_1, 3: TS_1, 4: TS_1, 5: TS_2, 6: TS_2, 7: TS_4}
SYNC_NAME = {0: "1/32T", 1: "1/32", 2: "1/16T", 3: "1/16", 4: "1/8T", 5: "1/8", 6: "1/4T", 7: "1/4"}


class Report:
    def __init__(self):
        self.lines = []

    def __call__(self, s=""):
        self.lines.append(s)

    def text(self):
        return "\n".join(self.lines) + "\n"


# ---------------------------------------------------------------------------------------------------- patterns ---

def circuit_track_patterns(ncs, t):
    """track t (0..7: S1 S2 M1 M2 D1..D4)'s eight patterns"""
    if t < 2:
        return ncs.synth_patterns[t * 8:(t + 1) * 8]
    if t < 4:
        return ncs.midi_patterns[(t - 2) * 8:(t - 1) * 8]
    return ncs.drum_patterns[(t - 4) * 8:(t - 3) * 8]


def pattern_steps(pat, warn):
    """a Circuit pattern's steps as they play once, forwards (start..end); its rate"""
    st = pat.settings
    a, b = st.playback_start, st.playback_end
    if b < a:
        a, b = b, a
    a, b = max(0, a), min(31, b)
    steps = list(pat.steps[a:b + 1])
    if st.playback_direction == 1:
        steps.reverse()
    elif st.playback_direction in (2, 3):
        warn(f"a pattern plays {'ping-pong' if st.playback_direction == 2 else 'random'}: converted forwards")
    rate = st.sync_rate if st.sync_rate in SYNC_16THS else 3
    return steps, rate


def chain_sequence(ncs, t, start, end, warn):
    """a track's chain start..end as one run of steps and its rate (the first pattern's: a chain of mixed rates is
    warned about and plays at it)"""
    pats = circuit_track_patterns(ncs, t)
    if end < start:
        start, end = end, start
    seq, rate = [], None
    for p in range(start, end + 1):
        steps, r = pattern_steps(pats[p], warn)
        if rate is None:
            rate = r
        elif r != rate:
            warn(f"{TRACK_NAMES[t]}: a chain mixes rates ({SYNC_NAME[rate]} and {SYNC_NAME[r]}): all at "
                 f"{SYNC_NAME[rate]}")
        seq.extend(steps)
    return seq, rate if rate is not None else 3


SURE = False


def prob_cond(p):
    """the Circuit's probability 0..7 (7 = always) as a condition (0 always, 1..99 a chance)"""
    return 0 if p >= 7 or SURE else max(1, min(99, int(round((p + 1) * 12.5))))


class Ev:
    """one MiniTraxFM step being built"""
    __slots__ = ("notes", "vel", "len", "nudge", "cond", "key", "comp", "cval")

    def __init__(self):
        self.notes, self.vel, self.len, self.nudge, self.cond = [], 0, 0, 0, 0
        self.key, self.comp, self.cval = 0, 0, 0


def place(evs, pos_ticks, nsteps):
    """the step and nudge a position in ticks (24 a step) lands on: within -12..12 of a step"""
    pos_ticks = int(round(pos_ticks))
    st = int(math.floor((pos_ticks + 11) / 24.0))   # (half a step late stays on its step: +12 is a nudge it can take)
    nud = pos_ticks - st * 24
    st %= nsteps
    ev = evs.setdefault(st, Ev())
    return ev, nud


def len_code(q):
    """quarter steps to pattern.h's step length code"""
    q = max(1, int(round(q)))
    return q if q <= 64 else min(112, (q + 3) // 4 + 48)


def keep4(notes, root):
    """a step's notes (NCSNote) as MIDI notes, at most SN of them: when there are more (the Circuit holds six), the
    lowest and the highest (the bass and the top line), then the loudest of the rest (the lower on a tie)"""
    best = {}
    for n in notes:
        m = max(1, min(127, n.note_number - 12 + root))
        best[m] = max(best.get(m, 0), n.velocity)
    ms = sorted(best)
    if len(ms) <= SN:
        return ms
    keep = [ms[0], ms[-1]]
    rest = sorted(ms[1:-1], key=lambda m: (-best[m], m))
    return sorted(keep + rest[:SN - 2])


def synth_events(seq, scale16, root, stats, nsteps):
    """a synth / MIDI track's run of steps (each scale16 sixteenths at the Circuit's rate; nsteps MiniTraxFM steps of a
    sixteenth each when scale16 != 1, else one each) as MiniTraxFM steps"""
    evs = {}
    for i, s in enumerate(seq):
        if s is None or not s.assigned_note_mask:
            continue
        notes = [n for k, n in enumerate(s.notes) if s.assigned_note_mask >> k & 1 and n.note_number > 0]
        if not notes:
            continue
        delay = min(n.delay for n in notes)
        pos = (i * 24 + delay * 4) * scale16
        ev, nud = place(evs, pos, nsteps)
        if not ev.notes:
            ev.nudge = nud
        elif nud != ev.nudge:            # (a late note of the step before meets this step's: one nudge a step, the
            stats["timing_merged"] += 1   # notes on the grid keep theirs)
            if nud == 0:
                ev.nudge = 0
        kept = keep4(notes, root)
        stats["notes_dropped"] += len(set(max(1, min(127, n.note_number - 12 + root)) for n in notes)) - len(kept)
        for m in kept:
            if m in ev.notes:
                continue
            if len(ev.notes) < SN:
                ev.notes.append(m)
            else:
                stats["notes_dropped"] += 1
        ev.vel = max(ev.vel, max(n.velocity for n in notes))
        gate = max(n.gate & 0x7F for n in notes) + (6 if any(n.gate & 0x80 for n in notes) else 0)
        ev.len = max(ev.len, len_code(gate * 4.0 / 6.0 * scale16))
        ev.cond = prob_cond(s.probability)
    return evs


def drum_events(seq, scale16, key_of, stats, nsteps):
    evs = {}
    # the hits on the grid first, then the late ones around them (a late hit never takes a step's own hit's place)
    order = sorted((i for i, s in enumerate(seq) if s is not None and s.active),
                   key=lambda i: ((seq[i].micro_hits & 0x3F or 1) & 1 == 0, i))
    for i in order:
        s = seq[i]
        mask = s.micro_hits & 0x3F or 1
        bits = [b for b in range(6) if mask >> b & 1]
        pos = int(round((i * 24 + bits[0] * 4) * scale16))
        ev, nud = place(evs, pos, nsteps)
        if ev.key:                       # the next step has its own hit: this late one as late as its own step allows
            st0 = int(math.floor(pos / 24.0)) % nsteps
            alt = evs.get(st0)
            if alt is None or not alt.key:
                ev = evs.setdefault(st0, Ev())
                nud = min(12, pos - int(math.floor(pos / 24.0)) * 24)
                stats["hits_early"] += 1
            else:
                stats["hits_merged"] += 1
                continue
        key = key_of(s.drum_choice)
        if not key:
            stats["hits_silent"] += 1
            if not ev.notes and not ev.key:
                evs.pop(next(k for k, v in evs.items() if v is ev))
            continue
        ev.key = key
        ev.vel = max(1, s.velocity)
        ev.nudge = nud
        ev.cond = prob_cond(s.probability)
        if len(bits) > 1:
            ev.comp, ev.cval = SC_MULTIPLY, min(8, len(bits) - 1)
            if len(bits) not in (2, 3, 6) or bits[0]:
                stats["rolls_approx"] += 1
    return evs


# ------------------------------------------------------------------------------------------------- the layout ---

class Layout:
    """MiniTraxFM's patterns, scenes and song for one project, built from the Circuit's scenes and chains"""

    def __init__(self, rep):
        self.rep = rep
        self.pats = [[] for _ in range(8)]          # per track: (len, scale, evs) in slot order
        self.keys = [{} for _ in range(8)]          # per track: pattern content hash -> slot
        self.scenes = []                            # tuples of 8 slots (0-based)
        self.song = []                              # (scene index, bars)
        self.full = set()

    def pattern(self, t, length, scale, evs):
        h = (length, scale, tuple(sorted((k, tuple(e.notes), e.vel, e.len, e.nudge, e.cond, e.key, e.comp, e.cval)
                                         for k, e in evs.items())))
        if h in self.keys[t]:
            return self.keys[t][h]
        if len(self.pats[t]) >= NPATT:
            if t not in self.full:
                self.rep(f"  ! {TRACK_NAMES[t]}: more than {NPATT} different patterns; the rest replay pattern 8")
                self.full.add(t)
            return NPATT - 1
        self.pats[t].append((length, scale, evs))
        self.keys[t][h] = len(self.pats[t]) - 1
        return self.keys[t][h]

    def scene(self, slots, bars):
        slots = tuple(slots)
        if slots in self.scenes:
            i = self.scenes.index(slots)
        elif len(self.scenes) < NSCENE:
            self.scenes.append(slots)
            i = len(self.scenes) - 1
        else:
            self.rep(f"  ! more than {NSCENE} scenes: the song stops early")
            return False
        if len(self.song) >= NSONG:
            self.rep(f"  ! the song is longer than {NSONG} parts: cut there")
            return False
        self.song.append((i, max(1, min(64, bars))))
        return True


def build_layout(pr, key_maps, rep, stats):
    ncs = pr.ncs
    root = ncs.project_settings.scale_root % 12
    warned = set()

    def warn(s):
        if s not in warned:
            warned.add(s)
            rep(f"  ~ {s}")

    parts = song_part_chains(ncs)
    lay = Layout(rep)
    for chains in parts:
        seqs = [chain_sequence(ncs, t, a, b, warn) for t, (a, b) in enumerate(chains)]
        dur16 = [len(s) * SYNC_16THS[r] for s, r in seqs]
        span = max(dur16) if dur16 else 16
        fits = all(len(s) <= NSTEP for s, _ in seqs)
        if fits:
            slots = []
            for t, (s, r) in enumerate(seqs):
                if r in (0, 2, 4, 6):
                    warn(f"{TRACK_NAMES[t]}: triplet rate {SYNC_NAME[r]} played straight")
                evs = events_for(t, s, 1.0, root, key_maps, stats, len(s))
                slots.append(lay.pattern(t, max(1, len(s)), SYNC_SCALE[r], evs))
            if not lay.scene(slots, int(math.ceil(span / 16.0))):
                break
        else:
            # longer than 64 steps: everything on a sixteenth grid in 4-bar blocks, each track looping its own run
            blocks = int(math.ceil(span / 64.0))
            for t, (s, r) in enumerate(seqs):
                if r not in (1, 3, 5, 7):
                    warn(f"{TRACK_NAMES[t]}: rate {SYNC_NAME[r]} in a long chain set on sixteenths")
            ok = True
            for bk in range(blocks):
                n16 = int(min(64, math.ceil(span - bk * 64)))
                slots = []
                for t, (s, r) in enumerate(seqs):
                    k16 = SYNC_16THS[r]
                    run = len(s) * k16
                    if not s or run <= 0:
                        slots.append(lay.pattern(t, n16, TS_1, {}))
                        continue
                    # the steps of this track that start within the block (the run looping from the scene's start)
                    m0 = int(math.ceil(bk * 64 / k16 - 1e-9))
                    m1 = int(math.ceil((bk * 64 + n16) / k16 - 1e-9))
                    sub = [s[m % len(s)] for m in range(m0, m1)]
                    evs = events_for(t, sub, k16, root, key_maps, stats, n16)
                    slots.append(lay.pattern(t, n16, TS_1, evs))
                if not lay.scene(slots, int(math.ceil(n16 / 16.0))):
                    ok = False
                    break
            if not ok:
                break
    return lay


def events_for(t, seq, scale16, root, key_maps, stats, nsteps):
    if t < 4:
        return synth_events(seq, scale16, root, stats, max(1, nsteps))
    km = key_maps[t - 4]
    return drum_events(seq, scale16, lambda c: km.get(c, 0), stats, max(1, nsteps))


# ---------------------------------------------------------------------------------------------------- samples ---

def trim(frames, rate):
    """the tail under -60 dB off, and a 5 ms fade at the cut"""
    thr = 0.001 * max(1e-9, max((abs(v) for v in frames), default=0))
    end = len(frames)
    while end > 1 and abs(frames[end - 1]) < thr:
        end -= 1
    out = frames[:end]
    f = min(len(out), int(0.005 * rate))
    for i in range(f):
        out[len(out) - f + i] *= 1.0 - (i + 1) / float(f)
    return out


def song_part_chains(ncs):
    """the Circuit's parts in playing order (each scene of the scene chain, or the pattern chains alone): 8 chains each"""
    stored = [i for i, s in enumerate(ncs.scenes) if s.header and s.header[0]]
    if stored:
        a, b = ncs.scene_chain.start, ncs.scene_chain.end
        if b < a:
            a, b = b, a
        order = [i for i in range(a, b + 1) if i in stored] or stored[:1]
        return [[(ncs.scenes[i].track_chains[t].start, ncs.scenes[i].track_chains[t].end) for t in range(8)]
                for i in order]
    return [[(c.start, c.end) for c in ncs.pattern_chains]]


def audible_seconds(projects):
    """sample slot -> the longest it is ever heard: a drum track plays one hit at a time (the next cuts it), so a hit
    lasts at most until the track's next hit. Over each project's song (twice round, so the wrap counts too); a sample
    whose track plays nothing after it (a single hit in a song that stops) gets None: all of it"""
    longest = {}
    for pr in projects:
        ncs = pr.ncs
        ms16 = 60000.0 / max(40, min(240, ncs.timing.tempo)) / 4.0
        parts = song_part_chains(ncs)
        for d in range(4):
            t = 4 + d
            default = pr.default_drums[d]
            hits = []                    # (ms, slot)
            at16 = 0.0
            for rnd in range(2):
                for chains in parts:
                    seqs = [chain_sequence(ncs, k, a, b, lambda x: None) for k, (a, b) in enumerate(chains)]
                    span = max(len(sq) * SYNC_16THS[r] for sq, r in seqs) or 16
                    part16 = math.ceil(span / 16.0) * 16 if len(parts) > 1 else span
                    seq, rate = seqs[t]
                    k16 = SYNC_16THS[rate]
                    m = 0
                    while seq and m * k16 < part16:
                        st = seq[m % len(seq)]
                        if st.active:
                            mask = st.micro_hits & 0x3F or 1
                            bits = [x for x in range(6) if mask >> x & 1]
                            slot = default if st.drum_choice == 0xFF else st.drum_choice
                            for b in bits:       # (a roll's every hit cuts the one before)
                                hits.append(((at16 + (m + b / 6.0) * k16) * ms16, slot))
                        m += 1
                    at16 += part16
            hits.sort()
            for i, (ms, slot) in enumerate(hits[:len(hits) // 2 + 1] if hits else []):
                nxt = hits[i + 1][0] if i + 1 < len(hits) else None
                gap = None if nxt is None else (nxt - ms) / 1000.0
                if slot in longest and longest[slot] is None:
                    continue
                longest[slot] = None if gap is None else max(longest.get(slot) or 0.0, gap)
    return longest


def used_samples(projects):
    """sample slot -> hits, over the projects (default sample of a drum track counts its own hits)"""
    use = {}
    for pr in projects:
        for d in range(4):
            default = pr.default_drums[d]
            for pat in circuit_track_patterns(pr.ncs, 4 + d):
                for s in pat.steps:
                    if s.active:
                        slot = default if s.drum_choice == 0xFF else s.drum_choice
                        use[slot] = use.get(slot, 0) + 1
            use.setdefault(default, 0)
    return use


BANK_MARGIN = 6 * 1024                   # the bank's layout (a sample's checkpoints in one window) costs a little more
#                                          than sample_bytes adds up: room kept for it


def plan_bank(pack, projects, max_len, alt, rep, fill=False, budget_cut=0):
    """which samples go in the bank: [(name, frames at RATE, source)], slot -> bank index (None: silent)"""
    use = used_samples(projects)
    heard = audible_seconds(projects)
    entries, slot_to = [], {}
    pool_index = {}
    budget = sio.BANK_MAX_DATA - BANK_MARGIN - budget_cut
    used_bytes = 0
    rep("Samples")
    cands, longs = [], []
    cut_notes = {}
    for slot, hits in sorted(use.items(), key=lambda kv: -kv[1]):
        s = pack.sample(slot)
        name = (pack.sample_names[slot] if slot < len(pack.sample_names) else "") or f"slot {slot + 1}"
        if s is None:
            cands.append((slot, hits, name, None, "an empty slot in the pack: silent on the Circuit too"))
            continue
        frames = trim(list(s.frames), s.rate)
        full = len(frames) / float(s.rate)
        h = heard.get(slot)
        if h is not None and h + 0.03 < full:    # never heard past the track's next hit: cut there (and a 20 ms fade)
            frames = frames[:int((h + 0.02) * s.rate)]
            fade = int(0.02 * s.rate)
            for i in range(min(fade, len(frames))):
                frames[len(frames) - 1 - i] *= i / float(fade)
            cut_notes[slot] = (full, h)
        secs = len(frames) / float(s.rate)
        if secs > max_len:
            if fill:                     # (--fill: a second pass, once the short ones are in)
                longs.append((slot, hits, name, frames, s.rate, secs))
            else:
                cands.append((slot, hits, name, None, f"{secs:.1f} s, longer than {max_len:g} s"))
            continue
        cands.append((slot, hits, name, sio.resample(frames, s.rate, RATE), ""))
    for slot, hits, name, frames, rate, secs in longs:
        cands.append((slot, hits, name, sio.resample(frames, rate, RATE), f"{secs:.1f} s"))

    def add_alt(slot, name, why):
        nonlocal used_bytes
        cat = pool.category(name) if alt else None
        if not cat:
            slot_to[slot] = None
            rep(f"  - {name}: left out ({why})" + ("" if "empty slot" in why else "; its hits are silent"))
            return
        if cat not in pool_index:
            frames = pool.make(cat)
            nb = sio.sample_bytes(len(frames))
            if used_bytes + nb > budget or len(entries) >= sio.BANK_N:
                slot_to[slot] = None
                rep(f"  - {name}: left out ({why}); no room for an alternate either")
                return
            entries.append((f"alt {cat}"[:11], frames, "pool"))
            used_bytes += nb
            pool_index[cat] = len(entries) - 1
        slot_to[slot] = pool_index[cat]
        rep(f"  ~ {name}: {why}; the pool's {cat} plays instead")

    for slot, hits, name, frames, why in cands:
        if frames is None:
            add_alt(slot, name, why)
            continue
        nb = sio.sample_bytes(len(frames))
        if used_bytes + nb > budget or len(entries) >= sio.BANK_N:
            add_alt(slot, name, (why + ", " if why else "") + "no room left in the bank")
            continue
        entries.append((name[:11].lower(), frames, f"slot {slot + 1}"))
        used_bytes += nb
        slot_to[slot] = len(entries) - 1
        cut = cut_notes.get(slot)
        rep(f"  + {name}: {len(frames) / RATE:.2f} s, {hits} hit{'s' if hits != 1 else ''}"
            + (f" (of {cut[0]:.1f} s: never heard past {cut[1]:.2f} s, the track's next hit cuts it)" if cut else "")
            + (" (long: kept by --fill)" if why else ""))
    rep(f"  bank: {len(entries)} samples, {used_bytes / 1024:.1f} of {budget / 1024:.1f} KB "
        f"({used_bytes * 100 // budget} %)")
    rep()
    return entries, slot_to


def write_bank(entries, workdir):
    """the bank's image (tools/loom_samples.py's build, every sample at 22050 Hz, no factory set) and each sample's
    peak (the build normalises them: the kit's key volume puts their level back)"""
    specs, peaks = [], []
    for i, (name, frames, _) in enumerate(entries):
        peak = max(1e-6, max(abs(v) for v in frames))
        peaks.append(peak)
        path = os.path.join(workdir, f"s{i:02d}.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(v / peak * 30000)))) for v in frames))
        safe = "".join(c if c.isalnum() or c in " -" else " " for c in name).strip() or f"s{i}"
        specs.append(f"{safe}={path}%{RATE}")
    if not specs:
        return ls.empty_bank(), peaks
    return ls.build(specs, rate=RATE, quiet=True, factory=False), peaks


# ---------------------------------------------------------------------------------------------------- sounds ---

def db_volume(gain):
    """a gain as a kit key's volume (-30..+20 dB over 0..127, 76 = 0 dB)"""
    db = 20 * math.log10(max(gain, 1e-4))
    return max(0, min(127, int(round(76 + db * 127.0 / 50.0))))


def sound_lines(pr, slot_to, peaks, key_maps, rep):
    """the project's sounds and mix as host commands; fills key_maps (per drum track: sample choice -> key)"""
    out = []
    ncs = pr.ncs
    fx = ncs.fx
    # synth 1 / 2: the project's own patches
    for s in range(2):
        v, notes = knitmap.to_knit(pr.patches[s])
        name = knitmap.patch_name(pr.patches[s])
        rep(f"  {TRACK_NAMES[s]}: {name}" + (f" (approximated: {'; '.join(notes)})" if notes else ""))
        for p, val in v.items():
            out.append(f"param {s + 1} {p} {val}")
        out.append(f"mtname {s + 1} {name.lower().replace(' ', '_')[:11]}")
    # midi 1 / 2: a plain knit sound, darker and mono for a low part
    for m in range(2):
        t = 2 + m
        notes = [n.note_number for pat in circuit_track_patterns(ncs, t) for st in pat.steps
                 if st.assigned_note_mask for k, n in enumerate(st.notes) if st.assigned_note_mask >> k & 1]
        if not notes:
            continue
        low = sum(notes) / len(notes) - 12 < 52
        rep(f"  {TRACK_NAMES[t]}: played another instrument on the Circuit; here a plain knit "
            f"{'bass' if low else 'poly'}")
        out += [f"param {t + 1} {TP.VMODE} {VM.MONO if low else VM.POLY}", f"param {t + 1} {TP.CUT} {70 if low else 96}",
                f"param {t + 1} {TP.E3} 1"]
        out.append(f"mtname {t + 1} {'bass' if low else 'poly'}")
    # mix: synth / midi levels and pans; sends (the Circuit's order S1 S2 D1 D2 D3 D4 M1 M2)
    send_ix = {0: 0, 1: 1, 2: 6, 3: 7}
    for t in range(4):
        lv = fx.mixer_levels[t] if t < len(fx.mixer_levels) else 100
        pn = fx.mixer_pans[t] if t < len(fx.mixer_pans) else 64
        out += [f"param {t + 1} {TP.LEVEL} {max(0, min(127, lv))}", f"param {t + 1} {TP.PAN} {max(0, min(127, pn))}",
                f"param {t + 1} {TP.SEND1} {fx.delay_sends[send_ix[t]] if not fx.fx_bypass else 0}",
                f"param {t + 1} {TP.SEND2} {fx.reverb_sends[send_ix[t]] if not fx.fx_bypass else 0}"]
    # drum 1-4: key 1 the track's sample, keys 2.. the flips its steps pick
    for d in range(4):
        t = 4 + d
        cfg = ncs.drum_configs[d]
        default = pr.default_drums[d]
        counts = {}
        for pat in circuit_track_patterns(ncs, t):
            for s in pat.steps:
                if s.active and s.drum_choice != 0xFF:
                    counts[s.drum_choice] = counts.get(s.drum_choice, 0) + 1
        order = [default] + [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if c != default]
        km = {}
        keys = []
        for slot in order:
            b = slot_to.get(slot)
            if b is None:
                continue
            if b in keys:                      # (two slots on one bank sample: an alternate shared)
                km[slot] = keys.index(b) + 1
                continue
            if len(keys) >= NDRUM:
                rep(f"  ! {TRACK_NAMES[t]}: more than {NDRUM} samples; the rest play key 1")
                km[slot] = 1
                continue
            keys.append(b)
            km[slot] = len(keys)
        km[0xFF] = km.get(default, 0)           # (a sample left out of the bank: its hits silent, as reported)
        key_maps[d] = km
        lv = cfg.level / 100.0
        for k, b in enumerate(keys):
            vol = db_volume(lv * peaks[b])
            out += [f"param {t + 1} {tp_drum(k, DP.MODEL)} {DM_SAMPLE}",
                    f"param {t + 1} {tp_drum(k, DP.K1)} {NSMP_FACT_HOST + b}",
                    f"param {t + 1} {tp_drum(k, DP.K2)} {max(0, min(127, cfg.pitch))}",
                    f"param {t + 1} {tp_drum(k, DP.VOLUME)} {vol}",
                    f"param {t + 1} {tp_drum(k, DP.PAN)} {max(0, min(127, cfg.pan))}",
                    f"param {t + 1} {tp_drum(k, DP.DECAY)} {max(1, min(127, cfg.decay))}",
                    f"param {t + 1} {tp_drum(k, DP.MODE)} {PM_CHOKE1}",
                    f"param {t + 1} {tp_drum(k, DP.SEND1)} {fx.delay_sends[2 + d] if not fx.fx_bypass else 0}",
                    f"param {t + 1} {tp_drum(k, DP.SEND2)} {fx.reverb_sends[2 + d] if not fx.fx_bypass else 0}"]
        if keys:
            nm = (pr_sample_name(d, default, slot_to) or TRACK_NAMES[t]).replace(" ", "_")[:11]
            out.append(f"mtname {t + 1} {nm}")
    return out


_names = {}


def pr_sample_name(d, slot, slot_to):
    return _names.get(slot)


# ------------------------------------------------------------------------------------------------------ main ---

def project_script(pr, slot, slot_to, peaks, rep, stats):
    ncs = pr.ncs
    key_maps = [{}, {}, {}, {}]
    rep(f"Project {slot + 1}: \"{pr.name}\" (pack slot {pr.slot + 1}), {ncs.timing.tempo} BPM")
    lines = ["mtclear", f"bpm {max(40, min(240, ncs.timing.tempo))}", "mtgroove 0"]
    lines += sound_lines(pr, slot_to, peaks, key_maps, rep)
    lay = build_layout(pr, key_maps, rep, stats)
    swing = max(-99, min(99, int(round((ncs.timing.swing - 50) * 3.3))))
    for t in range(8):
        for i, (length, scale, evs) in enumerate(lay.pats[t]):
            lines.append(f"mtpat {t + 1} {i + 1} {length} {scale} 50 {swing}")
            for st in sorted(evs):
                e = evs[st]
                if t < 4:
                    if not e.notes:
                        continue
                    lines.append(f"mtstep {t + 1} {i + 1} {st + 1} {e.len or 2} {e.vel or 100} {e.nudge} "
                                 + " ".join(str(n) for n in e.notes))
                else:
                    lines.append(f"mtkit {t + 1} {i + 1} {st + 1} {e.key} {e.vel} {e.nudge} {e.comp} {e.cval}")
                if e.cond:
                    lines.append(f"mtcond {t + 1} {i + 1} {st + 1} {e.cond}")
    for i, sc in enumerate(lay.scenes):
        lines.append(f"mtscene {i + 1} " + " ".join(str(p + 1) for p in sc))
    if len(lay.song) > 1:
        lines.append(f"mtsong {len(lay.song)} 1")
        for i, (sc, bars) in enumerate(lay.song):
            lines.append(f"mtslot {i + 1} {sc + 1} {bars}")
    lines.append("mtstart 1")
    rep(f"  {sum(len(p) for p in lay.pats)} patterns, {len(lay.scenes)} scene{'s' if len(lay.scenes) != 1 else ''}"
        + (f", a song of {len(lay.song)} parts ({sum(b for _, b in lay.song)} bars)" if len(lay.song) > 1 else ""))
    rep()
    return lines


def backup_with_samples(backup_path, bank, out_path):
    """the host's backup file with the bank appended as the "LSMP" section (fm1_backup.py's sections)"""
    data = open(backup_path, "rb").read()
    sec = b"LSMP" + struct.pack("<I", len(bank)) + bank + struct.pack("<I", zlib.crc32(bank) & 0xFFFFFFFF)
    open(out_path, "wb").write(data + sec)


def choose_projects(projects, spec, rep=lambda s="": None):
    """the projects to convert: pack slots spec ("1,4,9", from 1) or the first NPROJ with notes"""
    if spec:
        want = [int(x) - 1 for x in spec.split(",") if x.strip()]
        chosen = [p for w in want for p in projects if p.slot == w]
        missing = [w + 1 for w in want if w not in [p.slot for p in projects]]
        if missing:
            sys.exit(f"ct2mtx: no project in pack slot {', '.join(map(str, missing))}")
    else:
        chosen = [p for p in projects if p.has_content()]
    if len(chosen) > NPROJ:
        rep(f"The pack has {len(chosen)} projects with notes; MiniTraxFM holds {NPROJ}: "
            f"{', '.join(str(p.slot + 1) for p in chosen[:NPROJ])} converted (--projects picks others)")
        rep()
        chosen = chosen[:NPROJ]
    if not chosen:
        sys.exit("ct2mtx: no project with notes in this pack")
    return chosen


def main(argv=None):
    ap = argparse.ArgumentParser(description="A Circuit Tracks pack for MiniTraxFM (FM-1)")
    ap.add_argument("pack")
    ap.add_argument("-o", "--out", help="OUT.mtx (default: the pack's name beside it)")
    ap.add_argument("--projects", help="pack project slots to convert, from 1 (up to 3), e.g. 1,4,9")
    ap.add_argument("--max-len", type=float, default=1.5, help="longest sample kept, seconds (default 1.5)")
    ap.add_argument("--no-alt", action="store_true", help="no alternates from the pool for samples left out")
    ap.add_argument("--fill", action="store_true",
                    help="then keep samples longer than --max-len too while the bank has room (most played first)")
    ap.add_argument("--wav", action="store_true", help="also render each project (8 bars) to OUT-N.wav")
    ap.add_argument("--keep", action="store_true", help="keep the host scripts beside the output")
    ap.add_argument("--sure", action="store_true", help=argparse.SUPPRESS)   # every step at 100 % (verify.py's)
    a = ap.parse_args(argv)
    global SURE
    SURE = a.sure
    if not os.path.exists(HOST):
        sys.exit(f"ct2mtx: no host simulator at {HOST} (./build.sh --host first)")
    pack = ctpack.Pack(a.pack)
    out = a.out or os.path.splitext(a.pack)[0] + ".mtx"
    rep = Report()
    rep(f"ct2mtx: {os.path.basename(a.pack)} (\"{pack.name}\") for MiniTraxFM")
    rep()
    projects, errors = pack.projects()
    for slot, e in errors:
        rep(f"! project {slot + 1} could not be read: {e}")
    chosen = choose_projects(projects, a.projects, rep)
    cut = 0
    while True:                          # (the bank's exact layout decides: past it, a little less room and again)
        trial = Report()
        entries, slot_to = plan_bank(pack, chosen, a.max_len, not a.no_alt, trial, a.fill, cut)
        try:
            with tempfile.TemporaryDirectory() as wd:
                write_bank(entries, wd)
            break
        except ValueError:
            cut += 4 * 1024
            if cut > 64 * 1024:
                raise
    rep.lines += trial.lines
    for slot, b in slot_to.items():
        if b is not None:
            _names[slot] = entries[b][0]
    stats = {"notes_dropped": 0, "timing_merged": 0, "hits_merged": 0, "hits_early": 0, "hits_silent": 0, "rolls_approx": 0}
    with tempfile.TemporaryDirectory() as wd:
        bank, peaks = write_bank(entries, wd)
        bank_path = os.path.join(wd, "bank.bin")
        open(bank_path, "wb").write(bank)
        script = [f"samples {bank_path}"]
        for i, pr in enumerate(chosen):
            script += project_script(pr, i, slot_to, peaks, rep, stats)
            if a.wav:
                script += ["master 4096", "tap PLAY", "wait 300", f"wav {os.path.splitext(os.path.basename(out))[0]}-{i + 1}.wav",
                           f"wait {int(8 * 4 * 60000 / max(40, pr.ncs.timing.tempo))}", "wavstop", "tap PLAY",
                           "wait 200"]
            script.append(f"projsave {i + 1} {pr.name.replace(' ', '_')[:11]}")
        script.append("backup out:minitrax.bak")
        xy = os.path.join(wd, "convert.xy")
        open(xy, "w").write("\n".join(script) + "\n")
        outdir = os.path.join(wd, "out")
        os.makedirs(outdir)
        r = subprocess.run([HOST, xy, outdir], capture_output=True, text=True,
                           cwd=os.path.join(REPO, "app"))
        if r.returncode != 0 or not os.path.exists(os.path.join(outdir, "minitrax.bak")):
            sys.stderr.write(r.stdout[-3000:] + r.stderr[-2000:])
            sys.exit("ct2mtx: the host simulator did not write the projects")
        backup_with_samples(os.path.join(outdir, "minitrax.bak"), bank, out)
        for line in r.stdout.splitlines():
            if line.startswith("projsave:"):
                rep(f"  {line}")
        if a.wav:
            for f in os.listdir(outdir):
                if f.endswith(".wav"):
                    os.replace(os.path.join(outdir, f), os.path.join(os.path.dirname(os.path.abspath(out)), f))
        if a.keep:
            os.replace(xy, os.path.splitext(out)[0] + ".xy")
    rep()
    rep("Approximations: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in stats.items() if v) if any(
        stats.values()) else "Approximations: none counted")
    open(os.path.splitext(out)[0] + ".txt", "w").write(rep.text())
    print(rep.text(), end="")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
