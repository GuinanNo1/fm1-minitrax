#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""A Circuit Tracks pack for the converter's tests: a pack's samples and patches (TracksGM, say) with .ncs projects
put in its first project slots.

    make_test_pack.py BASE.circuittrackspack OUT.circuittrackspack PROJECT.ncs ...
"""
import json
import sys
import zipfile


def main(base, out, projects):
    zin = zipfile.ZipFile(base)
    index = json.loads(zin.read("index.json"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i, path in enumerate(projects):
            url = f"projects/project_{i}.ncs"
            z.writestr(url, open(path, "rb").read())
            index["projects"][i] = {"name": path.rsplit("/", 1)[-1].rsplit(".", 1)[0][:16], "url": url}
        z.writestr("index.json", json.dumps(index, indent=2))
        for n in zin.namelist():
            if n != "index.json" and not n.startswith("projects/project_"):
                z.writestr(n, zin.read(n))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
