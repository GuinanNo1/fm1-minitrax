# ct2mtx: Circuit Tracks packs for MiniTraxFM

Converts a Novation Circuit Tracks pack (`.circuittrackspack`, from Novation Components) into a MiniTraxFM backup
(`.mtx`) that you restore on the FM-1 from MiniTraxFM's backup page.

```
./build.sh --host                                   # once: the host simulator writes the projects
python3 tools/ct2mtx/ct2mtx.py MyPack.circuittrackspack
python3 tools/ct2mtx/ct2mtx.py MyPack.circuittrackspack --projects 1,5,9 --max-len 2.0 --wav
```

Output: `MyPack.mtx` (the three project slots and the sample bank), `MyPack.txt` (the report: every sample kept,
replaced or left out, every patch and what was approximated), and with `--wav` a render of each project.

## What goes where

| Circuit Tracks | MiniTraxFM |
| --- | --- |
| Synth 1, Synth 2 | tracks 1-2, knit voices made from the project's own patches (`knitmap.py`) |
| MIDI 1, MIDI 2 | tracks 3-4, a plain knit sound picked by register (they played other instruments on the Circuit) |
| Drum 1-4 | tracks 5-8: sample kits. Key 1 is the track's sample, keys 2-11 the other samples its steps pick (sample flips). One choke group, so a hit cuts the one before |
| samples | only the samples the converted projects play. 22050 Hz, 4-bit ADPCM: 214 KB, about 19 s in all, at most 32 samples. `--max-len` (default 1.5 s) leaves longer ones out |
| a sample left out | replaced by a synthesised alternate of the same kind (kick, snare, clap, hat, open hat, tom, rim, cowbell, shaker, cymbal) guessed from its name (`pool.py`), unless `--no-alt` |
| patterns (32 steps, 6 notes) | MiniTraxFM patterns (64 steps, 4 notes: the loudest four are kept). Gate, micro-step delay, velocity and probability carry over. A drum roll becomes the multiply trick |
| a chain | one pattern when its patterns fit 64 steps; a longer one is laid out in 4-bar blocks |
| scenes and the scene chain | scenes (up to 32) and the song (up to 64 parts). PLAY plays the song from any page; every part starts all tracks from step 1, as a Circuit scene does |
| tempo, swing, mixer levels, pans, reverb and delay sends | tempo, the swing groove, track levels and pans, the FX II (reverb) and FX I (delay) sends |
| 64 projects | the three MiniTraxFM slots: `--projects` picks them, else the first three with notes |

## Checking a conversion

```
python3 tools/ct2mtx/verify.py MyPack.circuittrackspack --song --bars 32
```

It converts the pack with every chance step made certain, plays each project in the host simulator, and compares
every note each track sends over MIDI with what the Circuit project holds: the same pitch, within 12 ms. A clean run
ends with `verify: every note matched`. Roll hits are counted but not timed.

## Not converted (yet)

- Synth patches are approximations. Knit has one oscillator wave (saw to pulse) in unison, a second oscillator, sub,
  noise, one filter, two envelopes and one LFO. The Circuit's wavetables, sine and triangle, ring modulation, chorus,
  EQ, the third envelope, the second LFO, most mod matrix routes and the macros are left out. The report lists them
  for each patch.
- Automation (macro and mixer locks) and per-step sample-flip pitch.
- Triplet rates play straight, and ping-pong and random pattern directions play forwards. Both are reported.
- Drum pitch and decay are copied as values, not measured against the Circuit.
- Which byte the Circuit loads as a drum track's sample is not certain: the converter uses 0x1A278, the default drum
  choices (RosettaGM's format notes).

## Files

- `ct2mtx.py`: the converter. `ctpack.py`: reads packs. `knitmap.py`: patches to knit. `pool.py`: the alternates.
  `consts.py`: MiniTraxFM's parameter numbers (`consts.check()` compares them with the headers). `verify.py`: the
  check. `survey.py`: what a set of `.ncs` files hold. `make_test_pack.py`: a test pack from another pack's sounds and
  any `.ncs` projects.
- `vendor/ncs_parser.py`: [circuit-tracks-tools](https://github.com/namirsab/circuit-tracks-tools)' `.ncs` parser by
  Namir Sayed-Ahmad Baraza (MIT), unchanged.
- The pack format notes come from [RosettaGM](https://github.com/GuinanNo1/RosettaGM)'s
  `circuitgm/docs/circuit-tracks-file-formats.md` and circuit-tracks-tools' `docs/ncs-format.md`.
