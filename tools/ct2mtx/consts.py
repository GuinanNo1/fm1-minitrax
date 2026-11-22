# SPDX-License-Identifier: MPL-2.0
"""MiniTraxFM's parameter numbers (app/dsp/synth.h, dsp/drumline.h, seq/pattern.h), as the converter writes them.
check() compiles a tiny program against the headers and fails if any moved (tests run it)."""
import os
import subprocess
import tempfile


class TP:
    ENGINE, E1, E2, E3, E4, VMODE, PORTA, BEND, VOLUME = range(9)
    A, D, S, R, FA, FD, FS, FR = range(9, 17)
    CUT, RES, FENV, KTRK, FTYPE, SEND1, SEND2 = range(17, 24)
    LTYPE, LSPEED, LAMT, LDEST, LX, LX2 = range(24, 30)
    CTYPE, CAMT, CTONE, CMIX = range(30, 34)
    X1, X2, X3, X4, OCT = range(34, 39)
    LEVEL, PAN, BRAIN, CHAN = 48, 49, 50, 51
    DRUM0, O2FINE = 52, 316


class DP:
    N = 20
    MODEL, K1, K2, K3, K4, RANDOM, PAN, VOLUME, MODE, ATTACK, HOLD, DECAY = range(12)
    SEND1, SEND2 = 18, 19


def tp_drum(key, k):                     # key 0..10
    return TP.DRUM0 + key * DP.N + k


class FT:
    LP24, LADDER, LP12, HP12, BP12 = range(5)


class VM:
    POLY, MONO, LEGATO = range(3)


class LT:
    OFF, WAVE, WOBBLE, DRIFT, PUMP = range(5)


class LD:
    SYNTH, ENV, FILTER, AMP = range(4)


class CT:
    OFF, DRIVE = 0, 1


DM_SAMPLE, PM_CHOKE1 = 10, 3
SC_MULTIPLY = 3
TS_HALF, TS_1, TS_2, TS_3, TS_4 = range(5)
NSTEP, NPATT, NSCENE, NSONG, NDRUM, SN = 64, 8, 32, 64, 11, 4
NSMP_FACT_HOST = 16                      # the host simulator's built-in factory rows (user 1 follows them)

_CHECK = {"TP_ENGINE": TP.ENGINE, "TP_E4": TP.E4, "TP_A": TP.A, "TP_FR": TP.FR, "TP_CUT": TP.CUT, "TP_FTYPE": TP.FTYPE,
          "TP_SEND1": TP.SEND1, "TP_SEND2": TP.SEND2, "TP_LTYPE": TP.LTYPE, "TP_LX2": TP.LX2, "TP_CTYPE": TP.CTYPE,
          "TP_CMIX": TP.CMIX, "TP_X1": TP.X1, "TP_OCT": TP.OCT, "TP_LEVEL": TP.LEVEL, "TP_PAN": TP.PAN,
          "TP_BRAIN": TP.BRAIN, "TP_DRUM0": TP.DRUM0, "DP_N": DP.N, "TP_O2FINE": TP.O2FINE, "DP_VOLUME": DP.VOLUME,
          "DP_MODE": DP.MODE, "DP_DECAY": DP.DECAY, "DP_SEND1": DP.SEND1, "DP_SEND2": DP.SEND2, "DM_SAMPLE": DM_SAMPLE,
          "PM_CHOKE1": PM_CHOKE1, "FT_LP12": FT.LP12, "FT_HP12": FT.HP12, "FT_BP12": FT.BP12, "LT_WOBBLE": LT.WOBBLE,
          "LD_FILTER": LD.FILTER, "SC_MULTIPLY": SC_MULTIPLY, "TS_4": TS_4, "NSTEP": NSTEP, "NSCENE": NSCENE,
          "NSONG": NSONG, "SMP_NFACT": NSMP_FACT_HOST}


def check(app_dir):
    """0 when every number here matches the headers (needs a C compiler and the host build's samples.h)"""
    gen = os.path.join(app_dir, "build", "gen")
    lines = ['#include <stdio.h>', '#include "dsp/synth.h"', '#include "dsp/drumline.h"', '#include "seq/pattern.h"',
             '#include "samples.h"', "int main(void){int bad=0;"]
    for k, v in _CHECK.items():
        lines.append(f'if(({k})!={v}){{printf("{k} is %d, consts.py says {v}\\n",(int)({k}));bad=1;}}')
    lines.append("return bad;}")
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, "c.c"), os.path.join(d, "c")
        open(c, "w").write("\n".join(lines))
        subprocess.run(["cc", "-I", app_dir, "-I", gen, "-o", exe, c], check=True)
        return subprocess.run([exe]).returncode
