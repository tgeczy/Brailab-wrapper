/* klatt.h -- a cascade/parallel formant synthesizer.
 *
 * Written from two papers:
 *   K80: D. H. Klatt, "Software for a cascade/parallel formant synthesizer",
 *        J. Acoust. Soc. Am. 67(3), 971-995 (1980).
 *   K90: D. H. Klatt and L. C. Klatt, "Analysis, synthesis, and perception of
 *        voice quality variations among female and male talkers",
 *        J. Acoust. Soc. Am. 87(2), 820-857 (1990).
 *
 * Control parameters in, audio out, in any block size.  See ../SPEC.md.
 * MIT, see the notice in klatt.c.
 */
#ifndef KLATT_H
#define KLATT_H

#ifdef _WIN32
#define KLATT_API __declspec(dllexport)
#else
#define KLATT_API __attribute__((visibility("default")))
#endif

#define KLATT_FORMANTS 6

/* Both structs are all doubles, in this order: a caller in another language
 * mirrors them as flat arrays. */

/* What stays fixed for the life of a state (K80 Table I, K90 Table XI). */
typedef struct {
    double sample_rate;        /* SR.  10000; 5000 to 20000 */
    double samples_per_frame;  /* NWS.  50; 1 to 200: the span AF and AH are interpolated over */
    double n_cascade;          /* NF.  5; 1 to 6 */
    double source;             /* SS.  2; 1 = K80 impulsive, 2 = KLGLOTT88 */
    double all_parallel;       /* SW / CP.  0 */
    double tap;                /* OS.  0 = the output; 1 = the voicing source as it
                                  enters the tract; 2 = the aspiration noise as it
                                  enters the tract; 3 = the frication noise as it
                                  enters the parallel branch */
    double seed;               /* RS.  8; a 32-bit unsigned value */
    double gain_db;            /* G0.  47; 0 to 80 */
} klatt_config;

/* What may change from frame to frame (K80 Table I, K90 Table XII).  The source
 * parameters and the amplitudes are held to the papers' ranges: F0 0 to 500 Hz
 * (a voiced F0 no lower than 40), amplitudes 0 to 80 dB, OQ 10 to 99, TL 0 to 41,
 * FL 0 to 100.  Formants and bandwidths are not held to the papers' tables, which
 * are one talker's English: any frequency from 0 to SR/2 and any bandwidth from
 * 5 Hz to SR/2 gives that resonator. */
typedef struct {
    double f0;                 /* Hz.  100; 0 = no voicing */
    double av, avs, ah, af;    /* dB.  60, 0, 0, 0; 0 = off.  AVS: K80's source only */
    double oq;                 /* percent.  50.  KLGLOTT88 only */
    double tl;                 /* dB down at 3 kHz.  0 */
    double fl;                 /* percent.  0 */
    double f[KLATT_FORMANTS];  /* F1..F6, Hz.  500 1500 2500 3250 3700 4900 */
    double b[KLATT_FORMANTS];  /* B1..B6, Hz.  60 90 150 200 200 1000 */
    double fnp, bnp, fnz, bnz; /* Hz.  280 90 280 90 */
    double a[KLATT_FORMANTS];  /* A1..A6, dB.  0 = off */
    double an, ab;             /* dB.  0 = off */
} klatt_frame;

#ifdef __cplusplus
extern "C" {
#endif

/* The caller owns the state: a block of klatt_state_size() bytes, aligned for a
 * double.  klatt_init clears it. */
KLATT_API int klatt_state_size(void);

KLATT_API void klatt_config_defaults(klatt_config *c);
KLATT_API void klatt_frame_defaults(klatt_frame *f);

/* Returns 0, or -1 for a config outside the papers' ranges (the state is then
 * unusable).  The default frame is in force until klatt_set_frame. */
KLATT_API int klatt_init(void *state, const klatt_config *c);

/* In force from the next sample.  Values outside a parameter's range (above) are
 * held to it.  Formants, bandwidths and the parallel amplitudes change at once;
 * AF and AH move to their new values over samples_per_frame samples; F0, AV,
 * AVS, OQ, TL and FL wait for the next glottal opening. */
KLATT_API void klatt_set_frame(void *state, const klatt_frame *f);

/* The next n samples, in K80's units: a strong vowel comes near
 * klatt_full_scale().  Nothing is truncated there; the output is held at 100
 * times that, so it is bounded whatever the parameters.  The taps are in the
 * same units. */
KLATT_API void klatt_run(void *state, int n, double *out);

/* The level a full-scale output reaches: K80 wrote 16-bit samples, +-32767. */
KLATT_API double klatt_full_scale(void);

/* K80 Eq. (2): the constants A, B, C of the digital resonator at f Hz, bw Hz wide.
 * Nothing is held to a range here. */
KLATT_API void klatt_resonator(double f, double bw, double sample_rate, double abc[3]);

#ifdef __cplusplus
}
#endif

#endif
