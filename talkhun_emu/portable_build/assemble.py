# -*- coding: utf-8 -*-
"""Assemble the portable (embeddable-Python) BraiLab games emulator.

Layout produced:
    BraiLabPC-portable/
        python/          embeddable Python 3.13 (full stdlib in python313.zip)
        app/             braipc.py + engine sources
        lib/             numpy/scipy/unicorn/sounddevice (from C:\\Python313)
        archive/         TALKHUN0.COM  (Arato's file, release only)
        BraiLab-jatek.cmd   launcher
"""
import os, shutil, sys, zipfile

BUILD = os.path.dirname(os.path.abspath(__file__))
EMU = os.path.dirname(BUILD)                       # talkhun_emu
ROOT = os.path.dirname(EMU)                        # repo root
SITE = os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
OUT = os.path.join(BUILD, "BraiLabPC-portable")
if os.path.isdir(OUT):
    shutil.rmtree(OUT)

# 1) embeddable python (already extracted to BUILD/python)
shutil.copytree(os.path.join(BUILD, "python"), os.path.join(OUT, "python"))
# configure sys.path: stdlib zip, self, ../app, ../lib
pth = os.path.join(OUT, "python", "python313._pth")
open(pth, "w").write("python313.zip\n.\n../app\n../lib\n")

# 2) app: engine sources
app = os.path.join(OUT, "app"); os.makedirs(app)
APP_PY = ["braipc.py", "brailab_device.py", "dos_host.py", "synth.py",
          "chip_synth.py", "pcf8200.py", "pcf8200_tables.py", "talkhun.py"]
for m in APP_PY:
    shutil.copy2(os.path.join(EMU, m), os.path.join(app, m))

# 3) lib: vendored deps
lib = os.path.join(OUT, "lib"); os.makedirs(lib)
IGN = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests", "test",
                             "*.lib", "*.a", "*.exp", "*.pdb", "*.h", "include", "*.pyi")
# scipy is gone: chip_synth + synth.resample are now pure-numpy (see chip_synth
# _LP2600_SOS and synth.resample).  That drops ~100 MB from the bundle.
DEPS = ["numpy", "numpy.libs", "unicorn",
        "sounddevice.py", "_sounddevice.py", "_sounddevice_data"]
for d in DEPS:
    s = os.path.join(SITE, d)
    if os.path.isfile(s):
        shutil.copy2(s, os.path.join(lib, d))
    elif os.path.isdir(s):
        shutil.copytree(s, os.path.join(lib, d), ignore=IGN)
    else:
        print("WARN missing dep:", d)
# cffi + pycparser: sounddevice needs them
for extra in ("cffi", "_cffi_backend", "pycparser"):
    for cand in (extra + ".py", extra):
        s = os.path.join(SITE, cand)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(lib, cand)); break
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(lib, cand), ignore=IGN); break
    else:
        # _cffi_backend is a .pyd
        import glob
        for pyd in glob.glob(os.path.join(SITE, extra + "*.pyd")):
            shutil.copy2(pyd, os.path.join(lib, os.path.basename(pyd)))

# 4) archive: Arato's TALKHUN (release only).  boot() loads TALKHUN.COM (v4);
# talkhun.load() accepts either.  Ship both -- they're ~110 KB together.
arch = os.path.join(OUT, "archive"); os.makedirs(arch)
for tk in ("TALKHUN.COM", "TALKHUN0.COM"):
    shutil.copy2(os.path.join(ROOT, "BRAILAB-archive", tk), os.path.join(arch, tk))

# 5) launcher
cmd = (
    "@echo off\r\n"
    "REM BraiLab PC games emulator -- portable. Runs a 1991 DOS program with\r\n"
    "REM the speech coming out of your speakers. No install, no Python needed.\r\n"
    "setlocal\r\n"
    'set "BRAILAB_ARCHIVE=%~dp0archive"\r\n'
    '"%~dp0python\\python.exe" "%~dp0app\\braipc.py" %*\r\n'
)
open(os.path.join(OUT, "BraiLab-jatek.cmd"), "w", newline="").write(cmd)

sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
print("assembled BraiLabPC-portable: %.0f MB" % (sz / 1e6))
print("->", OUT)
