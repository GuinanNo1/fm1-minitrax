#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Make MiniTraxFM's site for GitHub Pages (https://guinanno1.github.io/fm1-minitrax/):

  index.html                    what MiniTraxFM is, and the ways in: try it, install, quick start, guide, convert,
                                load a pack (backup), mirror, download, source
  quickstart/index.html         docs/QUICKSTART.md as a page (tools/make_manual.py)
  manual/index.html             docs/MANUAL.md as a page, its pictures in img/
  img/                          screenshots (docs/img)
  emu/                          MiniTraxFM in the browser (app/build/emu, from ./build.sh --web), with "Load converted
                                pack"
  words/                        the screen reader's words files (app/web/words)
  install/index.html            the web installer (fm1-base's web/installer.html, the package's metadata inlined;
                                Chrome or Edge, Web MIDI)
  backup/index.html             backup and restore in the browser: the projects and presets, and the sample bank in a
                                section of the file (app/web/backup/extras.js) - so a converted pack's .mtx loads here
  mirror/index.html             the FM-1's screen and panel on the computer (fm1-base's web/mirror; Chrome or Edge)
  firmware/minitrax-VERSION.fwsc  the package the installer writes; also the download (and its resource region)

  tools/make_pages.py PACKAGE.fwsc VERSION OUT_DIR [--build "test build, 22 Nov 2026, abc1234"]
  tools/make_pages.py --no-firmware VERSION OUT_DIR      (the pages without the installer and the download)

The look follows Novation Components (the Circuit Tracks' editor): charcoal, and the Circuit Tracks' eight track
colours, which the firmware's default theme wears too (app/pages.c "circuit"). The layout follows GIO-1's site. Every
page of the site wears the palette (dress()), whatever names its own stylesheet gives the colours."""
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "base" / "tools"))
import make_site as base_site  # noqa: E402  (fm1-base's: the installer, the backup page, the package format)
from make_site import product_of, strip_module  # noqa: E402

NAME = "MiniTraxFM"
REPO = "https://github.com/GuinanNo1/fm1-minitrax"
# the Circuit Tracks' track colours, as app/pages.c's "circuit" theme: synth 1 violet, synth 2 pale green, midi 1
# blue, midi 2 pink, drum 1 orange, drum 2 yellow, drum 3 purple, drum 4 aqua
TRACKS = ["#9660ec", "#8ce28c", "#468cff", "#ff6ebe", "#ff8c28", "#fad632", "#b854d6", "#3cdcdc"]
TRACK_NAMES = ["synth 1", "synth 2", "midi 1", "midi 2", "drum 1", "drum 2", "drum 3", "drum 4"]
# Components' charcoal: one palette, dark (the editor has no light one)
PALETTE = {"bg": "#161618", "card": "#222226", "now": "#2c2c31", "rule": "#34343a", "muted": "#a3a3ab", "ink": "#f0f0f2",
           "accent": "#9660ec", "on": "#ffffff", "teal": "#3cdcdc", "bad": "#ff5c5c", "focus": "#3cdcdc", "wave": "#6e6e78"}


def tokens(p):
    """the palette under every name the site's pages use for it (the landing's, the manual's, the installer's, the
    backup's, the emulator's)"""
    names = {"bg": ("ground", "bg", "paper"), "card": ("card", "panel"), "now": ("now",), "rule": ("rule", "line"),
             "muted": ("muted", "dim"), "ink": ("ink", "fg", "text"), "accent": ("accent", "red", "link"),
             "on": ("on-accent",), "teal": ("teal",), "bad": ("bad",), "focus": ("focus",), "wave": ("wave",)}
    out = [f"--{n}: {p[k]};" for k, ns in names.items() for n in ns]
    out.append(f"--key: {p['ink']}; --keytext: {p['bg']};")
    return " ".join(out)


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" '
         'crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700'
         '&family=Barlow+Semi+Condensed:wght@600;700&display=swap">')

SITE_CSS = """<style>
:root { --panel-lit: #9660ec; --panel-lit-ink: #ffffff; --panel-lit-white: #c9b2f6; --panel-lit-black: #3cdcdc;
        --panel-dim: #4a3a6e; --panel-dim-white: #dcd4ee; --panel-dim-black: #8fd8d8; }   /* (the FM-1's lights: fm1panel.js) */
:root, :root[data-theme="light"], :root[data-theme="dark"] { %s color-scheme: dark; }
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) { %s color-scheme: dark; } }
body { background: var(--bg) !important; color: var(--ink); }
a { color: #b896f5; }
.mt-top { position: sticky; top: 0; z-index: 10; background: rgba(22,22,24,.94); backdrop-filter: blur(6px);
          border-bottom: 1px solid var(--rule); margin: 0 -16px 28px; padding: 0 16px; }
.mt-top > div { max-width: 66rem; margin: 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: .3rem 1.4rem;
                min-height: 56px; font: 600 .8rem/1.4 "Barlow", "Helvetica Neue", Arial, sans-serif; letter-spacing: .09em; }
.mt-brand { display: inline-flex; align-items: center; gap: .6rem; color: var(--ink) !important; text-decoration: none;
            font: 700 1.25rem/1 "Barlow Semi Condensed", "Barlow", sans-serif; letter-spacing: .01em; }
.mt-pads { display: grid; grid-template-columns: repeat(4, 7px); gap: 2px; }
.mt-pads i { width: 7px; height: 7px; border-radius: 2px; }
.mt-brand b { font-weight: 700; color: #b896f5; }
.mt-top nav { display: flex; flex-wrap: wrap; gap: .1rem 1.2rem; margin-left: auto; text-transform: uppercase; }
.mt-top nav a { color: var(--muted); text-decoration: none; padding: 18px 0 15px; border-bottom: 3px solid transparent; }
.mt-top nav a:hover, .mt-top nav a:focus-visible { color: var(--ink); }
.mt-top nav a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--accent); }
@media (max-width: 640px) { .mt-top nav { margin-left: 0; width: 100%%; } .mt-top nav a { padding: 6px 0; } }
.mt-foot { max-width: 66rem; margin: 56px auto 0; padding-top: 18px; border-top: 1px solid var(--rule); color: var(--muted);
           font: 400 .85rem/1.5 "Barlow", Arial, sans-serif; }
</style>""" % (tokens(PALETTE), tokens(PALETTE))

SECTIONS = [("emu/", "Try it"), ("install/", "Install"), ("quickstart/", "Quick start"), ("manual/", "Guide"),
            ("backup/", "Load a pack"), ("mirror/", "Mirror")]

FOOT = (f'<footer class="mt-foot">{NAME} is not affiliated with Novation, Focusrite or M-VAVE. Novation, Circuit Tracks and '
        'Components are trademarks of Focusrite Audio Engineering; M-VAVE and FM-1 of their owner. MiniTraxFM is a fork of '
        '<a href="https://github.com/charlesvestal/fm1-loom">LOOM-8</a> by Charles Vestal, built on fm1-base and felucca-bsp, '
        f'which grew out of Felucca by Leo Kuroshita (Hügelton Instruments). <a href="{REPO}">Source on GitHub</a>.</footer>')


def pads(size=None):
    return "".join(f'<i style="background:{c}"></i>' for c in TRACKS)


def dress(page, here, sections):
    """a page of the site in the palette, with the site's header and footer; here: its section ("" the front page)"""
    up = "../" if here else ""
    links = "".join(f'<a href="{up}{d}"' + (' aria-current="page"' if d == here else "") + f">{t}</a>"
                    for d, t in sections)
    links += f'<a href="{REPO}">Source</a>'
    top = (f'<header class="mt-top"><div><a class="mt-brand" href="{up or "./"}"' + (' aria-current="page"' if not here else "") +
           f'><span class="mt-pads" aria-hidden="true">{pads()}</span>MiniTrax<b>FM</b></a>'
           f'<nav aria-label="{NAME}">{links}</nav></div></header>')
    if page.count("</head>") != 1 or not re.search(r"<body[^>]*>", page):
        raise SystemExit(f"dress: {here or 'index'}: no head or body")
    page = page.replace("</head>", FONTS + SITE_CSS + "</head>")
    page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + top, page, count=1)
    if "mt-foot" not in page:
        page = page.replace("</body>", FOOT + "</body>", 1)
    return page


LANDING = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiniTraxFM: Circuit Tracks packs on the FM-1</title>
<meta name="description" content="MiniTraxFM plays Novation Circuit Tracks packs on the M-VAVE FM-1: four synth tracks, four sample drum tracks, scenes and songs. Try it in the browser, install it, convert your packs.">
<style>
body { margin: 0; padding-inline: 16px; padding-block: 0 48px; font: 400 17px/1.6 "Barlow", "Helvetica Neue", Arial, sans-serif; }
main { max-width: 66rem; margin: 0 auto; }
.hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 28px 40px; align-items: center; margin: 18px 0 30px; }
@media (max-width: 760px) { .hero { grid-template-columns: 1fr; } }
.word { font: 700 clamp(3rem, 9vw, 5.6rem)/.95 "Barlow Semi Condensed", "Barlow", sans-serif; letter-spacing: -.01em; margin: 0; }
.word b { color: #b896f5; }
.tag { font: 500 1.3rem/1.35 "Barlow", sans-serif; color: var(--muted); margin: .7rem 0 1.1rem; max-width: 34rem; }
.bar { display: grid; grid-template-columns: repeat(8, 1fr); gap: 5px; max-width: 34rem; }
.bar span { height: 8px; border-radius: 3px; }
.grid8 { display: grid; grid-template-columns: repeat(4, 64px); gap: 9px; padding: 18px; background: #0e0e10; border-radius: 18px;
         border: 1px solid var(--rule); }
.grid8 span { height: 64px; border-radius: 10px; display: flex; align-items: flex-end; padding: 6px 7px; box-sizing: border-box;
              font: 700 .72rem/1 "Barlow Semi Condensed", sans-serif; color: rgba(0,0,0,.72); letter-spacing: .03em;
              box-shadow: inset 0 -10px 18px rgba(0,0,0,.18), 0 0 18px -6px currentColor; }
.lede { font-size: 1.12rem; max-width: 46rem; margin: 0 0 1.4rem; }
.status { border: 1px solid var(--rule); background: var(--card); border-radius: 12px; padding: 12px 16px; margin: 0 0 2rem;
          border-left: 4px solid #fad632; }
.status code { font-size: .88em; }
.shots { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin: 0 0 2.2rem; }
.shots figure { margin: 0; }
.shots img { width: 100%; height: auto; border-radius: 12px; image-rendering: pixelated; border: 1px solid var(--rule); display: block; }
.shots figcaption { font-size: .85rem; color: var(--muted); margin-top: 6px; }
h2 { font: 700 1.6rem "Barlow Semi Condensed", "Barlow", sans-serif; margin: 2.6rem 0 .9rem; }
.ways { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin: 0 0 1rem; }
.ways a { display: block; text-decoration: none; color: var(--ink); background: var(--card); border: 1px solid var(--rule);
          border-radius: 12px; padding: 14px 16px 15px; border-top: 4px solid var(--c); transition: background .12s; }
.ways a:hover, .ways a:focus-visible { background: var(--now); outline: none; }
.ways strong { font: 700 1.2rem "Barlow Semi Condensed", "Barlow", sans-serif; display: block; margin-bottom: 2px; }
.ways span { color: var(--muted); font-size: .94rem; line-height: 1.45; display: block; }
table { border-collapse: collapse; width: 100%; font-size: .97rem; }
.wrap { overflow-x: auto; background: var(--card); border: 1px solid var(--rule); border-radius: 12px; }
th, td { text-align: left; padding: 9px 14px; border-bottom: 1px solid var(--rule); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
th { color: var(--muted); font: 600 .75rem "Barlow", sans-serif; letter-spacing: .08em; text-transform: uppercase; }
td .sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 8px; }
pre { background: #0e0e10; border: 1px solid var(--rule); border-radius: 12px; padding: 14px 16px; overflow-x: auto;
      font: 14px/1.5 ui-monospace, Menlo, monospace; color: #e6e6ea; }
ul.feat { padding-left: 1.2rem; max-width: 50rem; }
ul.feat li { margin: 0 0 .5rem; }
</style>
</head>
<body>
<main>
<section class="hero">
  <div>
    <h1 class="word">MiniTrax<b>FM</b></h1>
    <p class="tag">Circuit Tracks packs on the M-VAVE FM-1.</p>
    <div class="bar" aria-hidden="true">__BAR__</div>
  </div>
  <div class="grid8" aria-hidden="true">__GRID__</div>
</section>
<p class="lede">MiniTraxFM turns the FM-1 into a pocket player for your Novation Circuit Tracks projects. Convert a
pack on your computer, load it onto the FM-1 and press PLAY: four polyphonic synth tracks and four sample drum tracks
play its patterns, scenes and songs, in the Circuit's own colours.</p>
<div class="status"><strong>__BUILD__</strong> MiniTraxFM is in testing: every change is built and published here,
for the emulator and the installer alike. You install and remove it like any other fm1-base firmware, and the
installer can always put M-VAVE's own firmware back. Install at your own risk.</div>
<div class="shots">__SHOTS__</div>

<h2>Get going</h2>
<nav class="ways" aria-label="Get MiniTraxFM">
  <a href="emu/" style="--c:#9660ec"><strong>Try it in the browser</strong><span>The firmware itself, running here with sound. Load a converted pack and play it, no FM-1 needed.</span></a>
  <a href="install/" style="--c:#8ce28c"><strong>Install</strong><span>Connect the FM-1 by USB and install from Chrome or Edge. Nothing to install on your computer.</span></a>
  <a href="quickstart/" style="--c:#468cff"><strong>Quick start</strong><span>From a Circuit Tracks pack to a song playing on the FM-1, in five steps.</span></a>
  <a href="manual/" style="--c:#ff6ebe"><strong>User guide</strong><span>The tracks, the steps, the sounds, the mixer, scenes and songs, saving.</span></a>
  <a href="__REPO__/tree/main/tools/ct2mtx" style="--c:#ff8c28"><strong>Convert a pack</strong><span>ct2mtx turns a .circuittrackspack into a MiniTraxFM file: three projects and the samples they play.</span></a>
  <a href="backup/" style="--c:#fad632"><strong>Load a pack</strong><span>Send a converted pack to the FM-1, and back up its projects and samples to a file.</span></a>
  <a href="mirror/" style="--c:#b854d6"><strong>Mirror</strong><span>The FM-1's screen live on the computer, and its buttons, keys and knobs to play from there.</span></a>
  __DOWNLOAD__
  <a href="__REPO__" style="--c:#6e6e78"><strong>Source</strong><span>On GitHub: GPL-3.0 (most files MPL-2.0). Issues and ideas welcome.</span></a>
</nav>

<h2>What goes where</h2>
<div class="wrap"><table>
<thead><tr><th>Circuit Tracks</th><th>MiniTraxFM</th><th></th></tr></thead>
<tbody>__ROWS__</tbody>
</table></div>

<h2>Converting a pack</h2>
<pre>git clone --recursive __REPO__
cd fm1-minitrax &amp;&amp; ./build.sh --host
python3 tools/ct2mtx/ct2mtx.py "My Pack.circuittrackspack"</pre>
<ul class="feat">
  <li>Only the samples the projects play go in, at 22 kHz, each trimmed to the longest it is ever heard. Long ones
    are left out (or kept while there is room, with <code>--fill</code>), and a missing drum gets a stand-in from a
    small synthesised set.</li>
  <li>Synth 1 and 2's patches are rebuilt on MiniTraxFM's synths; the report says what each lost.</li>
  <li>Patterns, chains and scenes become patterns, scenes and a song, checked note for note against the Circuit's
    own data (<code>tools/ct2mtx/verify.py</code>).</li>
  <li>Three projects fit, of the Circuit's 64: <code>--projects 1,5,9</code> picks them.</li>
</ul>

<h2>Thanks</h2>
<p>MiniTraxFM is <a href="https://github.com/charlesvestal/fm1-loom">LOOM-8</a> by Charles Vestal, cut down to the
Circuit Tracks' layout: its synths, sequencer, effects and pages are his. It runs on fm1-base and felucca-bsp, from
Felucca by Leo Kuroshita (Hügelton Instruments). The converter reads projects with
<a href="https://github.com/namirsab/circuit-tracks-tools">circuit-tracks-tools</a>' parser (MIT).</p>
</main>
</body>
</html>
"""


def shots_html():
    """the landing's screenshots: docs/img/mtx-*.png (tools/make_shots.sh), each with its alt text in docs/img/mtx.json"""
    meta = SRC / "docs" / "img" / "mtx.json"
    if not meta.exists():
        return ""
    out = []
    for f, (alt, cap) in json.loads(meta.read_text()).items():
        if (SRC / "docs" / "img" / f).exists():
            out.append(f'<figure><img src="img/{f}" width="240" height="240" alt="{html.escape(alt)}">'
                       f'<figcaption>{html.escape(cap)}</figcaption></figure>')
    return "".join(out)


def md_page(md, out_html, title):
    subprocess.run([sys.executable, str(SRC / "tools" / "make_manual.py"), str(md), str(out_html)], check=True)
    t = out_html.read_text(encoding="utf-8").replace('src="img/', 'src="../img/')
    t = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", t, count=1, flags=re.S)
    out_html.write_text(t, encoding="utf-8")


def main(argv):
    nofw = "--no-firmware" in argv
    argv = [a for a in argv if a != "--no-firmware"]
    build = None
    if "--build" in argv:
        i = argv.index("--build")
        build = argv[i + 1]
        del argv[i:i + 2]
    if nofw:
        if len(argv) != 2:
            sys.exit(__doc__)
        pkg, (version, out) = None, argv
    else:
        if len(argv) != 3:
            sys.exit(__doc__)
        pkg, version, out = Path(argv[0]), argv[1], argv[2]
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sections = [s for s in SECTIONS if not (nofw and s[0] == "install/")]
    pages = [("index.html", ""), ("quickstart/index.html", "quickstart/"), ("manual/index.html", "manual/"),
             ("backup/index.html", "backup/"), ("mirror/index.html", "mirror/"), ("emu/index.html", "emu/")]
    conf = base_site.read_conf(SRC / "app" / "fm1.toml")
    download = ""
    if pkg:
        raw = pkg.read_bytes()
        product = product_of(raw)
        if not re.fullmatch(r"FM-1_13\d*", product):
            raise SystemExit(f"{pkg}: identity {product!r}: not a MiniTraxFM package (FM-1_13...)")
        if b"FELUCCA-LOADER-1" not in raw:
            raise SystemExit(f"{pkg}: no update loader in it")
        name = f"minitrax-{re.sub(r'[^A-Za-z0-9.+-]', '-', version)}.fwsc"
        for d in ("install", "firmware"):
            (out / d).mkdir()
        shutil.copy(pkg, out / "firmware" / name)
        meta = {"version": version, "product": product, "pkg": "../firmware/" + name, "backup": True}
        res_src = pkg.with_name(pkg.stem + "-res.bin")      # the resource region (the large type, the 909 cymbals)
        if res_src.exists():
            from fm1_resources import ResError, payload_of
            try:
                payload_of(res_src.read_bytes())
            except ResError as e:
                raise SystemExit(f"make_pages: {res_src}: {e}")
            res_name = Path(name).stem + "-res.bin"
            shutil.copy(res_src, out / "firmware" / res_name)
            meta["res"] = "../firmware/" + res_name
        boot = SRC / "base" / "web" / "m-bootloader" / f"fm1-uboot-{base_site.MBOOT_VERSION}.fwsc"
        boot_name = f"m-bootloader-{base_site.MBOOT_VERSION}.fwsc"
        shutil.copy(boot, out / "firmware" / boot_name)
        shutil.copy(SRC / "base" / "web" / "m-bootloader" / "LICENSE", out / "firmware" / "m-bootloader-LICENSE.txt")
        for lic in sorted((SRC / "base" / "LICENSES").glob("*.txt")):
            shutil.copy(lic, out / "firmware" / lic.name)
        meta["boot"] = {"pkg": "../firmware/" + boot_name, "version": base_site.MBOOT_VERSION,
                        "sha256": hashlib.sha256(boot.read_bytes()).hexdigest()}
        page = (SRC / "base" / "web" / "installer.html").read_text(encoding="utf-8")
        lib = "\n".join(strip_module((SRC / "base" / "web" / f).read_text(encoding="utf-8"))
                        for f in ("fm1ports.js", "fm1pkg.js", "fm1ota.js"))
        for mark in ("/*LIB*/", "/*META*/", "/*APP*/"):
            if page.count(mark) != 1:
                raise SystemExit(f"base/web/installer.html must contain {mark} once")
        credits = conf.get("credits", "").replace("Built on fm1-base and felucca-bsp, from Felucca by Leo Kuroshita "
                                                  "(Hügelton Instruments). ", "")
        for key, val in (("RES", conf.get("resources_what", "")), ("RES_JA", conf.get("resources_what_ja", "")),
                         ("NAME", NAME), ("REPO", REPO), ("REPO_SHORT", REPO.replace("https://", "")),
                         ("LICENSE", conf.get("licence", "MPL-2.0")), ("CREDITS", " " + credits if credits else "")):
            page = page.replace("{{" + key + "}}", val)
        warn = '<p data-t="warn">'
        if page.count(warn) == 1:
            page = page.replace(warn, '<p class="note"><b>A test build.</b> MiniTraxFM is in testing, and this is the '
                                f'latest build ({html.escape(build or version)}). After installing, load a converted pack '
                                'from <a href="../backup/">Load a pack</a>.</p>\n  ' + warn)
            page = page.replace("</style>", "  .note { border-left: 4px solid #fad632; padding: 4px 0 4px 12px; }\n</style>", 1)
        # (MiniTraxFM adds nothing to the sample bank on install: the installer's app steps are none)
        (out / "install" / "index.html").write_text(page.replace("/*LIB*/", lib).replace("/*META*/", json.dumps(meta))
                                                    .replace("/*APP*/", "null"), encoding="utf-8")
        download = (f'<a href="firmware/{name}" style="--c:#3cdcdc"><strong>Download</strong><span>{html.escape(name)}, for '
                    f'the command-line installer: <code>python3 base/tools/fm1_install.py {html.escape(name)}</code></span></a>')
        pages.insert(1, ("install/index.html", "install/"))
    for d in ("backup", "mirror"):
        (out / d).mkdir(exist_ok=True)
    # the backup page: the projects and presets, and the sample bank in the file (a converted pack's .mtx loads here)
    extras = ("const EXTRAS = (() => {\n" +
              strip_module((SRC / "app" / "web" / "samples" / "loom_samples.js").read_text(encoding="utf-8")) + "\n" +
              (SRC / "app" / "web" / "backup" / "extras.js").read_text(encoding="utf-8") + "})();")
    note = ("\n  <li><b>A converted pack</b> (a <code>.mtx</code> file from <code>tools/ct2mtx</code>) is a backup: restore it "
            "here to load its three projects and its samples. MiniTraxFM asks on its screen first (<b>SEL</b> yes); the "
            "samples follow, which takes about 20 seconds.</li>")
    terminal = ("From a terminal, in MiniTraxFM's source folder: <code>python3 base/tools/fm1_backup.py restore FILE.mtx</code> "
                "for the projects, then <code>python3 tools/loom_samples.py restore FILE.mtx</code> for the samples.")
    tools = base_site.tool_pages(SRC / "app", conf, {"NAME": NAME, "EXTRAS_JS": extras, "EXTRA": note, "TERMINAL": terminal})
    (out / "backup" / "index.html").write_text(tools["backup/index.html"], encoding="utf-8")
    (out / "mirror" / "index.html").write_text(tools["mirror/index.html"], encoding="utf-8")
    # the docs
    shutil.copytree(SRC / "docs" / "img", out / "img")
    (out / "quickstart").mkdir()
    md_page(SRC / "docs" / "QUICKSTART.md", out / "quickstart" / "index.html", f"{NAME} quick start")
    (out / "manual").mkdir()
    md_page(SRC / "docs" / "MANUAL.md", out / "manual" / "index.html", f"{NAME} user guide")
    # the landing
    rows = "".join(f'<tr><td>{c}</td><td><span class="sw" style="background:{TRACKS[i]}"></span>track {i + 1}, '
                   f'{TRACK_NAMES[i]}</td><td>{w}</td></tr>'
                   for i, (c, w) in enumerate([
                       ("Synth 1", "a polyphonic synth, its sound rebuilt from the project's patch"),
                       ("Synth 2", "as synth 1"),
                       ("MIDI 1", "a polyphonic synth (on the Circuit it played another instrument)"),
                       ("MIDI 2", "as midi 1"),
                       ("Drum 1", "a sample kit: the track's sample and its flips, one hit at a time"),
                       ("Drum 2", "as drum 1"), ("Drum 3", "as drum 1"), ("Drum 4", "as drum 1")]))
    grid = "".join(f'<span style="background:{c};color:{c}"><em style="color:rgba(0,0,0,.72);font-style:normal">'
                   f'{TRACK_NAMES[i]}</em></span>' for i, c in enumerate(TRACKS))
    bar = "".join(f'<span style="background:{c}"></span>' for c in TRACKS)
    land = (LANDING.replace("__BAR__", bar).replace("__GRID__", grid).replace("__ROWS__", rows)
            .replace("__SHOTS__", shots_html()).replace("__DOWNLOAD__", download)
            .replace("__BUILD__", html.escape((build.rstrip(".") + ".") if build else f"Version {version}.")).replace("__REPO__", REPO))
    (out / "index.html").write_text(land, encoding="utf-8")
    # the emulator and the screen reader's words
    emu = SRC / "app" / "build" / "emu"
    if not (emu / "app.wasm").exists():
        raise SystemExit("no app/build/emu/app.wasm: run ./build.sh --web (needs Emscripten, or tools' WASI stand-in)")
    shutil.copytree(emu, out / "emu", ignore=shutil.ignore_patterns("o2", "web", "*.o"))
    shutil.copytree(SRC / "app" / "web" / "words", out / "words")
    for path, here in pages:
        f = out / path
        f.write_text(dress(f.read_text(encoding="utf-8"), here, sections), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"site: {out}: " + ", ".join(p for p, _ in pages) + (f", firmware/{name}" if pkg else " (no firmware)"))


if __name__ == "__main__":
    main(sys.argv[1:])
