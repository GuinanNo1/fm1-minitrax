# MiniTraxFM: handoff (25 Nov 2026)

## Where things stand

- **Repo:** GuinanNo1/fm1-minitrax, branch `main`, last commit `c94a7f9`. The tree is clean and pushed.
- **Site:** https://guinanno1.github.io/fm1-minitrax/ (emulator, quick start, guide, pack loader, mirror). It redeploys on every push to main.
- **Install page: ON HOLD.** `INSTALL_HOLD=true` is set inside the build script in `.github/workflows/pages.yml`. Keep it that way until the user says the UI is ready. The firmware itself can stay on GitHub.
- **Converter:** `tools/ct2mtx/` works and is verified note for note against the real test packs (see `tools/ct2mtx/README.md`).
- **Current task: the on-device UI redesign.** Stage 1 (SEQ) is done. Stage 2 (Mixer and FX) is blocked on flash space.

## The UI plan (agreed with the user)

Each printed FM-1 control opens the matching Circuit Tracks view.

| FM-1 | Opens | Circuit Tracks equivalent | Status |
| --- | --- | --- | --- |
| ALGORITHM | picks the track, 1–8 (track selection is by ALGORITHM only) | track buttons | **done** |
| SEQ | piano roll (synths) or step grid (drums). SELECT turns to page 2, Pattern settings | Note view, Velocity, Gate, Probability, Micro step, Pattern settings | **done** |
| GLO | Mixer. Page 1: levels for SYN1, SYN2, MIDI1, MIDI2 on KNOB 1–4. Page 2: Drum 1–4 levels. Pages 3–4: pans. Black keys 1–8 mute | Mixer view | next |
| FX | Pages 1–2: reverb sends for the 8 tracks. Pages 3–4: delay sends. Page 5: reverb and delay presets | FX view | next |
| HOME | patterns and scenes (8 tracks × 8 patterns), chaining, mutes | Patterns, Scenes | to do |
| EDIT + PRESETS | the sound: PRESETS picks the patch or sample, the knobs are macros 1–4 (page 2: 5–8) | Preset, Macros | to do |
| ARP | **Scales** (user's choice) | Scales | to do |
| ENV, LFO | deeper synth editing | (Components) | to do |
| SAVE | save; held, the projects | Save, Projects | to do |
| SEL | held, shift (clear, duplicate…); tapped, the page's menu | Shift | to do |
| REC, PLAY | as now | Record, Play | done |

Two more rules from the user:

- **Hide LOOM-8's extras** (the conductor/brain, weave, punch/throw aux tracks, players, tricks/components, p-lock pages). Nothing on screen the Circuit doesn't have.
- **The one deliberate difference from the Circuit is piano-roll editing.** A piano roll in the converter is possible later.
- Each stage goes to the website emulator for the user to try before the next starts.

## Next step: reclaim flash. The user wants as much as possible removed

The firmware build (CI log, run 45457568730) reports **image 580,764 B against the app slot 0x8DFBC = 581,564 B, so only about 800 B is free**. RAM has 2,776 B free. The Mixer and FX pages won't fit until code is removed.

The user's instruction: **remove the hidden features to reclaim as much space as possible.** They don't need to stay recoverable, but the code from before the removal gets a tag.

**First, before removing anything: the user is tagging the pre-removal commit on GitHub.** The tag is `pre-strip` on `5c6ba29` (main as of 25 Nov 2026). Pushing the tag from Claude's session was refused (HTTP 403 from the git proxy; branch pushes work), so the user will create it on GitHub: Releases → Draft a new release → new tag `pre-strip`, target `main` (`5c6ba29`) → publish the release (a saved draft doesn't create the tag). Check it's there before the first removal commit: `git ls-remote --tags origin pre-strip`.

Candidates, roughly biggest first. Check each before removing it.

1. **The acid engine:** `app/dsp/bass303.c` (1,049 lines) plus `bass303.h`. `EG_ACID` isn't allowed on any track (`mt_engine_ok` in `app/app.h` allows only KNIT, RAYON, JACQUARD, BELLOWS, CANE and VOILE). Also remove the other disallowed engines' code in `synth.c` and `engine.c`: acid, sample, slice, midi, and any engine besides those six.
2. **Factory drum synthesis:** `app/dsp/d909.c` (740 lines) and the analog/909 models in `drumline.c`. Drum keys are sample-only (`DM_SAMPLE`; `set_tp` refuses anything else). Dropping them also frees the **resource region's 909 cymbals** (`fm1.toml` resources and `app/res.c`; the large type also lives there). Check `digisophie.c` (388 lines) the same way.
3. **The conductor/brain** (`AUX_BRAIN`, about 160 references to "brain"), **weave** (`AUX_WEAVE`, about 110), **punch/throw** (`AUX_PUNCH`), the **FX aux tracks** (`AUX_FX1/2`: but check whether reverb and delay live there before cutting, since the FX page needs them), **players** (`PL_*`), **tricks/components** (`comp_*`, "trick"). These are spread across `seq/seq.c`, `ui.c`, `pages.c`, `engine.c` and `project.c`.
4. **Unused pages** in `pages.c` and `ui.c`: the weave steps, step pool, chord page, P_STATUS, the lock pages, the aux engine pages, and the old `draw_steps_as` cells. The old cell view still draws aux tracks and chord mode; SEQ now draws `draw_roll`, `draw_dgrid` and `draw_patset`.
5. `app/dsp/bench.c` is compiled in (`o2` list in `fm1.toml`) but should be empty unless `XY_BENCH=1`. Confirm it costs nothing.
6. `app/bt.c`, `app/midicc.c`: keep unless the user agrees to drop them (MIDI matters for the MIDI 1/2 tracks).

**Project format:** removing tracks or parameters changes `proj_t` and the backup layout. Then bump `PROJ_MAGIC` and `APP_BACKUP_MAGIC` in `app/app.h` and update the converter (`tools/ct2mtx/consts.py`, whose `check()` compares against the headers, and the `mt*` host import commands in `app/host.c`). Re-run `tools/ct2mtx/verify.py` on the test packs afterwards.

**Measuring size:** the device toolchain only runs in CI (the shared builder `zvenson/fm1-build`). Push, then read it with `gh run view <id> -R GuinanNo1/fm1-minitrax --log | grep " ok  *image"`. The host build is only a rough guide to relative size.

## How to build and test locally

- **Host simulator:** `cd ~/fm1-minitrax && ./build.sh --host`, giving `app/build/host/minitrax_host SCRIPT.xy OUTDIR` (commands: `tap/press/release BTN`, `turn ENC n`, `key n down/up`, `tapkey n`, `wait ms`, `shot name.png`).
- **A real pack in the simulator:** `python3 tools/ct2mtx/ct2mtx.py "<pack>.circuittrackspack" -o /tmp/ui/x.mtx --keep` writes an `.xy` alongside. Its lines 2–582 load the first project; append UI commands and a `shot`. `/tmp/ui/mk.sh` did this, but it lives in /tmp and may be gone.
- **Test packs:** in the user's `~/Documents/Claude` (staged at `/mnt/user-data/uploads/Claude/CircuitGM-testdata/tracks/`). Converted outputs are in `~/Documents/Claude/MiniTraxFM/`.
- **Sequencer tests:** `tests/host/seq_test.c` (68 pass). Scenario smoke test: `tests/scenarios/mt_layout.xy`. 35 of LOOM's 77 scenarios still fail on the old layout; rewrite or delete them during the strip.
- **Web emulator, locally:** `./build.sh --web` (clang + wasi-sdk-24 through `~/bin/emcc`). CI builds and deploys it anyway.

## Stage 1 changes (for reference)

- `app/pages.c`
  - `draw_roll` (piano roll; it auto-fits the pattern's note range, row height 3–9 px, PRESETS scrolls via `ui.roll_ofs`).
  - `draw_dgrid` (a row per drum key used, plus a velocity lane).
  - `draw_patset` (Pattern settings overview) and `dkey_name` (drum row names from the sample bank via `smp_name`).
  - `TRACK_NAME` is now SYN1…DRUM4; the engine name is gone from the breadcrumb; the page names are Notes, Steps and Pattern; the knob labels are GATE, NOTE and RATE; the footer hints are updated.
- `app/ui.c`
  - `track_step`: ALGORITHM moves through tracks 0–7 only.
  - PRESETS on SEQ scrolls the roll.
  - `bar_knob`: K1/K2 set the loop start and end (`lstart`/`lend`), K3 quantise, K4 default gate.
- `docs/QUICKSTART.md`: new section "5. Edit a pattern (SEQ)".

## Open items

- **Pattern direction** (forward/reverse/ping-pong/random) isn't in `tpat_t` or the sequencer; adding it needs a field and a seq change.
- **Drum row names** should show the pack's sample names when the bank is loaded; this hasn't been checked on the emulator yet.
- **The `FM-1_13` device identity** is a placeholder.
- **Docs:** update the MANUAL as each stage lands.
