# klatt

A cascade/parallel formant synthesizer in C99: Klatt's, as two papers describe it.

- D. H. Klatt, "Software for a cascade/parallel formant synthesizer",
  J. Acoust. Soc. Am. 67(3), 971-995 (1980).
- D. H. Klatt and L. C. Klatt, "Analysis, synthesis, and perception of voice
  quality variations among female and male talkers", J. Acoust. Soc. Am. 87(2),
  820-857 (1990): the KLGLOTT88 voicing source.

Control parameters go in a frame at a time (F0, amplitudes in dB, six formants
and bandwidths, the nasal pole and zero, the parallel amplitudes, open quotient,
tilt, flutter); audio comes out, in any block size. One C file, no dependency
beyond the C library, MIT. `SPEC.md` says exactly what is modelled and what is
left out; `csrc/klatt.c` cites the passage each part follows and marks what the
papers leave open.

## Build

```
python klatt/csrc/build_native.py
python -m pytest klatt/tests
```

On Windows this wants w64devkit (`W64DEVKIT`, `W64DEVKIT_X86`), as `pcf8200` does;
on Linux, any C compiler. The library lands in `klatt/_bin/`.

## Use

From C: `klatt_init` on a block of `klatt_state_size()` bytes, `klatt_set_frame`
whenever the parameters change, `klatt_run` for samples (see `csrc/klatt.h`).

From Python, through ctypes:

```python
from klatt import klatt_native as kn

s = kn.Synth()                                   # 10 kHz, KLGLOTT88 source
s.frame(f0=110, f=[700, 1220, 2600, 3250, 3700, 4900],
        b=[130, 70, 160, 200, 200, 1000])        # the 1980 paper's [a]
audio = s.run(5000) / kn.full_scale()            # half a second
s.frame(av=0, f0=0, af=60, a=[0, 0, 0, 0, 0, 52])  # and its [s]
audio = s.run(1500) / kn.full_scale()
```

The output is not truncated at full scale: clip it when you write 16-bit samples.

## What the tests are

`tests/test_klatt.py` checks what the papers predict, on the built library:
a resonator's response when a formant or bandwidth moves, F0 to a quarter of a
sample, open quotient, tilt in dB at 3 kHz, the flutter formula, amplitudes in
dB, which source goes through which branch, and that any split of a run into
calls gives the same samples. There are no stored renderings.
