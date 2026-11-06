/* pcf8200.h -- the PCF8200 audio core in plain C.
 *
 * The same model as pcf8200_core.py, which stays the reference: per-sample
 * parameters in, audio out, in any block size.  The tests hold the two together.
 * MIT, see ../LICENSE.
 */
#ifndef PCF8200_H
#define PCF8200_H

#include <stdint.h>

#ifdef _WIN32
#define PCF8200_API __declspec(dllexport)
#else
#define PCF8200_API __attribute__((visibility("default")))
#endif

#define PCF8200_MAX_FORMANTS 5
#define PCF8200_HIGHPASS_POLES 3

/* All doubles, in this order: the Python side and pcf8200_defaults.h both write
 * this as one flat array. */
typedef struct {
    double rate;            /* internal speech rate, Hz */
    double source_tilt_hz;  /* 0 = no glottal tilt */
    double noise_gain;
    double pitch_min_hz;
    double pitch_max_hz;
    double harmonic_fade;
    double lowpass;         /* non-zero runs lp_sos in the loop */
    double lp_sos[10];      /* two sections: b0 b1 b2 a1 a2 */
    double highpass_hz;     /* 0 = none */
    double gain;
    double knee;            /* 0 = none */
    double seed;            /* a 32-bit unsigned value */
} pcf8200_params;

typedef struct {
    pcf8200_params p;
    int nf;
    double tilt;            /* the tilt pole, when source_tilt_hz is set */
    double ha;              /* the high-pass pole, when highpass_hz is set */
    double phase;           /* unwrapped: the running sum of pitch / rate */
    double ty;
    double y1[PCF8200_MAX_FORMANTS], y2[PCF8200_MAX_FORMANTS];
    double lz[4];
    double hx[PCF8200_HIGHPASS_POLES], hy[PCF8200_HIGHPASS_POLES];
    uint32_t noise;
} pcf8200_core;

#ifdef __cplusplus
extern "C" {
#endif

PCF8200_API int pcf8200_core_size(void);

/* Returns 0, or -1 if nf is out of range. */
PCF8200_API int pcf8200_init(pcf8200_core *c, int nf, const pcf8200_params *p);

/* Audio for the next n samples.  amp, pitch (Hz), voiced: n values each.  fc, bw:
 * nf rows of n values, in hertz.  out: n values. */
PCF8200_API void pcf8200_run(pcf8200_core *c, const double *amp, const double *pitch,
                             const uint8_t *voiced, const double *fc, const double *bw,
                             int n, double *out);

/* For the tests: the two states that must match the reference exactly. */
PCF8200_API double pcf8200_phase(const pcf8200_core *c);
PCF8200_API uint32_t pcf8200_noise_state(const pcf8200_core *c);

#ifdef __cplusplus
}
#endif

#endif
