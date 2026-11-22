# SPDX-License-Identifier: MPL-2.0
"""Reading a Novation Circuit Tracks pack (.circuittrackspack): its index, projects, patches and samples.

A pack is a ZIP: index.json (64 projects, 128 patches, 64 samples, each {name, url}; an array position is a slot), then
projects/project_N.ncs, patches/patch_N.syx, samples/sample_N.wav. An empty slot is listed but has no file.
Format notes: RosettaGM's circuitgm/docs/circuit-tracks-file-formats.md (GuinanNo1) and circuit-tracks-tools'
docs/ncs-format.md (Namir Sayed-Ahmad Baraza, MIT); the .ncs parser is circuit-tracks-tools' (vendor/).
"""
import io
import json
import os
import sys
import wave
import zipfile
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vendor import ncs_parser as N  # noqa: E402

# raw offsets in an .ncs (RosettaGM's notes)
PATCH_SLOT = (0xCD64, 0xCD6C)            # Synth 1 / Synth 2: the pack's patch slot
PATCH_EMBED = (0x26D14, 0x26E68)         # each synth's own working copy of its patch (340 bytes): what it plays
DEFAULT_DRUMS = 0x1A278                  # 4 bytes: each drum track's sample slot
DRUM_MUTES = 0x1A274                     # 4 bytes
PATCH_LEN = 340


@dataclass
class Project:
    slot: int                            # 0..63
    name: str
    raw: bytes
    ncs: object                          # vendor.ncs_parser.NCSFile
    patch_slots: list = field(default_factory=list)
    patches: list = field(default_factory=list)      # two 340-byte patches (the embedded copies)
    default_drums: list = field(default_factory=list)

    def has_content(self):
        n = self.ncs
        return (any(s.assigned_note_mask for p in n.synth_patterns + n.midi_patterns for s in p.steps)
                or any(s.active for p in n.drum_patterns for s in p.steps))


@dataclass
class Sample:
    slot: int
    name: str
    rate: int
    frames: list                         # float -1..1, mono

    @property
    def seconds(self):
        return len(self.frames) / float(self.rate)


def read_wav(data):
    """a WAV's samples as mono floats, and its rate (16- or 24-bit PCM)"""
    w = wave.open(io.BytesIO(data))
    ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    out = []
    if width == 2:
        import array
        a = array.array("h")
        a.frombytes(raw[: len(raw) // 2 * 2])
        if sys.byteorder != "little":
            a.byteswap()
        vals = [v / 32768.0 for v in a]
    elif width == 3:
        vals = []
        for i in range(0, len(raw) - 2, 3):
            v = raw[i] | raw[i + 1] << 8 | raw[i + 2] << 16
            vals.append((v - (1 << 24) if v & 0x800000 else v) / 8388608.0)
    elif width == 1:
        vals = [(b - 128) / 128.0 for b in raw]
    else:
        raise ValueError(f"{width * 8}-bit WAV")
    if ch == 1:
        out = vals
    else:
        out = [sum(vals[i:i + ch]) / ch for i in range(0, len(vals) - ch + 1, ch)]
    return out, rate


class Pack:
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path)
        names = set(self.zip.namelist())
        try:
            self.index = json.loads(self.zip.read("index.json"))
        except KeyError:
            raise ValueError(f"{path}: no index.json, so not a Novation Components pack")
        if self.index.get("product") not in (None, "circuit-tracks"):
            raise ValueError(f"{path}: a pack for {self.index.get('product')!r}, not the Circuit Tracks")
        self.name = self.index.get("name", os.path.splitext(os.path.basename(path))[0])
        self._has = lambda u: bool(u) and u in names
        self.sample_names = [(s or {}).get("name", "") for s in self.index.get("samples", [])]
        self.patch_names = [(p or {}).get("name", "") for p in self.index.get("patches", [])]
        self._samples = {}

    def projects(self):
        """every project slot with a file, parsed (unreadable ones reported, not raised)"""
        out, errors = [], []
        for i, p in enumerate(self.index.get("projects", [])):
            url = (p or {}).get("url")
            if not self._has(url):
                continue
            raw = self.zip.read(url)
            if raw[:4] != b"USER":
                continue                 # Components' blank slot
            try:
                ncs = N.parse_ncs_from_bytes(raw)
            except Exception as e:      # noqa: BLE001 (a damaged project: reported, the rest go on)
                errors.append((i, str(e)))
                continue
            pr = Project(slot=i, name=(p.get("name") or ncs.header.name or f"project {i + 1}").strip(), raw=raw,
                         ncs=ncs)
            pr.patch_slots = [raw[o] for o in PATCH_SLOT]
            pr.patches = [raw[o:o + PATCH_LEN] for o in PATCH_EMBED]
            pr.default_drums = list(raw[DEFAULT_DRUMS:DEFAULT_DRUMS + 4])
            out.append(pr)
        return out, errors

    def sample(self, slot):
        """sample slot as a Sample, None when the slot is empty"""
        if slot in self._samples:
            return self._samples[slot]
        s = None
        ents = self.index.get("samples", [])
        if 0 <= slot < len(ents) and self._has((ents[slot] or {}).get("url")):
            frames, rate = read_wav(self.zip.read(ents[slot]["url"]))
            s = Sample(slot=slot, name=ents[slot].get("name", "") or f"sample {slot + 1}", rate=rate, frames=frames)
        self._samples[slot] = s
        return s
