#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""What a set of Circuit Tracks .ncs projects hold: tempo, steps on each kind of track, chains, scenes.

    survey.py FILE.ncs ...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vendor import ncs_parser as N  # noqa: E402


def main(paths):
    for f in paths:
        try:
            n = N.parse_ncs(f)
        except Exception as e:  # a damaged or foreign file: say so, go on
            print(f"ERR {os.path.basename(f)}: {e}")
            continue
        sy = sum(1 for p in n.synth_patterns for s in p.steps if s.assigned_note_mask)
        dr = sum(1 for p in n.drum_patterns for s in p.steps if s.active)
        md = sum(1 for p in n.midi_patterns for s in p.steps if s.assigned_note_mask)
        scenes = sum(1 for s in n.scenes if s.header[0])
        chains = [(c.start, c.end) for c in n.pattern_chains]
        print(f"{os.path.basename(f)[:30]:30s} {n.timing.tempo:3d} bpm  synth {sy:4d}  drum {dr:4d}  midi {md:3d}  "
              f"scenes {scenes:2d}  chains {chains}")


if __name__ == "__main__":
    main(sys.argv[1:])
