# Moving the PCF8200 to portable C

The plan for taking the chip from Python to C, the way ssi263-speech did, without
losing what the Python library gives people. Steps 1 to 4 below are done; the add-on
and SAPI are not.

## What ssi263-speech does

- `src/ssi263/chip.py` stays the reference. Research and tuning happen there.
- `params.py` holds every uncertain constant in one place, tagged by its source.
  The C side receives them as one struct of doubles, in the header's order.
- `ssi263.c` is the same model in plain C99. `native.py` gives it the same class
  interface as `chip.py`, through ctypes, so no numpy is needed.
- `tools/check_native_core.py` runs both on seeded random sessions, under the
  defaults and with every switch flipped. Timing and integer state must be exact,
  audio within 1e-9, and the 16-bit PCM identical. Every add-on build runs it.
- `gen_chip_defaults.py` writes the defaults into a header for front ends with no
  Python, and `--check` fails if the header is stale.
- `build_native.py` uses w64devkit gcc, `-static`, `-ffp-contract=off`, and SSE2
  doubles on 32-bit, and refuses a DLL that imports anything beyond KERNEL32 and
  msvcrt.
- `python/ssi263speech` is a thin ctypes package around the same library: one wheel
  per platform, every Python 3, built by `python/build_wheel.py`. CI builds Linux
  in Debian 11 for a low glibc floor.
- Firmware runs on CPU cores extracted from MAME (BSD-3) behind `cpu/cpu.h`.
  `pc86/` is the DOS machine around the 8086 core.

## Where the PCF8200 stands

The code is small, but there are two renderers, and that comes first:

| Piece | File | Lines | Needs |
|---|---|---|---|
| The library's renderer | `pcf8200/chip.py` | 271 | numpy |
| The add-on's renderer | `talkhun_emu/chip_synth.py` | 510 | numpy, scipy off the default path |
| Frame decoding and tables | `talkhun_emu/pcf8200.py`, `pcf8200_tables.py`, `pcf8200/protocol.py`, `pcf8200/tables.py` | about 570 | nothing |
| Frame to parameters | `brai_synth.frame_params` | small | tables |
| TALKHUN0 running | `talkhun_emu/talkhun.py` | 359 | Unicorn |
| BRAISPK's synth | `dos_speaker/braispk.c` | part of 2201 | Watcom, x87 |

`chip.py` and `chip_synth.py` do the same maths but share only 29 lines.

## What stops C matching Python today

1. **Two references.** The add-on sums harmonics with a matrix `.sum(1)`, whose
   rounding depends on the matrix size. The library sums them in order, which is
   the form C can repeat. Use the library's.
2. **Noise.** Both use numpy's `default_rng`. That generator is not worth porting.
   Replace it in the reference with a small generator written out in both languages.
   This changes the noise samples, not the kind of noise, so it needs one ear check.
3. **Maths functions.** numpy's vector `sin` and `exp` can differ from C's in the
   last bit. ssi263's answer applies: audio within 1e-9, PCM identical.
4. **Streaming.** C has to work frame by frame. This should fit: each frame
   interpolates from the previous frame, with no lookahead, and the library's sum
   already makes any prefix of a render exact. One detail: stop each sample's sum
   at its own cutoff rather than at the utterance's `KMAX`. The harmonics beyond
   it add an exact zero.
5. **Other output rates.** The library resamples by FFT over the whole signal, which
   can't stream, and the add-on uses scipy. A C front end needs a streaming
   resampler; `ssi263dsp.c` has one to start from.
6. **Non-default low-pass.** This calls scipy's `butter`. C needs its own design;
   BRAISPK's `lp_design` already reproduces the 2600 Hz table.

## Keeping the flexibility

The `pcf8200` package keeps its API: `PCF8200`, `Chip`, `Voice`, `protocol`, `tables`,
`write_wav`, and every `render` option (`rate`, `source_tilt`, `lowpass`, `highpass`,
`noise_gain`, `seed`), any formant tracks, any language.

One difference from ssi263speech: the pure-Python renderer stays inside the package,
not only in the repository. It is the reference, and it is the fallback:

- With the wheel's native library present, `Chip.render` runs in C.
- Without it, on any platform with numpy, the same call runs in Python.
- `PCF8200_BACKEND=python` forces the reference, for research.

Because the noise changes, this is a 2.0 of the library. The Ciber232P add-on uses the
library's prefix renders, so it has to keep working through the same calls.

## BRAISPK

It can't take the full core: the harmonic sum doesn't fit a 166. It stays a scaled-down
profile of the same chip, sharing what it can:

- **Shared, compiled by both gcc and Watcom (so plain C89):** the tables, frame and
  control decoding, frame to parameters, and the constants.
- **Its own:** the PolyBLEP source, the output paths, the timing.
- **Gate:** the same frames must give identical parameters. Audio can only be compared
  by measurement, since the source differs on purpose.

## Order of work

1. **One reference.** `pcf8200_core.py` is the audio core for both the library and the
   add-on, with the constants tagged by source. The track builders stay separate for now:
   the add-on ignores FS on purpose. Then the new noise generator, with one A/B for Tomi's ear.
2. **The C core and its gate.** `csrc/pcf8200.c`, tested by `tests/test_native.py` on seeded
   random sessions, x64 and x86, every option: phase and noise state exact, audio within
   1e-9, PCM identical. `make_core` chooses C when the library is there; `PCF8200_BACKEND`
   forces either. Frames too: `pcf8200_tracker` with tables generated by `csrc/gen_tables.py`,
   exactly equal to both Python track builders, its `honour_fs` switch choosing between them.
3. **The wheel.** `build_wheel.py` and `.github/workflows/wheels.yml`: Windows 64- and 32-bit,
   Linux x86-64 and arm64 from Debian 11, and a pure wheel with no C. Each platform runs the suite
   on C, then `test_wheel.py` installs its wheel into a clean environment and compares PCM with
   the reference inside it. CI posts them to an untagged draft release.
4. **TALKHUN without Unicorn.** Done early, because it was the one real unknown:
   `talkhun_emu/csrc/talkhun_host.c` runs TALKHUN0 on MAME's 8086, 13 times faster. Against
   Unicorn, over 720 lines of the archive's own text, every byte value and random ESC
   settings: 395,958 frames, none different.
5. **The NVDA add-on on C.** Drops numpy, scipy and Unicorn. Ships only after Tomi has heard it.
6. **SAPI, Linux, and BRAISPK's shared header.** SAPI: an emulated voice and a TTS.dll voice.

Real-box findings are table changes at any step. Keep a set of real-box recordings as a
hold-out that nothing is tuned on, as ssi263-speech does with its hold-out set.

## Questions to settle

- MAME's core is copied from ssi263-speech with its pin, into `talkhun_emu/csrc/cpu/`, so this
  repository stands alone. A fix there has to be carried over by hand.
- `talkhun_emu/pcf8200.py` has the package's name, which is why the two suites can't run in
  one pytest and why `chip_synth` takes only `pcf8200_core`. Rename it when the track builders
  merge.
- `PCF8200.tracks()` starts from the last pitch and speed given, not the first, so frames ahead
  of those commands decode wrongly. The chip would apply them in order. Fix it with the merge.
- A sample rate setting for the add-on: the C resampler carries it, and the real box shows
  what, if anything, sits above 5 kHz. Brightness itself is the `[ear]` low-pass, to be set
  from the box, probably as separate voiced and noise cutoffs as BRAISPK has.
- Speed on small devices: the C core spends its time in `sin`, about 40 calls a sample at a
  low pitch. It runs some 80 times real time here. A recurrence would be far cheaper but
  rounds differently, so it needs the gate's tolerance checked first.
- `TALKHUN0.COM` in the repository waits on Arató's answer. The add-on bundles it already.
- The TTS.dll voice is 32-bit, so a 64-bit SAPI host needs a plan for it.
