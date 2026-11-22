// SPDX-License-Identifier: MPL-2.0
// MiniTraxFM's own part of fm1-base's emulator page (LOOM-8's, with "Load converted pack": below) (base/web/emu/index.html; fm1-base's build loads it as app_own.js
// beside the emulator's parts, when the emulator is switched on). It works through the page's own names (KEYMAP,
// holdDown, turn, knobs, buttons, shortcuts, controls, node): the projects saved by the earlier page, what each
// control does on hover, and LOOM-8's computer keys: Space PLAY, Enter REC, / SEQ, as everywhere on the page, not
// only on the panel. A control reached with Tab keeps Space and Enter for itself (it presses that control); one
// clicked with the mouse or a finger does not, so Space stays PLAY after playing the panel with the mouse.

// what each control does, on hover and for a screen reader (the Buttons list below the panel says the same)
const TIP = { FX: "Sends and effects", SEL: "The page's list: copy, paste, weave, presets", ENV: "Envelope and filter",
  LFO: "LFO", EDIT: "The sound", GLO: "Mix, master and setup", HOME: "Arrange; held, the shift key", SAVE: "Save",
  ARP: "Players: arp, strum, hold", SEQ: "Steps; held, play the notes a step takes", PLAY: "Start / stop",
  REC: "Held: record; stopped, a tap: step record", "OCT-": "An octave down", "OCT+": "An octave up", SELECT: "Page",
  ALGORITHM: "Track", PRESETS: "Next sound", MASTER: "Volume" };
function tips() {
  for (const [n, b] of Object.entries(buttons)) if (TIP[n]) { b.hit.title = TIP[n]; b.hit.setAttribute("aria-description", TIP[n]); }
  for (const [n, k] of Object.entries(knobs)) {
    if (!TIP[n] || n === "MASTER") continue;
    const how = k.hit.getAttribute("aria-description");
    k.hit.title = TIP[n];
    k.hit.setAttribute("aria-description", how ? `${TIP[n]}. ${how}` : TIP[n]);
  }
}

// the computer's keys: fm1-base's map (white keys Q-I, A-K; black keys 1-0, -; Esc HOME; Z / X octave) and LOOM-8's
const KNOB_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End"]);
function keyboard() {
  const map = { ...KEYMAP, Space: { btn: BTN.PLAY }, Enter: { btn: BTN.REC }, Slash: { btn: BTN.SEQ } };
  let clicked = null;                    // the control the mouse or a finger last gave the focus to
  controls.addEventListener("pointerdown", (e) => { clicked = e.target.closest(".hit"); }, true);
  addEventListener("keydown", (e) => { if (e.key === "Tab") clicked = null; }, true);
  addEventListener("keydown", (e) => {
    if (!node || !shortcuts.checked || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t !== document.body && t !== document.documentElement && !controls.contains(t)) return;   // the page's fields
    const hit = t.closest ? t.closest(".hit") : null;
    if (hit && hit.classList.contains("knob") && KNOB_KEYS.has(e.key)) return;   // a knob turns with its keys
    if (hit && hit !== clicked && (e.key === " " || e.key === "Enter")) return;   // reached with Tab: presses it
    if (e.code === "ArrowUp" || e.code === "ArrowDown") {
      turn(knobs.SELECT, e.code === "ArrowUp" ? 1 : -1);
      e.preventDefault(); e.stopPropagation();
      return;
    }
    const m = map[e.code];
    if (!m) return;
    e.preventDefault(); e.stopPropagation();
    if (!e.repeat) holdDown("k" + e.code, m.key !== undefined ? "key" : "btn", m.key !== undefined ? m.key : m.btn);
  }, true);
}

// Load converted pack: a ct2mtx .mtx file (fm1-base's backup file: the projects, then sections; the sample bank in
// its "LSMP" section) put into the emulator as the backup page and the samples page would put it on an FM-1. The
// bank goes into the data area the page keeps (the data part: the windows of app/dsp/sample.h SMP_REG*), the
// projects through the backup part's restore, then the page starts again (the app reads its bank at boot).
import * as data from "./parts/data.js";
import { imageLength } from "./parts/backup.js";

const ID = "minitrax";
const REGIONS = [[0xC1000, 0x1B000], [0xE5000, 0x17000], [0x93000, 0x4000]];   // (dsp/sample.h SMP_REG0..2)

function sections(file, from) {
  const out = {}, dv = new DataView(file.buffer, file.byteOffset, file.byteLength);
  let p = from;
  while (p + 8 <= file.length) {
    const tag = String.fromCharCode(...file.subarray(p, p + 4)), n = dv.getUint32(p + 4, true);
    if (p + 8 + n + 4 > file.length) break;
    out[tag] = file.subarray(p + 8, p + 8 + n);
    p += 8 + n + 4;
  }
  return out;
}

function putBank(area, base, bank) {
  let v = 0;
  for (const [off, size] of REGIONS) {
    if (v >= bank.length) break;
    const n = Math.min(size, bank.length - v), at = off - base;
    if (at < 0 || at + n > area.length) throw new Error("this emulator has no room for the sample bank");
    area.set(bank.subarray(v, v + n), at);
    v += n;
  }
}

async function loadPack(file, name, say) {
  const img = imageLength(file), image = file.slice(0, img), bank = sections(file, img).LSMP;
  if (!bank) say(`${name} has no samples in it: only its projects are loaded.`);
  const cur = await data.current();
  if (!cur) throw new Error("switch the emulator on first");
  if (bank) {
    const area = new Uint8Array(cur.data);
    putBank(area, cur.base, bank);
    data.stop();                           // (what the running emulator writes from now on is not kept)
    await data.keep(ID, area.buffer);
  }
  node.port.postMessage({ type: "app", part: "backup", cmd: "restore", image: image.buffer }, [image.buffer]);
  say(`Loading ${name}…`);
  await new Promise((r) => setTimeout(r, 1500));   // (the restore's objects reach the page's store)
  location.reload();
}

function packButton(ctx) {
  const bar = document.querySelector(".bar"), say = ctx.status || (() => {});
  if (!bar || bar.querySelector("#mt-pack")) return;
  const b = document.createElement("button"), pick = document.createElement("input");
  b.type = "button";
  b.id = "mt-pack";
  b.textContent = "Load converted pack…";
  b.title = "A .mtx file from the converter (tools/ct2mtx): its projects and samples";
  pick.type = "file";
  pick.accept = ".mtx";
  pick.hidden = true;
  b.addEventListener("click", () => pick.click());
  pick.addEventListener("change", async () => {
    const f = pick.files[0];
    pick.value = "";
    if (!f) return;
    if (!window.confirm(`Replace the emulator's three projects and its samples with ${f.name}?`)) return;
    try {
      await loadPack(new Uint8Array(await f.arrayBuffer()), f.name, say);
    } catch (e) {
      say(`${f.name}: ${e.message || e}`);
    }
  });
  bar.insertBefore(b, bar.firstChild && bar.firstChild.nextSibling);
  bar.appendChild(pick);
}

export function attach(ctx) {
  tips();
  keyboard();
  packButton(ctx || {});
}
