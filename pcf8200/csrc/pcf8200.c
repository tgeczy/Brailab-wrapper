/* pcf8200.c -- the PCF8200 audio core.  See pcf8200.h and pcf8200_core.py.
 *
 * Every expression keeps the order of operations of the Python reference, so
 * build with -ffp-contract=off, and with SSE2 doubles on 32-bit x86.
 */
#include <math.h>
#include <string.h>

#include "pcf8200.h"

#define PI 3.141592653589793

int pcf8200_core_size(void)
{
    return (int)sizeof(pcf8200_core);
}

int pcf8200_init(pcf8200_core *c, int nf, const pcf8200_params *p)
{
    if (nf < 1 || nf > PCF8200_MAX_FORMANTS)
        return -1;
    memset(c, 0, sizeof *c);
    c->p = *p;
    c->nf = nf;
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

void pcf8200_run(pcf8200_core *c, const double *amp, const double *pitch,
                 const uint8_t *voiced, const double *fc, const double *bw,
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
        double p = pitch[s], src, noise, wrapped, v;

        if (p < q->pitch_min_hz)
            p = q->pitch_min_hz;
        if (p > q->pitch_max_hz)
            p = q->pitch_max_hz;

        /* both sources run on every sample, whichever one is heard */
        c->phase += p / rate;
        wrapped = c->phase - floor(c->phase);
        src = sawtooth(wrapped, p, fade_width);
        if (q->source_tilt_hz != 0.0) {
            c->ty = (1.0 - c->tilt) * src + c->tilt * c->ty;
            src = c->ty;
        }
        noise = next_noise(c, noise_scale, q->noise_gain);
        v = (voiced[s] ? src : noise) * amp[s];

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

double pcf8200_phase(const pcf8200_core *c)
{
    return c->phase;
}

uint32_t pcf8200_noise_state(const pcf8200_core *c)
{
    return c->noise;
}
