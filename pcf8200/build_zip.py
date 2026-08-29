# -*- coding: utf-8 -*-
r"""Package the standalone pcf8200 library for release.

    python build_zip.py            -> ../release/pcf8200-python-<version>.zip

This exists because the released zip silently went stale: it was built once by
hand for v3.0.5 and then re-attached to two later releases, so the published
library was missing the FS frame-timing fix, the continuous rate control, and
the output high-pass -- all of which the repository had. A script that reads the
version out of the package and rebuilds from the working tree cannot drift like
that, and `verify()` refuses to write a zip whose contents do not match.
"""
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "release")

#: What a user of the library needs. Tests and the build script itself stay out.
FILES = [
    "__init__.py", "chip.py", "device.py", "protocol.py", "tables.py",
    "voice.py", "phonemes.py", "README.md", "LICENSE", "pyproject.toml",
]
EXAMPLES = ["vowels.py", "frames.py", "polish.py"]

#: Things the published zip must contain, with the release that added them --
#: cheap insurance against shipping another stale copy.
REQUIRED = [
    ("device.py", "_std_samples", "v3.1: honour the FS speed bits"),
    ("device.py", "time_scale", "v3.2: continuous rate control"),
    # The *value*, not just the name: v3.2 shipped this constant set to 600,
    # which was tuned against a speaker recording and gutted the low end.
    ("chip.py", "HIGHPASS_HZ = 90.0", "v3.2.1: high-pass, corrected cutoff"),
    ("chip.py", "HIGHPASS_MAKEUP = 0.81", "v3.2.1: matching makeup gain"),
]


def version():
    text = open(os.path.join(HERE, "pyproject.toml"), encoding="utf-8").read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("no version in pyproject.toml")
    return m.group(1)


def verify():
    missing = []
    for name, needle, why in REQUIRED:
        src = open(os.path.join(HERE, name), encoding="utf-8").read()
        if needle not in src:
            missing.append("%s is missing %r (%s)" % (name, needle, why))
    return missing


def main():
    missing = verify()
    if missing:
        print("refusing to build; the working tree is behind:")
        for m in missing:
            print("  " + m)
        return 2

    ver = version()
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    out = os.path.join(OUT_DIR, "pcf8200-python-%s.zip" % ver)
    if os.path.exists(out):
        os.remove(out)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in FILES:
            z.write(os.path.join(HERE, name), "pcf8200/%s" % name)
        for name in EXAMPLES:
            p = os.path.join(HERE, "examples", name)
            if os.path.isfile(p):
                z.write(p, "pcf8200/examples/%s" % name)

    n = len(zipfile.ZipFile(out).namelist())
    print("-> %s (%d files, %.1f KB)" % (out, n, os.path.getsize(out) / 1024.0))
    for name, needle, _why in REQUIRED:
        s = zipfile.ZipFile(out).read("pcf8200/%s" % name).decode("utf-8")
        print("   %-12s contains %-16s %s" % (name, needle, needle in s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
