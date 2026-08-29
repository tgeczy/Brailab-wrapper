# -*- coding: utf-8 -*-
r"""Assemble the self-contained "BraiLab PC (emulated)" NVDA add-on.

The emulated synth runs the 1991 TALKHUN engine (Unicorn) + a software PCF8200
(chip_synth) entirely inside NVDA's process.  NVDA ships neither numpy/scipy/
unicorn nor a full stdlib, so the add-on carries them under
    synthDrivers/_brailab_engine/lib/
plus a few stdlib modules NVDA trims but numpy needs (fileinput, secrets,
timeit).  TALKHUN0.COM is Arato Andras's work -- it is copied into the release
package's archive/ only, never committed to this repo.

    python build.py            -> release/brailabEmulated-<ver>.nvda-addon

Requires a Python (default: C:\Python313) whose site-packages has numpy, scipy
and unicorn, matching NVDA's Python ABI (3.13, 64-bit).
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                 # repo root
EMU = os.path.join(ROOT, "talkhun_emu")                       # engine sources
ARCHIVE_SRC = os.path.join(ROOT, "BRAILAB-archive")           # TALKHUN0.COM (not in git)
SITE = os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
STDLIB = os.path.join(os.path.dirname(sys.executable), "Lib")
VERSION = "3.0.5"

# mame_synth dropped: nothing on the driver path imports it (it only pulled in
# scipy).  scipy dropped: chip_synth + synth are now pure-numpy (see chip_synth
# _LP2600_SOS), which removes ~100 MB of vendored scipy from the add-on.
ENGINE_PY = ["talkhun.py", "chip_synth.py", "brai_synth.py",
             "pcf8200.py", "pcf8200_tables.py"]
DEPS = ["numpy", "numpy.libs", "unicorn"]
STDLIB_FILLERS = ["fileinput.py", "secrets.py", "timeit.py"]  # NVDA trims these; numpy needs them
IGN = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests", "test",
                             "*.lib", "*.a", "*.exp", "*.pdb", "*.h", "include", "*.pyi")


def bundle_vcrt(dst):
    """App-local MSVC runtime + Universal CRT, so numpy/unicorn's native DLLs load
    even without the VC++ redist / UCRT update (older Windows).  The driver
    os.add_dll_directory(_vcrt) before importing numpy; on modern Windows the OS
    copies are already loaded, so these only matter as a fallback."""
    import glob
    os.makedirs(dst, exist_ok=True)
    got = 0
    win = os.environ.get("SystemRoot", r"C:\Windows")
    vc_srcs = [os.path.join(win, "System32"), r"C:\Program Files\NVDA",
               os.path.dirname(sys.executable)]
    for dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        for s in vc_srcs:
            p = os.path.join(s, dll)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(dst, dll)); got += 1; break
        else:
            print("  WARN vcrt missing:", dll)
    kits = sorted(glob.glob(
        r"C:\Program Files (x86)\Windows Kits\10\Redist\*\ucrt\DLLs\x64"))
    if kits:
        for p in (glob.glob(os.path.join(kits[-1], "ucrtbase.dll")) +
                  glob.glob(os.path.join(kits[-1], "api-ms-win-crt-*.dll"))):
            shutil.copy2(p, os.path.join(dst, os.path.basename(p))); got += 1
    else:
        print("  WARN: no Windows SDK UCRT redist -- older Windows may need the UCRT update")
    print("  bundled %d CRT DLLs into _vcrt" % got)


def main():
    stage = os.path.join(HERE, "_stage")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    sd = os.path.join(stage, "synthDrivers")
    eng = os.path.join(sd, "_brailab_engine")
    lib = os.path.join(eng, "lib")
    os.makedirs(lib)
    os.makedirs(os.path.join(stage, "archive"))

    shutil.copy2(os.path.join(HERE, "manifest.ini"), os.path.join(stage, "manifest.ini"))
    shutil.copy2(os.path.join(HERE, "synthDrivers", "brailabEmulated.py"),
                 os.path.join(sd, "brailabEmulated.py"))
    open(os.path.join(eng, "__init__.py"), "w").close()
    for m in ENGINE_PY:
        shutil.copy2(os.path.join(EMU, m), os.path.join(eng, m))
    for pkg in DEPS:
        s = os.path.join(SITE, pkg)
        if not os.path.isdir(s):
            raise SystemExit("missing dependency %s in %s" % (pkg, SITE))
        shutil.copytree(s, os.path.join(lib, pkg), ignore=IGN)
    for f in STDLIB_FILLERS:
        shutil.copy2(os.path.join(STDLIB, f), os.path.join(lib, f))
    bundle_vcrt(os.path.join(lib, "_vcrt"))
    talkhun = os.path.join(ARCHIVE_SRC, "TALKHUN0.COM")
    if not os.path.isfile(talkhun):
        raise SystemExit("TALKHUN0.COM not found in %s (Arato's file, release only)" % ARCHIVE_SRC)
    shutil.copy2(talkhun, os.path.join(stage, "archive", "TALKHUN0.COM"))

    out_dir = os.path.join(ROOT, "release")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "brailabEmulated-%s.nvda-addon" % VERSION)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(stage):
            dns[:] = [d for d in dns if d != "__pycache__"]
            for f in fns:
                full = os.path.join(dp, f)
                z.write(full, os.path.relpath(full, stage))
    shutil.rmtree(stage)
    print("-> %s (%.0f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
