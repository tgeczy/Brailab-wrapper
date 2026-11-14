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
#define PCF8200_NOISE_POLES 3

/* All doubles, in this order: the Python side and pcf8200_defaults.h both write
 * this as one flat array. */
typedef struct {
    double rate;            /* internal speech rate, Hz */
    double source_tilt_hz;  /* 0 = no glottal tilt */
    double noise_gain;
    double noise_lowpass_hz[PCF8200_NOISE_POLES];   /* one-pole low-passes on the noise; 0 = unused */
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
    double na[PCF8200_NOISE_POLES], nz[PCF8200_NOISE_POLES];   /* the noise low-passes in use */
    int nn;                 /* how many of them */
    uint32_t noise;
} pcf8200_core;

/* Turns the chip's 5-byte frames into the per-sample parameters pcf8200_run takes:
 * each frame glides from the one before it. */
typedef struct {
    double rate, pitch_min_hz, pitch_max_hz;
    int female;             /* the four-formant table */
    int nf;
    int honour_fs;          /* 0: every standard frame is 12.8 ms, whatever the FS bits say */
    int flat_pitch;         /* hold the start pitch: no intonation */
    int fs;
    double time_scale;
    double anchor, pitch;
    int have_prev;
    double prev_amp, prev_fc[PCF8200_MAX_FORMANTS], prev_bw[PCF8200_MAX_FORMANTS];
} pcf8200_tracker;

/* The largest frame: 17.6 ms at FD x5, in samples at 1:1 time scale. */
#define PCF8200_MAX_FRAME_SAMPLES 880

#ifdef __cplusplus
extern "C" {
#endif

PCF8200_API int pcf8200_core_size(void);
PCF8200_API int pcf8200_tracker_size(void);

PCF8200_API void pcf8200_tracker_init(pcf8200_tracker *t, const pcf8200_params *p, int female,
                                      int honour_fs, int flat_pitch, double time_scale,
                                      int pitch_byte);
/* The chip's start-pitch command, and the FS bits of a control write. */
PCF8200_API void pcf8200_tracker_pitch(pcf8200_tracker *t, int pitch_byte);
PCF8200_API void pcf8200_tracker_speed(pcf8200_tracker *t, int fs);
/* How many samples this frame will give. */
PCF8200_API int pcf8200_tracker_length(const pcf8200_tracker *t, const uint8_t *frame);
/* Write the frame's parameters and return their length.  amp, pitch, voiced: one value
 * per sample.  fc, bw: nf rows, each `stride` values apart. */
PCF8200_API int pcf8200_tracker_frame(pcf8200_tracker *t, const uint8_t *frame, double *amp,
                                      double *pitch, uint8_t *voiced, double *fc, double *bw,
                                      int stride);

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
