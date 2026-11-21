/* pcf8200.c -- the PCF8200 audio core.  See pcf8200.h and pcf8200_core.py.
 *
 * Every expression keeps the order of operations of the Python reference, so
 * build with -ffp-contract=off, and with SSE2 doubles on 32-bit x86.
 */
#include <math.h>
#include <string.h>

#include "pcf8200.h"
#include "pcf8200_tables.h"

#define PI 3.141592653589793

int pcf8200_core_size(void)
{
    return (int)sizeof(pcf8200_core);
}

int pcf8200_init(pcf8200_core *c, int nf, const pcf8200_params *p)
{
    int i;
    if (nf < 1 || nf > PCF8200_MAX_FORMANTS)
        return -1;
    memset(c, 0, sizeof *c);
    c->p = *p;
    c->nf = nf;
    for (i = 0; i < PCF8200_NOISE_POLES; i++)
        if (p->noise_lowpass_hz[i] != 0.0)
            c->na[c->nn++] = exp(-2.0 * PI * p->noise_lowpass_hz[i] / p->rate);
    if (p->source_tilt_hz != 0.0)
        c->tilt = exp(-2.0 * PI * p->source_tilt_hz / p->rate);
    if (p->highpass_hz != 0.0)
        c->ha = exp(-2.0 * PI * p->highpass_hz / p->rate);
    c->noise = (uint32_t)p->seed * 2654435761u + 1u;
    if (c->noise == 0)
        c->noise = 1;
    return 0;
}

/* One value of the band-limited sawtooth, before the tilt.  A harmonic at or past
 * the band edge would add an exact zero, so the sum stops there. */
static double sawtooth(double phase, double p, double fade_width)
{
    const double edge = 5000.0;
    double sum = 0.0;
    int k;
    for (k = 1;; k++) {
        double w = (edge - p * k) / fade_width;
        if (w <= 0.0)
            break;
        if (w > 1.0)
            w = 1.0;
        w = w * w * (3.0 - 2.0 * w);
        sum += sin(2.0 * PI * phase * k) * (w / k);
    }
    return sum * -(2.0 / PI);
}

/* The voiced source at pitch p (not negative), before the tilt.  The chip's own is a
 * counter stepped by the pitch once a sample and read as it stands: a sawtooth with
 * nothing done against aliasing, which is what a real one sounds like once its pitch
 * has walked far from speech (pcf8200_core.py, CLEAN_FROM_HZ, has the measurement).
 * Between `from` and `to` this is the band-limited sawtooth the voice was tuned with;
 * below half of `from` and above twice `to` it is the plain counter; in between the
 * two are mixed in a straight line.  A pitch of zero never reaches the harmonic sum,
 * which would not end. */
static double voiced_source(double wrapped, double p, double fade_width, double from, double to)
{
    const double plain = 2.0 * wrapped - 1.0;
    const double half = from * 0.5, top = to * 2.0;
    double mix;
    if (p <= half)
        mix = 0.0;
    else if (p < from)
        mix = (p - half) / half;
    else if (p <= to)
        mix = 1.0;
    else if (p < top)
        mix = (top - p) / to;
    else
        mix = 0.0;
    if (mix > 0.0)
        return mix * sawtooth(wrapped, p, fade_width) + (1.0 - mix) * plain;
    return plain;
}

static double next_noise(pcf8200_core *c, double scale, double gain)
{
    uint32_t x = c->noise;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    c->noise = x;
    return (double)x * scale - gain;
}

static double soft_knee(double v, double knee)
{
    double a = fabs(v), room;
    if (knee == 0.0 || knee >= 1.0 || !(a > knee))
        return v;
    room = 1.0 - knee;
    a = knee + room * tanh((a - knee) / room);
    return v < 0.0 ? -a : a;
}

void pcf8200_run(pcf8200_core *c, const double *voice_amp, const double *noise_amp,
                 const double *pitch, const double *fc, const double *bw,
                 int n, double *out)
{
    const pcf8200_params *q = &c->p;
    const double rate = q->rate;
    const double fade_width = rate * 0.5 * q->harmonic_fade;
    const double noise_scale = 2.0 * q->noise_gain / 4294967296.0;
    const double *l = q->lp_sos;
    const int nf = c->nf;
    int s, i;

    for (s = 0; s < n; s++) {
        /* no floor and no ceiling; a negative pitch sounds as the positive one */
        /* a pitch that is not a number (NaN, infinite) is silence for that sample: the phase
         * is a running sum, and one NaN in it was every sample after it (#43) */
        double p = isfinite(pitch[s]) ? fabs(pitch[s]) : 0.0, src, noise, wrapped, v;

        /* both sources run on every sample, whichever one is heard */
        c->phase += p / rate;
        wrapped = c->phase - floor(c->phase);
        src = voiced_source(wrapped, p, fade_width, q->clean_from_hz, q->clean_to_hz);
        if (q->source_tilt_hz != 0.0) {
            c->ty = (1.0 - c->tilt) * src + c->tilt * c->ty;
            src = c->ty;
        }
        noise = next_noise(c, noise_scale, q->noise_gain);
        for (i = 0; i < c->nn; i++) {
            c->nz[i] = (1.0 - c->na[i]) * noise + c->na[i] * c->nz[i];
            noise = c->nz[i];
        }
        v = src * voice_amp[s] + noise * noise_amp[s];

        for (i = 0; i < nf; i++) {
            double bc = exp(-PI * bw[i * n + s] / rate);
            double fcos = 2.0 * cos(2.0 * PI * fc[i * n + s] / rate);
            double yn = v + (bc * fcos) * c->y1[i] + (-(bc * bc)) * c->y2[i];
            c->y2[i] = c->y1[i];
            c->y1[i] = yn;
            v = yn;
        }

        if (q->lowpass != 0.0) {
            double o = l[0] * v + c->lz[0];
            c->lz[0] = l[1] * v - l[3] * o + c->lz[1];
            c->lz[1] = l[2] * v - l[4] * o;
            v = l[5] * o + c->lz[2];
            c->lz[2] = l[6] * o - l[8] * v + c->lz[3];
            c->lz[3] = l[7] * o - l[9] * v;
        }

        if (q->highpass_hz != 0.0) {
            const double ha = c->ha;
            c->hy[0] = ha * (c->hy[0] + v - c->hx[0]);
            c->hx[0] = v;
            c->hy[1] = ha * (c->hy[1] + c->hy[0] - c->hx[1]);
            c->hx[1] = c->hy[0];
            c->hy[2] = ha * (c->hy[2] + c->hy[1] - c->hx[2]);
            c->hx[2] = c->hy[1];
            v = c->hy[2];
        }

        out[s] = soft_knee(v * q->gain, q->knee);
    }
}

/* ---- frames ------------------------------------------------------------ */

#define STD_SAMPLES 128     /* the 12.8 ms standard frame at 10 kHz */
#define MIN_SAMPLES 16      /* the shortest frame with the FS bits ignored */

int pcf8200_tracker_size(void)
{
    return (int)sizeof(pcf8200_tracker);
}

void pcf8200_tracker_init(pcf8200_tracker *t, const pcf8200_params *p, int female,
                          int honour_fs, int flat_pitch, double time_scale, int pitch_byte)
{
    memset(t, 0, sizeof *t);
    t->rate = p->rate;
    t->female = female;
    t->nf = female ? 4 : 5;
    t->honour_fs = honour_fs;
    t->flat_pitch = flat_pitch;
    /* a frame's length is converted to int: a time_scale that is not a number, or one that
     * would overflow it, was undefined behaviour (#43).  Kept within 1/1000 to 1000. */
    t->time_scale = !isfinite(time_scale) || time_scale <= 0.0 ? 1.0
                  : time_scale < 1e-3 ? 1e-3 : time_scale > 1e3 ? 1e3 : time_scale;
    pcf8200_tracker_pitch(t, pitch_byte);
}

void pcf8200_tracker_pitch(pcf8200_tracker *t, int pitch_byte)
{
    /* the chip's pitch register is one byte, as the Python stream has it (#41) */
    t->anchor = (pitch_byte & 0xFF) * PCF8200_PITCH_HZ_PER_UNIT;
    t->pitch = t->anchor;
}

void pcf8200_tracker_speed(pcf8200_tracker *t, int fs)
{
    t->fs = fs & 3;
}

static int field_fd(const uint8_t *f)
{
    return (((f[2] >> 7) & 1) << 1) | ((f[3] >> 7) & 1);
}

int pcf8200_tracker_length(const pcf8200_tracker *t, const uint8_t *f)
{
    const int mult = PCF8200_FD_MULT[field_fd(f)];
    int n;
    if (t->honour_fs) {
        int std = (int)rint(PCF8200_FS_MS[t->fs] * 0.001 * t->rate * t->time_scale);
        if (std < 1)
            std = 1;
        n = (int)rint((double)(std * mult));
        return n < 1 ? 1 : n;
    }
    n = (int)rint(STD_SAMPLES * mult * t->time_scale);
    return n < MIN_SAMPLES ? MIN_SAMPLES : n;
}

/* One source's amplitude across a frame: fade() in pcf8200_core.py. */
static double fade(double a, double b, double frac)
{
    return a + (b - a) * frac;
}

int pcf8200_tracker_frame(pcf8200_tracker *t, const uint8_t *f, double *voice_amp,
                          double *noise_amp, double *pitch, double *fc, double *bw, int stride)
{
    const int f1 = f[0] & 0x1F, b1 = (f[0] >> 5) & 7;
    const int pi = f[1] & 0x1F, b5 = (f[1] >> 5) & 3, f5 = (f[1] >> 7) & 1;
    const int am = f[2] & 0x0F, f3 = (f[2] >> 4) & 7;
    const int f2 = f[3] & 0x1F, b3 = (f[3] >> 5) & 3;
    const int b2 = f[4] & 7, f4 = (f[4] >> 3) & 7, b4 = (f[4] >> 6) & 3;
    const int nf = t->nf, n = pcf8200_tracker_length(t, f);
    const double cur_amp = PCF8200_AMPL[am];
    const int cur_noise = pi == PCF8200_PI_NOISE;
    double cur_fc[PCF8200_MAX_FORMANTS], cur_bw[PCF8200_MAX_FORMANTS], target;
    double pv, pn, cv, cn;
    int i, s;

    if (t->female) {
        cur_fc[0] = PCF8200_FEMALE_F[0][f1];  cur_bw[0] = PCF8200_FEMALE_B[0][b1];
        cur_fc[1] = PCF8200_FEMALE_F[1][f2];  cur_bw[1] = PCF8200_FEMALE_B[1][b2];
        cur_fc[2] = PCF8200_FEMALE_F[2][f3];  cur_bw[2] = PCF8200_FEMALE_B[2][b3];
        cur_fc[3] = PCF8200_FEMALE_F[3][f4];  cur_bw[3] = PCF8200_FEMALE_B[3][b4];
    } else {
        cur_fc[0] = PCF8200_MALE_F[0][f1];  cur_bw[0] = PCF8200_MALE_B[0][b1];
        cur_fc[1] = PCF8200_MALE_F[1][f2];  cur_bw[1] = PCF8200_MALE_B[1][b2];
        cur_fc[2] = PCF8200_MALE_F[2][f3];  cur_bw[2] = PCF8200_MALE_B[2][b3];
        cur_fc[3] = PCF8200_MALE_F[3][f4];  cur_bw[3] = PCF8200_MALE_B[3][b4];
        cur_fc[4] = PCF8200_MALE_F[4][f5];  cur_bw[4] = PCF8200_MALE_B[4][b5];
    }
    if (!t->have_prev) {
        t->prev_amp = cur_amp;
        t->prev_noise = cur_noise;
        for (i = 0; i < nf; i++) {
            t->prev_fc[i] = cur_fc[i];
            t->prev_bw[i] = cur_bw[i];
        }
        t->have_prev = 1;
    }

    if (t->flat_pitch) {
        target = t->anchor;
    } else {
        /* the chip's pitch register has no floor and no ceiling */
        target = t->pitch + PCF8200_PI[pi] * PCF8200_FD_MULT[field_fd(f)];
    }

    pv = t->prev_noise ? 0.0 : t->prev_amp;
    pn = t->prev_noise ? t->prev_amp : 0.0;
    cv = cur_noise ? 0.0 : cur_amp;
    cn = cur_noise ? cur_amp : 0.0;
    for (s = 0; s < n; s++) {
        const double frac = (s + 0.5) / n;
        voice_amp[s] = fade(pv, cv, frac);
        noise_amp[s] = fade(pn, cn, frac);
        pitch[s] = t->pitch + (target - t->pitch) * frac;
        for (i = 0; i < nf; i++) {
            fc[i * stride + s] = t->prev_fc[i] + (cur_fc[i] - t->prev_fc[i]) * frac;
            bw[i * stride + s] = t->prev_bw[i] + (cur_bw[i] - t->prev_bw[i]) * frac;
        }
    }

    t->pitch = target;
    t->prev_amp = cur_amp;
    t->prev_noise = cur_noise;
    for (i = 0; i < nf; i++) {
        t->prev_fc[i] = cur_fc[i];
        t->prev_bw[i] = cur_bw[i];
    }
    return n;
}

double pcf8200_phase(const pcf8200_core *c)
{
    return c->phase;
}

uint32_t pcf8200_noise_state(const pcf8200_core *c)
{
    return c->noise;
}
