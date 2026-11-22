# SPDX-License-Identifier: MPL-2.0
"""A Circuit Tracks synth patch (340 bytes, the Programmer's Reference v3 layout) as MiniTraxFM's knit voice.

Knit is a subtractive voice: one wave (saw .. square .. 10 % pulse) in a unison of 1..7, a second oscillator at an
interval with its own level, a sub sine, noise, a filter (lp24, lp12, hp12, bp12) with its own ADSR and envelope amount,
an amp ADSR, one LFO and a character stage (drive). The Circuit's synth has two oscillators of 30 waves, a mixer with
ring modulation, a filter with drive, three envelopes, two LFOs, a 20-slot mod matrix, distortion, chorus, EQ and 8
macros. So the result is the nearest knit sound, not the same one: what knit has no place for is listed (notes).

Parameter numbers: dsp/synth.h's enum (tools/ct2mtx/consts.py checks them against the headers).
"""
from consts import TP, FT, VM, LT, LD, CT

# patch byte offsets (RosettaGM docs/circuit-tracks-file-formats.md, from the Programmer's Reference v3)
NAME, CATEGORY = 0, 16
POLY, PORTA, PREGLIDE, OCTAVE = 32, 33, 34, 35
OSC1, OSC2 = 36, 45                      # + 0 wave, 1 interpolate, 2 PW index, 3 vsync, 4 density, 5 density detune,
#                                          6 semitones, 7 cents, 8 pitch bend
MIX_O1, MIX_O2, MIX_RING, MIX_NOISE = 54, 55, 56, 57
F_ROUTING, F_DRIVE, F_DRIVETYPE, F_TYPE, F_FREQ, F_TRACK, F_RES, F_QNORM, F_ENV2 = range(60, 69)
ENV1, ENV2, ENV3 = 69, 74, 79            # ENV1/2: velocity, A, D, S, R; ENV3: delay, A, D, S, R
LFO1, LFO2 = 84, 92                      # + 0 wave, 1 phase, 2 slew, 3 delay, 4 delay sync, 5 rate, 6 rate sync, 7 flags
DIST_LEVEL, CHORUS_LEVEL = 100, 102
MODM = 124                               # 20 x [src1, src2, depth (64 = 0), dest]

# the Circuit's waves (0..29): which are saws, which square / pulse, which sine-like
SAWS = set(range(2, 12)) | {16, 17, 20}
SQUARES = {12, 13, 15}
SINES = {0, 1, 14}
# mod matrix sources and destinations (Programmer's Reference)
SRC_LFO = {6: 1, 7: 1, 8: 2, 9: 2}       # LFO 1 / 2, unipolar / bipolar
DST_PITCH = {0, 1, 2}
DST_PW = {5, 6}
DST_CUT = 12


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else int(round(v))


def patch_name(p):
    return bytes(p[NAME:NAME + 16]).decode("ascii", "replace").strip() or "patch"


def lfo_speed(rate):
    """the Circuit's free LFO rate 0..127 as knit's LFO speed (8..127 free, 0.1..30 Hz on knit's curve)"""
    return clamp(8 + rate * (119.0 / 127.0), 8, 127)


def to_knit(p):
    """{TP_*: value} for a knit track, and a list of notes on what did not carry over"""
    p = bytes(p)
    notes = []
    o1 = p[OSC1:OSC1 + 9]
    o2 = p[OSC2:OSC2 + 9]
    lv1, lv2 = p[MIX_O1], p[MIX_O2]
    v = {TP.ENGINE: 0}
    # the main oscillator: the louder of the two
    main, other, lmain, lother = (o1, o2, lv1, lv2) if lv1 >= lv2 or lv2 == 0 else (o2, o1, lv2, lv1)
    w = main[0]
    if w in SAWS:
        wave = 0
    elif w in SQUARES:
        wave = clamp(64 + abs(main[2] - 64) * 0.8, 64, 127)    # a pulse narrower than square past the middle
    elif w in SINES:
        wave = 64                                             # (knit has no sine: a square, darker below)
        notes.append("sine / triangle wave as a square, filtered")
    else:
        wave = 0
        notes.append(f"wavetable wave {w} as a saw")
    v[TP.E1] = wave
    dens, ddet = main[4], main[5]
    voices = 1 + clamp(dens / 127.0 * 6.0, 0, 6)
    v[TP.E3] = voices
    v[TP.E2] = clamp(ddet if voices > 1 else 0, 0, 127)
    v[TP.E4] = 64 if voices > 1 else 0                        # (width: a unison spread)
    # the second oscillator at its interval from the first
    semi = (other[6] - 64) - (main[6] - 64)
    cents = (other[7] - 64) - (main[7] - 64)
    while semi > 24:
        semi -= 12
    while semi < -24:
        semi += 12
    v[TP.X1] = clamp(64 + semi, 40, 88)
    v[TP.X2] = clamp(lother * 127.0 / max(lmain, 1) * 0.8, 0, 127) if lother else 0
    v[TP.O2FINE] = clamp(64 + cents, 14, 114)
    v[TP.X3] = 0
    v[TP.X4] = clamp(p[MIX_NOISE], 0, 127)
    if p[MIX_RING] > 8:
        notes.append("ring modulation left out")
    # octave and pitch of the main oscillator: knit's octave knob, the rest of the semitones moves the notes
    oct_ = p[OCTAVE] - 64
    oct_semis = main[6] - 64
    oct_total = oct_ + int(round(oct_semis / 12.0))
    v[TP.OCT] = clamp(2 + oct_total, 0, 4)
    transpose = (oct_semis - 12 * int(round(oct_semis / 12.0)))
    if transpose:
        notes.append(f"oscillator tuned {transpose:+d} semitones: the notes moved instead")
    # voice mode and glide
    v[TP.VMODE] = {0: VM.MONO, 1: VM.LEGATO, 2: VM.POLY}.get(p[POLY], VM.POLY)
    v[TP.PORTA] = clamp(p[PORTA], 0, 127)
    # filter
    ft = p[F_TYPE]
    v[TP.FTYPE] = {0: FT.LP12, 1: FT.LP24, 2: FT.BP12, 3: FT.BP12, 4: FT.HP12, 5: FT.HP12}.get(ft, FT.LP24)
    cut = p[F_FREQ]
    if w in SINES:
        cut = min(cut, 70)
    v[TP.CUT] = clamp(cut, 0, 127)
    v[TP.RES] = clamp(p[F_RES], 0, 127)
    v[TP.FENV] = clamp(p[F_ENV2], 0, 127)
    v[TP.KTRK] = clamp(p[F_TRACK], 0, 127)
    # envelopes: env 1 the amp, env 2 the filter (both 0..127, exponential times on both instruments)
    v[TP.A], v[TP.D], v[TP.S], v[TP.R] = (clamp(x, 0, 127) for x in p[ENV1 + 1:ENV1 + 5])
    v[TP.FA], v[TP.FD], v[TP.FS], v[TP.FR] = (clamp(x, 0, 127) for x in p[ENV2 + 1:ENV2 + 5])
    # drive: the filter's drive or the distortion, as knit's character stage
    drive = max(p[F_DRIVE], p[DIST_LEVEL])
    if drive > 4:
        v[TP.CTYPE], v[TP.CAMT], v[TP.CTONE], v[TP.CMIX] = CT.DRIVE, clamp(drive, 0, 127), 64, 127
    else:
        v[TP.CTYPE] = CT.OFF
    if p[CHORUS_LEVEL] > 8:
        notes.append("chorus left out (a little of the delay send instead)")
    # the strongest LFO route in the mod matrix: knit has one LFO
    best = None
    for k in range(20):
        s1, s2, depth, dst = p[MODM + 4 * k:MODM + 4 * k + 4]
        if s1 in SRC_LFO and depth != 64 and (dst in DST_PITCH or dst in DST_PW or dst == DST_CUT):
            if best is None or abs(depth - 64) > abs(best[2] - 64):
                best = (s1, s2, depth, dst)
    v[TP.LTYPE] = LT.OFF
    if best:
        s1, _, depth, dst = best
        lfo = LFO1 if SRC_LFO[s1] == 1 else LFO2
        shape = {0: 1, 1: 1, 2: 3, 3: 0}.get(p[lfo], 1)      # sine, triangle -> sine; saw; square
        if dst in DST_PITCH:
            v[TP.LTYPE], v[TP.LSPEED] = LT.WOBBLE, lfo_speed(p[lfo + 5])
            v[TP.LAMT] = clamp(64 + (depth - 64) * 0.5, 0, 127)   # vibrato
            v[TP.LDEST], v[TP.LX], v[TP.LX2] = 64, 64, 0
        else:
            v[TP.LTYPE], v[TP.LSPEED] = LT.WAVE, lfo_speed(p[lfo + 5])
            v[TP.LAMT] = clamp(depth, 0, 127)
            v[TP.LDEST] = LD.SYNTH if dst in DST_PW else LD.FILTER
            v[TP.LX] = 0                                     # knit's wave (past square: PWM) / the cutoff
            v[TP.LX2] = shape
        others = sum(1 for k in range(20) if p[MODM + 4 * k + 2] != 64 and p[MODM + 4 * k] != 0) - 1
        if others > 0:
            notes.append(f"{others} more mod matrix route{'s' if others > 1 else ''} left out")
    return v, notes
