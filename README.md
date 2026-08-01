# Brailab-wrapper
A DLL wrapper for the Hungarian Brailab Speech synthesizer.


This project provides a small native wrapper around the classic **Brailab PC** TTS engine so it can be used cleanly from **NVDA** via **nvwave**.

Why this exists:

- The original Brailab `tts.dll` plays audio directly through WinMM (waveOut), bypassing NVDA’s audio pipeline.
- NVDA works best when synth audio goes through `nvwave` (device routing, consistent stop behavior, fewer conflicts).
- This wrapper hooks the WinMM waveOut APIs, captures PCM, and lets the NVDA driver feed it into `nvwave.WavePlayer`.

## What’s in this repo

- `brailab_wrapper.dll` (built from the sources here)
- A Python NVDA synth driver (`synthDrivers/brailab.py`) that uses the wrapper
- **`talkhun_emu/` — an emulator of the BraiLab PC itself** (see below)

## What’s NOT in this repo

- **The Brailab speech engine DLL (`tts.dll`) is not included here.**
  - It is distributed separately as part of the NVDA driver release package.
  - This repository only contains the wrapper + driver code.

## How it works (high level)

1. The NVDA driver calls into `brailab_wrapper.dll`.
2. The wrapper loads `tts.dll`.
3. MinHook detours WinMM functions (`waveOutOpen`, `waveOutWrite`, etc.).
4. When `tts.dll` tries to output PCM via `waveOutWrite`, the wrapper captures the PCM bytes.
5. The NVDA driver pulls PCM from the wrapper and feeds it to `nvwave`, so NVDA controls the audio output device.

The wrapper also:
- Paces output to prevent “fast synthesis / skipping” behavior.
- Applies tempo/pitch/volume on the same worker thread that calls `StartSay` (some engines behave like this internally).
- Supports an option to disable intonation using `TTS_StartSayWithNoIntonation` when available.

## Requirements

### Build tools
- Windows
- Visual Studio Build Tools (MSVC) + Windows SDK
- CMake + Ninja
- MinHook sources vendored into the repo (recommended)

### Runtime
- NVDA (the driver is written for modern NVDA versions; tested with NVDA 2025.x)
- Brailab `tts.dll` (provided via the NVDA driver release package, not this repo)

## `talkhun_emu/` — the BraiLab PC emulator

The wrapper above gives you the *voice*. This gives you the *machine*.

It runs the DOS programs written for BraiLab PC in the late 80s and 90s, with
the speech coming out of your speakers — and it does so by loading the original
**`TALKHUN.COM`** and running it, resident, inside an emulated DOS. That is the
real 1991 code, not a reimplementation. It watches `INT 10h` and speaks whatever
a program prints, exactly as it did on real hardware; the I2C traffic it
bit-bangs at the parallel port is decoded here and synthesised by a software
PCF-8200.

None of those programs were written to know about speech. They just printed,
and something else did the talking.

```
python talkhun_emu/braipc.py            # browse for a program and run it
python talkhun_emu/speak.py "mama."     # just the synthesiser
```

`F12` opens a settings menu — tempo, pitch, furcsa — which speaks itself, so it
needs no screen reader. Holding `Ctrl` skips through speech the way the real
card did, blips and all.

**`TALKHUN.COM` is not in this repo.** It is Vaspöri Teréz and Arató András's
work, not ours to redistribute; point `BRAILAB_ARCHIVE` at a folder containing
it.

**The games are not here either.** They are Hungarian blind-community software
from the 1990s and belong in a public archive rather than in this repository.

The technical basis is Arató's 1992 candidate dissertation, *A BraiLab beszélő
számítógépcsalád*, public at the Hungarian Electronic Library:
<https://mek.oszk.hu/02000/02025/02025.htm>

## Building `brailab_wrapper.dll` (32-bit)

Brailab is typically a **32-bit** DLL, so you must build the wrapper as **Win32/x86** and use **32-bit NVDA**.

From an **“x86 Native Tools Command Prompt for VS”**:

```bat
cmake -S . -B build-x86 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-x86
