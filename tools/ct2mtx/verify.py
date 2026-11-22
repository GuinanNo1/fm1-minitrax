#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Check a conversion by ear's stand-in: the notes MiniTraxFM plays against the notes the Circuit project holds.

    verify.py PACK.circuittrackspack [--projects 1,2,3] [--bars 8] [--tol 12]

Converts the pack (ct2mtx, its host script kept), plays each converted project's first scene in the host simulator for
--bars bars, and reads the notes every track sends out over MIDI (each track on its own channel). The Circuit's side:
the same project's first scene (or its pattern chains) laid out on the same clock, straight from the .ncs. Per track:
the notes expected, played, matched (same time within --tol ms, the same pitch on a synth track), missing and extra.
The conversion is made with every step at 100 % (--sure) so chance steps are compared too.
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ct2mtx as C  # noqa: E402
import ctpack  # noqa: E402


def song_parts(ncs):
    """the Circuit's parts in playing order: each scene of the scene chain (or the pattern chains alone)"""
    stored = [i for i, s in enumerate(ncs.scenes) if s.header and s.header[0]]
    if stored:
        a, b = ncs.scene_chain.start, ncs.scene_chain.end
        order = [i for i in range(min(a, b), max(a, b) + 1) if i in stored] or stored[:1]
        return [[(ncs.scenes[i].track_chains[t].start, ncs.scenes[i].track_chains[t].end) for t in range(8)]
                for i in order]
    return [[(c.start, c.end) for c in ncs.pattern_chains]]


def expected(pr, bars, whole_song=False):
    """[(track, ms, note or None)] the Circuit project plays in `bars` bars: its first part looping, or (whole_song)
    its parts in turn, each for its longest chain rounded up to whole bars (as ct2mtx lays the song out), the song
    looping; and the count of chance steps"""
    ncs = pr.ncs
    tempo = max(40, min(240, ncs.timing.tempo))
    ms16 = 60000.0 / tempo / 4.0
    root = ncs.project_settings.scale_root % 12
    parts = song_parts(ncs)
    if not whole_song:
        parts = parts[:1]
    total16 = bars * 16
    out, chance = [], 0
    at16, k = 0.0, 0
    while at16 < total16:
        chains = parts[k % len(parts)]
        seqs = [C.chain_sequence(ncs, t, a, b, lambda s: None) for t, (a, b) in enumerate(chains)]
        span = max(len(sq) * C.SYNC_16THS[r] for sq, r in seqs) or 16
        part16 = math.ceil(span / 16.0) * 16 if len(parts) > 1 else total16
        for t, (seq, rate) in enumerate(seqs):
            if not seq:
                continue
            k16 = C.SYNC_16THS[rate]
            m = 0
            while m * k16 < part16 and at16 + m * k16 < total16:
                s = seq[m % len(seq)]
                base = at16 + m * k16
                m += 1
                if t < 4:
                    if not s.assigned_note_mask:
                        continue
                    if s.probability < 7:
                        chance += 1
                    notes = [n for j, n in enumerate(s.notes) if s.assigned_note_mask >> j & 1 and n.note_number > 0]
                    if not notes:
                        continue
                    d = min(n.delay for n in notes)
                    ms = (base + d / 6.0 * k16) * ms16
                    midi = sorted(set(max(1, min(127, n.note_number - 12 + root)) for n in notes))
                    for nn in midi[:4]:
                        out.append((t, ms, nn))
                else:
                    if not s.active:
                        continue
                    if s.probability < 7:
                        chance += 1
                    mask = s.micro_hits & 0x3F or 1
                    bits = [x for x in range(6) if mask >> x & 1]
                    out.append((t, (base + bits[0] / 6.0 * k16) * ms16, None))
                    for _ in bits[1:]:
                        out.append((t, None, None))      # a roll's further hits: counted, not timed
        at16 += part16
        k += 1
    return out, chance


def played(log_path, t0):
    """[(track, ms, note)] note-ons in the host's MIDI log (channels 1-8 = tracks 1-8), from t0 on"""
    out = []
    for line in open(log_path):
        try:
            ms_s, rest = line.split(" ms: ")
            b = rest.split()
            st, note, vel = int(b[0], 16), int(b[1], 16), int(b[2], 16)
        except (ValueError, IndexError):
            continue
        if st & 0xF0 == 0x90 and vel > 0 and (st & 0x0F) < 8 and int(ms_s) >= t0:
            out.append((st & 0x0F, int(ms_s) - t0, note))
    return out


def compare(exp, got, tol, span_ms):
    rows = []
    for t in range(8):
        e = [x for x in exp if x[0] == t]
        g = [x for x in got if x[0] == t and x[1] < span_ms - tol]
        e_timed = [x for x in e if x[1] is not None and x[1] < span_ms - tol]
        e_rolls = len([x for x in e if x[1] is None])
        used = [False] * len(g)
        hit = 0
        for _, ms, nn in e_timed:
            for i, (_, gms, gnn) in enumerate(g):
                if not used[i] and abs(gms - ms) <= tol and (nn is None or nn == gnn):
                    used[i] = True
                    hit += 1
                    break
        extra = used.count(False)
        rows.append((t, len(e_timed) + e_rolls, len(g), hit, len(e_timed) - hit, extra, e_rolls))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pack")
    ap.add_argument("--projects")
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--tol", type=float, default=12.0)
    ap.add_argument("--song", action="store_true", help="the whole scene chain, not the first scene alone")
    a = ap.parse_args(argv)
    pack = ctpack.Pack(a.pack)
    projects, _ = pack.projects()
    with tempfile.TemporaryDirectory() as wd:
        out = os.path.join(wd, "v.mtx")
        args = [a.pack, "-o", out, "--keep", "--sure"] + (["--projects", a.projects] if a.projects else [])
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            C.main(args)
        script = open(os.path.splitext(out)[0] + ".xy").read().splitlines()
        # the projects' parts of the script: from each mtclear to its projsave
        parts, cur = [], None
        for line in script:
            if line.startswith("samples "):
                bank_line = line
            if line == "mtclear":
                cur = [line]
            elif line.startswith("projsave") and cur is not None:
                parts.append(cur)
                cur = None
            elif cur is not None:
                cur.append(line)
        names = [ln.split(" ", 2)[2] for ln in script if ln.startswith("projsave")]
        chosen = [p for n in names for p in projects if p.name.replace(" ", "_")[:11] == n][:len(parts)]
        bad = 0
        for i, (pr, part) in enumerate(zip(chosen, parts)):
            tempo = max(40, min(240, pr.ncs.timing.tempo))
            span = a.bars * 4 * 60000.0 / tempo
            xy = os.path.join(wd, f"p{i}.xy")
            od = os.path.join(wd, f"o{i}")
            os.makedirs(od)
            # the bank file is gone with ct2mtx's own temporary folder: drums play nothing, but their notes still go out
            body = [ln for ln in part if not ln.startswith("samples")]
            open(xy, "w").write("\n".join(body + ["tap PLAY", f"wait {int(span + 400)}", "tap PLAY"]) +
                                "\n")
            r = subprocess.run([C.HOST, xy, od], capture_output=True, text=True, cwd=os.path.join(C.REPO, "app"))
            log = os.path.join(od, "midi_out.txt")
            if not os.path.exists(log):
                print(r.stdout[-2000:])
                sys.exit("verify: no MIDI log")
            got_all = played(log, 0)
            t0 = min((ms for _, ms, _ in got_all), default=0)
            got = [(t, ms - t0, n) for t, ms, n in got_all]
            exp, chance = expected(pr, a.bars, a.song)
            rows = compare(exp, got, a.tol, span)
            print(f"{pr.name}: {'the song' if a.song else 'first scene'}, {a.bars} bars at {tempo} BPM ({chance} chance steps played as sure)")
            print("  track     expected played matched missing extra")
            for t, ne, ng, hit, miss, extra, rolls in rows:
                if ne or ng:
                    flag = "" if not miss and not extra else "  <"
                    print(f"  {C.TRACK_NAMES[t]:8s} {ne:8d} {ng:6d} {hit:7d} {miss:7d} {extra:5d}"
                          + (f"  ({rolls} roll hits)" if rolls else "") + flag)
                    bad += miss + max(0, extra - rolls)
        print("verify:", "every note matched" if not bad else f"{bad} notes differ")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
