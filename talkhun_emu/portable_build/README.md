# BraiLab PC games emulator -- portable build

Assembles a self-contained Windows bundle that runs the 1991 JATEKOK DOS
programs with BraiLab speech coming out of the speakers -- no install, no
Python on the target machine, no hardware.  Aimed at Windows 7+ users who
can't run a modern toolchain.

## What's inside the bundle

```
BraiLabPC-portable/
    python/          embeddable CPython 3.13 (full stdlib in python313.zip)
    app/             braipc.py + the engine sources (talkhun, chip_synth, synth, ...)
    lib/             numpy + unicorn + sounddevice   (NO scipy -- the DSP is pure numpy)
    archive/         TALKHUN.COM (v4) + TALKHUN0.COM  (Arato Andras's work, release only)
    BraiLab-jatek.cmd   launcher
```

The speech is the rebuilt 10 kHz PCF8200 core (`chip_synth.render_chip_fast`),
so the portable emulator sounds exactly like the NVDA "BraiLab PC (emulated)"
synth.  Dropping scipy (its filters are hardcoded / reimplemented in numpy)
takes the bundle from ~158 MB to ~65 MB on disk / ~25 MB zipped.

## To build

1. Download `python-3.13.1-embed-amd64.zip` from python.org, extract it to
   `python/` here (an embeddable distro -- it has no site-packages of its own).
2. Build numpy/unicorn/sounddevice must be importable from the Python running
   `assemble.py` (a normal 64-bit CPython 3.13 with those installed).
3. `python assemble.py`  ->  `BraiLabPC-portable/`

`assemble.py` sets `python313._pth` so the bundle's Python finds `../app` and
`../lib`, and copies Arato's TALKHUN from `../../BRAILAB-archive` (not in git).
