# -*- coding: utf-8 -*-
r"""Assemble the self-contained "BraiLab PC (emulated)" NVDA add-on.

The voice is one library, talkhun.dll, in both widths: the 1991 TALKHUN engine on
MAME's 8086 feeding the PCF8200 core, all in C.  The driver reaches it through
brailab_voice.py with ctypes, so the add-on carries no numpy and no Unicorn.
TALKHUN0.COM is Arato Andras's work -- it is copied into the release package's
archive/ only, never committed to this repo.

    python talkhun_emu/csrc/build_native.py     (needs W64DEVKIT and W64DEVKIT_X86)
    python build.py          -> release/brailabEmulated-<ver>.nvda-addon
    python build.py --test   -> release/brailabEmulatedC-<ver>.nvda-addon

--test renames the add-on and its driver, so it installs beside the released one and
the two can be compared by switching synthesizer.
"""
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                 # repo root
EMU = os.path.join(ROOT, "talkhun_emu")                       # engine sources
ARCHIVE_SRC = os.path.join(ROOT, "third_party", "brailab")    # TALKHUN0.COM (NOTICE.md)
ENGINE = "_brailab_native"
MAME_LICENSE = os.path.join(EMU, "csrc", "cpu", "mame_i86", "LICENSE-BSD-3-Clause.txt")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    test = "--test" in sys.argv[1:]
    name = "brailabEmulatedC" if test else "brailabEmulated"
    engine = ENGINE + "_test" if test else ENGINE

    manifest = read(os.path.join(HERE, "manifest.ini"))
    driver = read(os.path.join(HERE, "synthDrivers", "brailabEmulated.py"))
    version = re.search(r"^version = (\S+)", manifest, re.M).group(1)
    if test:
        manifest = manifest.replace("name = brailabEmulated", "name = " + name)
        manifest = manifest.replace('summary = "BraiLab PC (emulated, PCF8200)"',
                                    'summary = "BraiLab PC (emulated, C test)"')
        driver = driver.replace('name = "brailabEmulated"', 'name = "%s"' % name)
        driver = driver.replace('"Brailab PC (emulated, PCF8200)"', '"Brailab PC (emulated, C test)"')
        driver = driver.replace(ENGINE, engine)
        if 'name = "%s"' % name not in driver or "C test" not in manifest:
            raise SystemExit("the test build's renames no longer match")

    stage = os.path.join(HERE, "_stage")
    lay_out(stage, name, engine, manifest, driver)

    out_dir = os.path.join(ROOT, "release")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%s-%s.nvda-addon" % (name, version))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(stage):
            dns[:] = [d for d in dns if d != "__pycache__"]
            for f in fns:
                full = os.path.join(dp, f)
                z.write(full, os.path.relpath(full, stage))
    shutil.rmtree(stage)
    print("-> %s (%.2f MB)" % (out, os.path.getsize(out) / 1e6))


def lay_out(stage, name="brailabEmulated", engine=ENGINE, manifest=None, driver=None):
    """The add-on's files, unzipped, in `stage`: what the tests load, and what gets zipped."""
    if manifest is None:
        manifest = read(os.path.join(HERE, "manifest.ini"))
    if driver is None:
        driver = read(os.path.join(HERE, "synthDrivers", "brailabEmulated.py"))
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    sd = os.path.join(stage, "synthDrivers")
    eng = os.path.join(sd, engine)
    os.makedirs(eng)
    os.makedirs(os.path.join(stage, "archive"))

    write(os.path.join(stage, "manifest.ini"), manifest)
    write(os.path.join(sd, name + ".py"), driver)
    open(os.path.join(eng, "__init__.py"), "w").close()
    shutil.copy2(os.path.join(EMU, "brailab_voice.py"), eng)
    shutil.copy2(MAME_LICENSE, os.path.join(eng, "LICENSE-MAME-8086.txt"))
    for arch in ("x64", "x86"):
        dll = os.path.join(EMU, "_bin", arch, "talkhun.dll")
        if not os.path.isfile(dll):
            raise SystemExit("%s isn't built: run talkhun_emu/csrc/build_native.py" % dll)
        os.makedirs(os.path.join(eng, "_bin", arch))
        shutil.copy2(dll, os.path.join(eng, "_bin", arch))
    talkhun = os.path.join(ARCHIVE_SRC, "TALKHUN0.COM")
    if not os.path.isfile(talkhun):
        raise SystemExit("TALKHUN0.COM not found in %s (Arato and Vaspori's file, see NOTICE.md)" % ARCHIVE_SRC)
    shutil.copy2(talkhun, os.path.join(stage, "archive", "TALKHUN0.COM"))


if __name__ == "__main__":
    main()
