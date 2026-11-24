# MiniTraxFM quick start

From a Circuit Tracks pack to a song playing on your FM-1, in five steps. No FM-1 to hand? Every step works in the
[emulator](https://guinanno1.github.io/fm1-minitrax/emu/) too.

## 1. Install MiniTraxFM

Connect the FM-1 to your computer by USB and open the
[installer](https://guinanno1.github.io/fm1-minitrax/install/) in Chrome or Edge. Press **Install** and follow the
page. It takes about a minute, and the installer can always put M-VAVE's own firmware back.

## 2. Convert a pack

Save the pack from Novation Components as a `.circuittrackspack` file. Then, in a terminal:

```
git clone --recursive https://github.com/GuinanNo1/fm1-minitrax
cd fm1-minitrax
./build.sh --host
python3 tools/ct2mtx/ct2mtx.py "My Pack.circuittrackspack"
```

That makes `My Pack.mtx`: the pack's first three projects with notes in them, and only the samples they play. The
report beside it, `My Pack.txt`, lists what was kept and what was left out. To pick other projects, add
`--projects 1,5,9` (the pack's slots, from 1).

## 3. Load it

Open the [backup page](https://guinanno1.github.io/fm1-minitrax/backup/) in Chrome or Edge, with the FM-1
connected and stopped. Choose `My Pack.mtx` and press **Restore**. When MiniTraxFM asks on its screen, press
**SEL**. The samples follow, which takes about 20 seconds.

In the emulator: switch it on and press **Load converted pack…** under the FM-1.

## 4. Play

Press **PLAY**. The first project plays its song: each part of the Circuit's scene chain in turn.

| | |
| --- | --- |
| **HOME** | the arrangement: each track's pattern and playhead. Black keys 1 to 8 mute the tracks |
| **KNOB 1** on **HOME** | tempo |
| **ALGORITHM** | picks the track: 1 to 4 synths, 5 to 8 drums |
| **SEQ** | the selected track's pattern: a piano roll for a synth, a step grid for a drum. **SELECT** turns to page 2, Pattern settings |
| **EDIT**, then **PRESETS** | another sound for the track |
| **HOME**, **SEL**, LOAD PROJECT | the other two projects |

The tracks wear the Circuit's colours: synth 1 violet, synth 2 green, midi 1 blue, midi 2 pink, then the drums
orange, yellow, purple and aqua.

## 5. Edit a pattern (SEQ)

The screen shows the bar's 16 steps across, one for each white key; the squares 1 to 4 at the top right are the bars.

| | |
| --- | --- |
| tap a **white key** | a step on or off (a synth writes the notes you last played with **SEQ** held) |
| hold a **white key** | **KNOB 1** velocity, **KNOB 2** gate, **KNOB 3** chance, **KNOB 4** note; **OCT−/+** micro step |
| hold a step, press a later one | the first step's gate reaches to it |
| hold **SEQ**, play the keys | a keyboard: sets the notes a tap writes |
| **PRESETS** | moves the piano roll up or down |
| black keys (drum track) | pick the drum sound the steps write |
| **KNOB 1** to **4** | pattern, length, rate, groove |
| **SELECT** → Pattern | **KNOB 1** start, **KNOB 2** end, **KNOB 3** record quantise, **KNOB 4** default gate |

## 6. Save and back up

MiniTraxFM saves by itself a few seconds after you stop. To keep your changes on the computer, use **Backup** on
the [backup page](https://guinanno1.github.io/fm1-minitrax/backup/).

Next: the [user guide](https://guinanno1.github.io/fm1-minitrax/manual/), for the steps, the sounds, the mixer and
everything else.
