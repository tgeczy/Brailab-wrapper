# klatt: a cascade/parallel formant synthesizer in C

A small, general Klatt synthesizer: per-frame control parameters in, audio out.
It is written from two published papers:

- D. H. Klatt, "Software for a cascade/parallel formant synthesizer",
  J. Acoust. Soc. Am. 67(3), 1980 ("K80").
- D. H. Klatt and L. C. Klatt, "Analysis, synthesis, and perception of voice
  quality variations among female and male talkers", J. Acoust. Soc. Am. 87(2),
  1990 ("K90"): the KLGLOTT88 voicing source and the KLSYN88 parameter set.

Where the two differ, K90 wins for what it defines (the source, the parameter
defaults); K80 supplies the rest (resonators, branches, amplitude scaling).

## What it models

Sources, in K80/K90's terms:

- **Voicing**, chosen by the source switch SS:
  - SS = 1: K80's impulsive source: an impulse train through the glottal
    low-pass resonator RGP and antiresonator RGZ, with the quasi-sinusoidal
    branch (RGS, amplitude AVS).
  - SS = 2 (default): K90's KLGLOTT88: during the open phase the glottal flow
    is Ug(t) = a t^2 - b t^3, lasting OQ percent of the period, with a and b
    set by the amplitude of voicing and the open period; then the tilt
    low-pass, set so the source is TL dB down at 3 kHz.  The radiation
    characteristic is folded into the source, as K90 says.
  - The period is computed from F0 and quantized to a quarter of a sample: the
    voicing source runs at four times the sampling rate and is low-pass
    filtered and downsampled (K90, footnote 17).  Flutter FL changes F0 by
    K90's Eq. (1).
  - A change of F0, AV, OQ or TL takes effect at the next glottal opening, not
    in the middle of a pulse.
- **Aspiration** (AH) and **frication** (AF) noise from one seeded pseudorandom
  generator, written out in the code so every platform gives the same samples;
  shaped and, when voicing is on, amplitude-modulated as K80 describes.

Vocal tract, as K80's block diagram:

- **Cascade branch** for voicing and aspiration: NF formant resonators (1 to 6),
  the nasal pole (FNP, BNP) and the nasal zero (FNZ, BNZ).
- **Parallel branch** for frication: resonators F2 to F6 with amplitudes A2 to
  A6, the bypass path AB, alternating signs; and, with the cascade/parallel
  switch set to all-parallel, voicing through A1 and AN too.  The parallel
  formants may have bandwidths of their own (K90 Table XII's B2F to B6F): a
  noise-excited formant is wider than the same formant in the cascade.  Left at
  0, a parallel formant has its cascade bandwidth, as in K80.
- Resonators are K80's: y(n) = A x(n) + B y(n-1) + C y(n-2) with
  C = -exp(-2 pi BW T), B = 2 exp(-pi BW T) cos(2 pi F T), A = 1 - B - C; an
  antiresonator is its inverse.
- Amplitudes in dB become linear factors with K80's scale factors and overall
  gain G0.  AF and AH are interpolated linearly across a frame; K80's burst
  rule for a jump in AF is kept.

Not included: K90's modified LF source (SS = 3), diplophonia (DI), the tracheal
pole-zero pair and the pitch-synchronous F1/B1 changes (DF1, DB1).

## Interface (csrc/klatt.h)

All fields are `double`, in this order, so a caller in another language can
mirror the two structs as flat arrays.

```c
typedef struct {
    double sample_rate;        /* SR.  10000 */
    double samples_per_frame;  /* NWS.  50: the span AF and AH are interpolated over */
    double n_cascade;          /* NF.  5; 1 to 6 */
    double source;             /* SS.  2; 1 = K80 impulsive, 2 = KLGLOTT88 */
    double all_parallel;       /* SW / CP.  0 */
    double tap;                /* OS.  0 = the output; 1 = the voicing source as it
                                  enters the tract; 2 = the aspiration noise as it
                                  enters the tract; 3 = the frication noise as it
                                  enters the parallel branch */
    double seed;               /* RS.  8; a 32-bit unsigned value */
    double gain_db;            /* G0.  47 */
} klatt_config;

typedef struct {
    double f0;                 /* Hz.  100; 0 = no voicing */
    double av, avs, ah, af;    /* dB.  60, 0, 0, 0 */
    double oq;                 /* percent.  50 */
    double tl;                 /* dB down at 3 kHz.  0 */
    double fl;                 /* percent.  0 */
    double f[6];               /* F1..F6, Hz.  500 1500 2500 3250 3700 4900 */
    double b[6];               /* B1..B6, Hz.  60 90 150 200 200 1000 */
    double fnp, bnp, fnz, bnz; /* Hz.  280 90 280 90 */
    double a[6];               /* A1..A6, dB.  0 */
    double an, ab;             /* dB.  0 */
    double bp[6];              /* the parallel formants' own bandwidths, Hz.  0 = the cascade's */
} klatt_frame;

int    klatt_state_size(void);
void   klatt_config_defaults(klatt_config *c);
void   klatt_frame_defaults(klatt_frame *f);
int    klatt_init(void *state, const klatt_config *c);    /* 0, or -1 for a bad config */
void   klatt_set_frame(void *state, const klatt_frame *f);/* in force from the next sample */
void   klatt_run(void *state, int n, double *out);         /* the next n samples */
double klatt_full_scale(void);                             /* the level a full-scale output reaches */
void   klatt_resonator(double f, double bw, double sample_rate, double abc[3]);
```

Requirements on the implementation:

- C99, one file `csrc/klatt.c` and `csrc/klatt.h`, no dependency but `<math.h>`,
  `<string.h>`, `<stdint.h>`.  It must build with
  `-O2 -std=c99 -ffp-contract=off -Wall -Wextra` without warnings, as a shared
  library (`__declspec(dllexport)` on Windows, default visibility elsewhere).
- No global state: everything lives in the caller's `state` block, which
  `klatt_init` clears.  Several states can run at once.
- Any split of the same samples into `klatt_run` calls gives the same output,
  bit for bit; `klatt_set_frame` may come at any sample.
- Nothing a caller passes may produce NaN or infinity.  The source parameters
  and the amplitudes are held to the ranges the papers give.  Formants and
  bandwidths are not: the papers' tables are one talker's English, and another
  voice's frames go lower and higher.  A frequency is held to 0 .. SR/2 and a
  bandwidth to 5 Hz .. SR/2, and inside that a resonator is the resonator of
  K80's Eq. (2), whatever its number.
- With AV, AVS, AH and AF all 0 from the start, the output is exactly 0.
- The same config and frames give the same samples on every machine whose
  exp, cos, sin and sqrt agree (IEEE doubles, one fixed arithmetic order); the
  noise generator is integer, so the noise itself is the same everywhere.

The tests in `tests/test_klatt.py` are the acceptance: each states what the
papers predict and measures it on the built library.
