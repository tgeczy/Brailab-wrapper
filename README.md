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

## Building `brailab_wrapper.dll` (32-bit)

Brailab is typically a **32-bit** DLL, so you must build the wrapper as **Win32/x86** and use **32-bit NVDA**.

From an **“x86 Native Tools Command Prompt for VS”**:

```bat
cmake -S . -B build-x86 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-x86
