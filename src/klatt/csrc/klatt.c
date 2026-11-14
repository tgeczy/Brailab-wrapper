/* klatt.c -- a cascade/parallel formant synthesizer.  See klatt.h and ../SPEC.md.
 *
 * MIT License
 *
 * Copyright (c) 2026 Tamás Géczy (tgeczy)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 * Based on:
 *   K80: D. H. Klatt, "Software for a cascade/parallel formant synthesizer",
 *        J. Acoust. Soc. Am. 67(3), 971-995 (1980).
 *   K90: D. H. Klatt and L. C. Klatt, "Analysis, synthesis, and perception of
 *        voice quality variations among female and male talkers",
 *        J. Acoust. Soc. Am. 87(2), 820-857 (1990).
 *
 * The signal, one output sample at a time:
 *
 *   glottal pulses at 4 x SR -> tilt low-pass -> decimator -+
 *     (K80's impulses, or K90's a t^2 - b t^3)              |  K80's glottal
 *                                                           v  filters, SS = 1
 *   noise -> modulator -+-> x AH ------------------------> (+) -> cascade ----+
 *                       |                                                     v
 *                       +-> x AF -> parallel F2..F6 and the bypass --------> (+) -> out
 *
 * Every sum is written in one fixed order, so build with -ffp-contract=off, and
 * with SSE2 doubles on 32-bit x86: then a run is the same however it is cut into
 * calls, and the same on every machine whose exp, cos, sin and sqrt agree.
 */
#include <math.h>
#include <stdint.h>
#include <string.h>

#include "klatt.h"

#define PI 3.141592653589793
#define LN10 2.302585092994046

#define SOURCE_IMPULSIVE 1
#define SOURCE_KLGLOTT88 2
#define TAP_OUTPUT 0
#define TAP_VOICING 1
#define TAP_ASPIRATION 2
#define TAP_FRICATION 3

/* K80 wrote 16-bit samples: the sum of the two branches times 170, truncated at
 * +-32767 (the output stage of its COEWAV listing).  The scale is kept.  The
 * truncation is left to whoever turns these doubles into 16-bit samples: here
 * the output is held only at 40 dB above full scale (my choice), so that it stays
 * linear past full scale and bounded whatever the parameters. */
#define FULL_SCALE 32767.0
#define OUTPUT_SCALE 170.0
#define OUTPUT_LIMIT (100.0 * FULL_SCALE)

/* The scale factors, in dB, that K80 adds to each amplitude control (the table in
 * its PARCOE listing; the text gives none).  The four sources also get G0. */
#define DB_AV (-72.0)
#define DB_AVS (-44.0)
#define DB_AH (-102.0)
#define DB_AF (-72.0)
#define DB_AN (-58.0)
#define DB_AB (-84.0)
static const double DB_A[KLATT_FORMANTS] = {-58.0, -65.0, -73.0, -78.0, -79.0, -80.0};

/* The source parameters and the amplitudes are held to the ranges of K80 Table I
 * and K90 Table XII.  Formants and bandwidths are not: the tables are one
 * talker's English, and another voice's frames go lower and higher.  A frequency
 * is held to 0 .. SR/2 and a bandwidth to BW_MIN .. SR/2: inside that every
 * resonator is Eq. (2)'s and stable, its poles at exp(-pi BW T) < 1. */
#define BW_MIN 5.0
/* The one place the wider range needs a hold of its own: the parallel branch
 * divides by F2 (see klatt_set_frame), so there F2 counts as no less than this,
 * the lowest second formant of K80 Table I. */
#define F2_SKIRT_MIN 500.0
#define AMP_MAX 80.0
#define F0_MAX 500.0
#define F0_MIN 40.0         /* K80's listing lets no voiced F0 fall below 40 Hz */

/* K80 Table I, the glottal filters' constants: RGP at FGP = 0 Hz, BGP = 100 Hz;
 * the zero RGZ at 1500 Hz, 6000 Hz wide; RGS 200 Hz wide. */
#define BGP 100.0
#define FGZ 1500.0
#define BGZ 6000.0
#define BGS 200.0
/* From K80's listing, which settles what the text leaves out: RGP's gain is a
 * constant, so the level between the formants does not move with its bandwidth;
 * the bandwidth is BGP at 100 Hz and narrows as F0 rises; the impulse grows with
 * F0; and the quasi-sinusoidal impulse is ten times its control's value. */
#define RGP_GAIN 0.007
#define AVS_GAIN 10.0

/* KLGLOTT88: the peak of the glottal flow when AV's linear factor is 1.  K90 says
 * only that a and b follow from the amplitude of voicing and the open period, and
 * gives no scale.  My choice: at the default open quotient of 50 % the step in
 * the flow's derivative at closure equals the step K80's source makes at its
 * impulse, for the same AV and F0, so the two sources are about equally loud.
 * With the derivative taken per 0.1 ms the step at closure is
 * 27 peak F0 / (4 (OQ/100) 10000); K80's is RGP_GAIN x F0. */
#define KLGLOTT88_PEAK (RGP_GAIN * 4.0 * 0.5 * 10000.0 / 27.0)
#define REFERENCE_RATE 10000.0

/* K90, footnote 17: the glottal source runs at four times the sampling rate, so
 * a period is a whole number of quarter samples.  The decimator is my design: a
 * Kaiser-windowed sinc of 97 taps, 60 dB down in the stop band, cut off at
 * 0.475 SR: flat to 0.4 SR, and nothing above 0.55 SR is left to fold back below
 * 0.45 SR.  Its delay is a whole number of output samples. */
#define OVERSAMPLE 4
#define TAPS 97
#define DELAY ((TAPS - 1) / 2 / OVERSAMPLE)
#define KAISER_BETA 5.653
#define CUTOFF 0.475
#define MIN_PERIOD 8        /* ticks; never reached inside the ranges above */

/* Below this a filter's memory is called zero: silence then costs no denormals. */
#define TINY 1e-30
/* Above this the filters' memories are cleared.  Stable filters fed bounded input
 * never get here; filters whose constants a caller changes every sample might. */
#define HUGE_LEVEL 1e30

/* K80 Eq. (1): y(n) = A x(n) + B y(n-1) + C y(n-2).  As an antiresonator, Eq. (4),
 * the two remembered samples are inputs. */
typedef struct {
    double a, b, c;
    double m1, m2;
} section;

/* K80, I-F: a noise amplitude moves to its new value in a straight line. */
typedef struct {
    double now, target, step;
    int left;
} ramp;

typedef struct {
    /* the config */
    double rate;            /* SR */
    double tick_rate;       /* 4 SR: the glottal source's own rate */
    double per_tick;        /* turns a difference per tick into one per 0.1 ms */
    double g0;
    int frame_samples;      /* NWS */
    int n_cascade;          /* NF */
    int source;             /* SS */
    int all_parallel;       /* SW */
    int tap;                /* OS */
    int parallel_corrections;   /* K80's corrections of A1..A6: on or off */

    /* the source parameters of the last frame: they wait for a glottal opening */
    double next_f0, next_av, next_avs, next_oq, next_tl, next_fl;

    /* the glottal source, in ticks */
    uint64_t ticks;         /* since klatt_init */
    int voiced;             /* a period is running */
    int modulated;          /* and its AV is not 0 */
    int period, pos;        /* its length; how far into it */
    int open_ticks;         /* KLGLOTT88: the open phase */
    double flow_a;          /* KLGLOTT88: a, per tick squared */
    double flow_was;        /* KLGLOTT88: the flow one tick ago */
    double impulse;         /* K80: this period's impulse */
    double sine_impulse;    /* K80: and the one for quasi-sinusoidal voicing */
    section tilt;

    /* the decimator */
    double taps[TAPS];
    double line[2][TAPS];   /* the last TAPS ticks of the pulses and of AVS's impulses */
    int line_at;
    unsigned char gate[DELAY];  /* the noise modulator, delayed as the voicing is */
    int gate_at;

    /* K80's glottal filters, at SR */
    section rgp, rgz, rgs, rgp_sine;
    double flow_last;       /* for the radiation characteristic */

    /* the noise */
    uint32_t noise;
    ramp aspiration, frication;
    double last_af;         /* dB, as the last frame gave it */

    /* the tract */
    section cascade[KLATT_FORMANTS], nasal_zero, nasal_pole;
    section parallel[KLATT_FORMANTS], parallel_nasal;
    double amp[KLATT_FORMANTS], amp_nasal, amp_bypass;
    double glottal_last;    /* for the parallel branch's first difference */
} klatt_state;

/* ---- small things ------------------------------------------------------ */

/* x held to lo..hi; not-a-number becomes lo. */
static double hold(double x, double lo, double hi)
{
    if (!(x >= lo))
        return lo;
    return x > hi ? hi : x;
}

/* A control in dB as a linear factor.  0 dB is off: K80 Table I's "0 dB when the
 * source is turned off", made exact. */
static double level(double db, double scale_db)
{
    return db > 0.0 ? exp((db + scale_db) * (LN10 / 20.0)) : 0.0;
}

static int whole(double x, double lo, double hi)
{
    return x >= lo && x <= hi && x == floor(x);
}

void klatt_resonator(double f, double bw, double sample_rate, double abc[3])
{
    /* K80 Eq. (2), the impulse-invariant transformation */
    const double t = 1.0 / sample_rate;
    abc[2] = -exp(-2.0 * PI * bw * t);
    abc[1] = 2.0 * exp(-PI * bw * t) * cos(2.0 * PI * f * t);
    abc[0] = 1.0 - abc[1] - abc[2];
}

static void set_resonator(section *r, double f, double bw, double rate)
{
    double abc[3];
    klatt_resonator(f, bw, rate, abc);
    r->a = abc[0];
    r->b = abc[1];
    r->c = abc[2];
}

/* K80 Eq. (5).  The antiresonator is the resonator's inverse, so C' = -C/A: the
 * printed "-CA" would not give the mirror-image response the text describes. */
static void set_antiresonator(section *r, double f, double bw, double rate)
{
    double abc[3];
    klatt_resonator(f, bw, rate, abc);
    r->a = 1.0 / abc[0];
    r->b = -abc[1] / abc[0];
    r->c = -abc[2] / abc[0];
}

static double resonate(section *r, double x)
{
    double y = r->a * x + r->b * r->m1 + r->c * r->m2;
    if (y > -TINY && y < TINY)
        y = 0.0;
    r->m2 = r->m1;
    r->m1 = y;
    return y;
}

static double antiresonate(section *r, double x)
{
    const double y = r->a * x + r->b * r->m1 + r->c * r->m2;
    r->m2 = r->m1;
    r->m1 = x;
    return y;
}

static void forget(section *r)
{
    r->m1 = 0.0;
    r->m2 = 0.0;
}

static void ramp_to(ramp *r, double target, int samples, int at_once)
{
    r->target = target;
    if (at_once) {
        r->now = target;
        r->left = 0;
    } else {
        r->step = (target - r->now) / samples;
        r->left = samples;
    }
}

static double ramp_next(ramp *r)
{
    if (r->left > 0) {
        r->left--;
        r->now = r->left ? r->now + r->step : r->target;
    }
    return r->now;
}

/* ---- the noise source -------------------------------------------------- */

/* K80, I-D: sixteen uniform random numbers summed, for a nearly Gaussian
 * distribution; each from 0 to 1 (the listing), less the mean of 8.  The
 * generator is my choice: a 32-bit xorshift, written out so that the samples are
 * the same everywhere; its top 16 bits are the number. */
static double next_noise(klatt_state *s)
{
    uint32_t x = s->noise, sum = 0;
    int i;
    for (i = 0; i < 16; i++) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        sum += x >> 16;
    }
    s->noise = x;
    return ((double)sum - 16.0 * 32767.5) / 65536.0;
}

/* ---- the voicing source ------------------------------------------------ */

/* K90 Fig. 10: the tilt filter is a low-pass resonator, F = 0, its bandwidth a
 * function of TL.  The function is mine.  With F = 0 both poles sit at r, and
 * the gain at w = 2 pi 3000 T is (1-r)^2 / (1 - 2 r cos w + r^2).  Setting that
 * to g = 10^(-TL/20) gives a quadratic in r whose root inside the unit circle is
 *     r = (p - sqrt(p^2 - q^2)) / q,   p = 1 - g cos w,   q = 1 - g.
 * TL = 0 gives r = 0: the filter passes its input unchanged. */
static void set_tilt(section *r, double tl, double rate)
{
    double pole = 0.0;
    if (tl > 0.0) {
        const double g = exp(-tl * (LN10 / 20.0));
        const double p = 1.0 - g * cos(2.0 * PI * 3000.0 / rate);
        const double q = 1.0 - g;
        pole = (p - sqrt(p * p - q * q)) / q;
    }
    r->c = -(pole * pole);
    r->b = 2.0 * pole;
    r->a = 1.0 - r->b - r->c;
}

/* A glottal opening: the one moment the source takes new values of F0, AV, AVS,
 * OQ, TL and FL (K80, I-F; K90, footnotes 17 and 18), so that no amplitude jumps
 * in the middle of a pulse.  With F0 or the amplitude at 0 no pulse is issued,
 * and the question is asked again every tick: voicing starts on the tick both
 * become nonzero (K80, I-G). */
static void open_glottis(klatt_state *s)
{
    const double f0 = s->next_f0;
    double hz = f0, peak;

    s->voiced = 0;
    s->modulated = 0;
    if (!(f0 > 0.0))
        return;
    /* AVS belongs to K80's source; K90's has no such control, so there it does
     * nothing */
    if (!(s->next_av > 0.0) && !(s->source == SOURCE_IMPULSIVE && s->next_avs > 0.0))
        return;

    if (s->next_fl > 0.0) {
        /* K90 Eq. (1): three slow sine waves added to F0 */
        const double t = (double)s->ticks / s->tick_rate;
        hz += (s->next_fl / 50.0) * (f0 / 100.0)
            * (sin(2.0 * PI * 12.7 * t) + sin(2.0 * PI * 7.1 * t) + sin(2.0 * PI * 4.7 * t));
    }
    /* K90, footnote 17: the period, to the nearest quarter of a sample */
    s->period = (int)floor(s->tick_rate / hz + 0.5);
    if (s->period < MIN_PERIOD)
        s->period = MIN_PERIOD;
    s->pos = 0;
    s->voiced = 1;
    s->modulated = s->next_av > 0.0;

    set_tilt(&s->tilt, s->next_tl, s->tick_rate);
    peak = level(s->next_av, s->g0 + DB_AV);
    if (s->source == SOURCE_KLGLOTT88) {
        /* K90, II B: Ug(t) = a t^2 - b t^3 while the glottis is open, OQ percent
         * of the period.  The flow is back at 0 when the open phase ends, so
         * b = a / n for n open ticks; it peaks at t = 2n/3 with 4 a n^2 / 27,
         * and AV is that peak ("the peak amplitude of the glottal pulse"):
         * a = 27 peak / (4 n^2). */
        int n = (int)floor(s->next_oq / 100.0 * s->period + 0.5);
        if (n < 2)
            n = 2;
        if (n > s->period)
            n = s->period;
        s->open_ticks = n;
        s->flow_a = 6.75 * (KLGLOTT88_PEAK * peak) / ((double)n * (double)n);
        s->flow_was = 0.0;
    } else {
        /* K80, I-A to I-C: an impulse per period, AV its amplitude.  The decimator
         * passes a quarter of a tick-rate impulse, hence the factor. */
        double abc[3];
        klatt_resonator(0.0, BGP * 100.0 / f0, s->rate, abc);
        s->impulse = OVERSAMPLE * peak * f0;
        s->sine_impulse = OVERSAMPLE * AVS_GAIN * level(s->next_avs, s->g0 + DB_AVS);
        s->rgp.a = s->rgp_sine.a = RGP_GAIN;
        s->rgp.b = s->rgp_sine.b = abc[1];
        s->rgp.c = s->rgp_sine.c = abc[2];
    }
}

/* One tick of the glottal source: a quarter of an output sample. */
static void tick(klatt_state *s)
{
    double x = 0.0, sine = 0.0;

    if (!s->voiced || s->pos >= s->period)
        open_glottis(s);
    if (s->voiced) {
        if (s->source == SOURCE_KLGLOTT88) {
            if (s->pos < s->open_ticks) {
                /* The radiation characteristic is folded into the source (K90
                 * Fig. 10): what leaves is the first difference of the flow
                 * (K80 Eq. (7)), here per tick and scaled to one per 0.1 ms so
                 * that the level does not depend on the sampling rate.  Taking
                 * differences of a t^2 (1 - t/n), not sampling the derivative,
                 * makes each pulse sum to exactly nothing: no dc, and silence
                 * while the glottis is closed. */
                const double k = (double)(s->pos + 1);
                const double u = s->flow_a * k * k * (1.0 - k / (double)s->open_ticks);
                x = (u - s->flow_was) * s->per_tick;
                s->flow_was = u;
            }
        } else if (s->pos == 0) {
            x = s->impulse;
            sine = s->sine_impulse;
        }
        s->pos++;
    }
    s->ticks++;

    /* K90 Figs. 10 and 14: every voicing source goes through the tilt filter */
    s->line[0][s->line_at] = resonate(&s->tilt, x);
    s->line[1][s->line_at] = sine;
    if (++s->line_at == TAPS)
        s->line_at = 0;
}

/* The decimator's output for the newest tick in a line. */
static double decimate(const klatt_state *s, const double *line)
{
    double sum = 0.0;
    int i, at = s->line_at;
    for (i = 0; i < TAPS; i++) {
        if (--at < 0)
            at = TAPS - 1;
        sum += s->taps[i] * line[at];
    }
    return sum;
}

/* The modified Bessel function I0, by its power series. */
static double bessel_i0(double x)
{
    double sum = 1.0, term = 1.0;
    int k;
    for (k = 1; k <= 40; k++) {
        term *= (x * 0.5) / k;
        sum += term * term;
    }
    return sum;
}

static void design_decimator(double *taps)
{
    const int centre = (TAPS - 1) / 2;
    const double fc = CUTOFF / OVERSAMPLE;      /* cycles per tick */
    double sum = 0.0;
    int i;
    for (i = 0; i <= centre; i++) {
        const double m = (double)(i - centre);
        const double ideal = i == centre ? 2.0 * fc : sin(2.0 * PI * fc * m) / (PI * m);
        const double t = m / centre;
        taps[i] = ideal * bessel_i0(KAISER_BETA * sqrt(1.0 - t * t)) / bessel_i0(KAISER_BETA);
        taps[TAPS - 1 - i] = taps[i];
    }
    for (i = 0; i < TAPS; i++)
        sum += taps[i];
    for (i = 0; i < TAPS; i++)
        taps[i] /= sum;                         /* unity gain at dc */
}

/* ---- frames ------------------------------------------------------------ */

/* K80, II-G, rule (2): the parallel formants rise when two of them come close,
 * as a cascade's do (Fig. 11(d)).  The listing has the numbers: 10 dB at 50 Hz
 * apart, a dB less for every 50 Hz more, nothing from 550 Hz.  A straight line
 * through the middle of each of those steps, so a moving formant makes no steps. */
static double proximity_db(double apart)
{
    return hold((575.0 - apart) / 50.0, 0.0, 10.0);
}

/* How much of each pair's rise a parallel formant gets: the pairs are F1-F2,
 * F2-F3 and F3-F4; the lower formant of a pair gets it once, the upper twice. */
static const double NEAR[KLATT_FORMANTS][3] = {
    {1.0, 0.0, 0.0}, {2.0, 1.0, 0.0}, {0.0, 2.0, 1.0}, {0.0, 0.0, 2.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}};

void klatt_set_frame(void *state, const klatt_frame *in)
{
    klatt_state *s = (klatt_state *)state;
    const double nyquist = s->rate * 0.5;
    double f[KLATT_FORMANTS], near[3], af, d1, d2;
    int i;

    /* the source: held here, taken at the next glottal opening */
    s->next_f0 = hold(in->f0, 0.0, F0_MAX);
    if (s->next_f0 > 0.0 && s->next_f0 < F0_MIN)
        s->next_f0 = F0_MIN;
    s->next_av = hold(in->av, 0.0, AMP_MAX);
    s->next_avs = hold(in->avs, 0.0, AMP_MAX);
    s->next_oq = hold(in->oq, 10.0, 99.0);
    s->next_tl = hold(in->tl, 0.0, 41.0);
    s->next_fl = hold(in->fl, 0.0, 100.0);

    /* the noise: K80, I-F.  AF and AH reach their new values after one frame;
     * but a plosive's burst starts faster than that, so a rise in AF of more
     * than 50 dB is made at once. */
    af = hold(in->af, 0.0, AMP_MAX);
    ramp_to(&s->aspiration, level(hold(in->ah, 0.0, AMP_MAX), s->g0 + DB_AH), s->frame_samples, 0);
    ramp_to(&s->frication, level(af, s->g0 + DB_AF), s->frame_samples, af - s->last_af > 50.0);
    s->last_af = af;

    /* the tract: the same formant frequencies in the cascade and in the parallel
     * branch */
    for (i = 0; i < KLATT_FORMANTS; i++) {
        f[i] = hold(in->f[i], 0.0, nyquist);
        set_resonator(&s->cascade[i], f[i], hold(in->b[i], BW_MIN, nyquist), s->rate);
        if (in->bp[i] != 0.0) {
            /* K90 Table XII (B2F to B6F): a parallel formant may have a bandwidth
             * of its own, a noise-excited formant being wider than the same one in
             * the cascade.  Only the bandwidth differs: the frequency is shared,
             * and the amplitude rules below do not look at bandwidths. */
            set_resonator(&s->parallel[i], f[i], hold(in->bp[i], BW_MIN, nyquist), s->rate);
        } else {
            /* K80: one bandwidth for both branches */
            s->parallel[i].a = s->cascade[i].a;
            s->parallel[i].b = s->cascade[i].b;
            s->parallel[i].c = s->cascade[i].c;
        }
    }
    set_resonator(&s->nasal_pole, hold(in->fnp, 0.0, nyquist), hold(in->bnp, BW_MIN, nyquist), s->rate);
    s->parallel_nasal.a = s->nasal_pole.a;
    s->parallel_nasal.b = s->nasal_pole.b;
    s->parallel_nasal.c = s->nasal_pole.c;
    /* the zero's A is at least (1 - exp(-pi BW T))^2 > 0, so 1/A is finite */
    set_antiresonator(&s->nasal_zero, hold(in->fnz, 0.0, nyquist), hold(in->bnz, BW_MIN, nyquist), s->rate);

    /* The parallel amplitudes.  K80, II-G: with A1 to A5 all at 60 dB the
     * parallel branch is to give about the cascade's transfer function, so
     * (1) a formant's gain follows the formants below it, on whose skirts it
     * rides in a cascade (rule 4: with the square of their frequencies; 500 and
     * 1500 Hz are the neutral tube's), and (2) two close formants both rise, the
     * upper one twice as much.  The second formant loses one power of F2 again to
     * the first difference its voicing input goes through.  The text states the
     * rules and no numbers: the arithmetic, and the 50 and 150 Hz taken off the
     * two upper distances, are settled from K80's listing.
     * With formants free to be anywhere from 0 to SR/2 the factors stay finite:
     * no formant is above SR/2, so the products are bounded; a rise is 0 to
     * 10 dB whatever the distance (negative too); and the one division is by an
     * F2 that is not let under F2_SKIRT_MIN here.  (As F2 goes to 0 so does what
     * the first difference passes, and undoing that would take a gain without
     * limit.)
     * The config can turn all of this off. */
    d1 = f[0] / 500.0;
    d2 = (f[1] > F2_SKIRT_MIN ? f[1] : F2_SKIRT_MIN) / 1500.0;
    near[0] = proximity_db(f[1] - f[0]);
    near[1] = proximity_db(f[2] - f[1] - 50.0);
    near[2] = proximity_db(f[3] - f[2] - 150.0);
    for (i = 0; i < KLATT_FORMANTS; i++) {
        const double a = hold(in->a[i], 0.0, AMP_MAX);
        if (s->parallel_corrections) {
            const double skirt = i == 0 ? 1.0 : i == 1 ? d1 * d1 / d2 : d1 * d1 * d2 * d2;
            const double boost = NEAR[i][0] * near[0] + NEAR[i][1] * near[1] + NEAR[i][2] * near[2];
            s->amp[i] = skirt * level(a, boost + DB_A[i]);
        } else {
            /* The later KLSYN88 makes none of these corrections: a parallel
             * formant's amplitude is what its control says, wherever the other
             * formants are.  The scale factors stay K80's. */
            s->amp[i] = level(a, DB_A[i]);
        }
    }
    s->amp_nasal = level(hold(in->an, 0.0, AMP_MAX), DB_AN);
    s->amp_bypass = level(hold(in->ab, 0.0, AMP_MAX), DB_AB);
}

/* ---- one sample -------------------------------------------------------- */

static void forget_everything(klatt_state *s)
{
    int i;
    forget(&s->tilt);
    forget(&s->rgp);
    forget(&s->rgz);
    forget(&s->rgs);
    forget(&s->rgp_sine);
    forget(&s->nasal_zero);
    forget(&s->nasal_pole);
    forget(&s->parallel_nasal);
    for (i = 0; i < KLATT_FORMANTS; i++) {
        forget(&s->cascade[i]);
        forget(&s->parallel[i]);
    }
    memset(s->line, 0, sizeof s->line);
    s->flow_last = 0.0;
    s->glottal_last = 0.0;
}

static double next_sample(klatt_state *s)
{
    double voicing, sine = 0.0, noise, aspiration, frication, glottal, lips, diff = 0.0;
    double y2, y3, y4, y5, y6, out;
    int gate, i;

    /* The voicing source: four ticks in, one sample out.  The decimator is read
     * after the first tick, which puts its delay at DELAY whole samples. */
    tick(s);
    gate = s->gate[s->gate_at];
    s->gate[s->gate_at] = (unsigned char)(s->voiced && s->modulated && 2 * (s->pos - 1) < s->period);
    if (++s->gate_at == DELAY)
        s->gate_at = 0;
    voicing = decimate(s, s->line[0]);
    if (s->source == SOURCE_IMPULSIVE)
        sine = decimate(s, s->line[1]);
    tick(s);
    tick(s);
    tick(s);

    if (s->source == SOURCE_IMPULSIVE) {
        /* K80, I-B and I-C, at K80's own rate so that Eq. (2) gives its filters:
         * normal voicing is the impulse through the low-pass RGP and the zero
         * RGZ; quasi-sinusoidal voicing is its own impulse through RGS and RGP.
         * Their sum is the glottal flow, and the radiation characteristic, Eq.
         * (7), is moved into the source as K80, I-D allows. */
        const double flow = antiresonate(&s->rgz, resonate(&s->rgp, voicing))
                          + resonate(&s->rgp_sine, resonate(&s->rgs, sine));
        voicing = flow - s->flow_last;
        s->flow_last = flow;
    }

    /* K80, I-D and I-E: one noise generator for aspiration and frication.  With
     * voicing on, a square wave of the period modulates it by 50 %; the listing
     * settles which way: half amplitude is the level of voiceless noise, and the
     * first half of each period has the full one.  The low-pass LPF and the
     * radiation characteristic cancel, so neither is computed. */
    noise = next_noise(s);
    if (!gate)
        noise *= 0.5;
    aspiration = ramp_next(&s->aspiration) * noise;
    frication = ramp_next(&s->frication) * noise;
    glottal = voicing + aspiration;

    if (!s->all_parallel) {
        /* K80, II-A and II-E: the laryngeal sources go through the nasal zero
         * and pole (K90 Fig. 14 has them first) and NF formants, the highest
         * first (K80 Fig. 3). */
        lips = resonate(&s->nasal_pole, antiresonate(&s->nasal_zero, glottal));
        for (i = s->n_cascade - 1; i >= 0; i--)
            lips = resonate(&s->cascade[i], lips);
    } else {
        /* K80, II-G: the first formant and the nasal formant take the place of
         * the cascade.  The formants above the first get the first difference of
         * the source, which keeps their low frequencies out of F1's region (rule
         * 3); that the nasal formant gets it too is settled from the listing. */
        diff = glottal - s->glottal_last;
        s->glottal_last = glottal;
        lips = resonate(&s->parallel[0], s->amp[0] * glottal)
             + resonate(&s->parallel_nasal, s->amp_nasal * diff);
    }

    /* K80, II-F: frication excites F2 to F6 in parallel, each with its own
     * amplitude, and a bypass path with none of them.  Voicing reaches only the
     * second to fourth (K90 Table XII: A2V to A4V).  The formants' outputs are
     * summed with alternating signs (K80, II-G and Fig. 13); the signs of the
     * nasal formant and of the bypass path are settled from the listing. */
    y2 = resonate(&s->parallel[1], s->amp[1] * (frication + diff));
    y3 = resonate(&s->parallel[2], s->amp[2] * (frication + diff));
    y4 = resonate(&s->parallel[3], s->amp[3] * (frication + diff));
    y5 = resonate(&s->parallel[4], s->amp[4] * frication);
    y6 = resonate(&s->parallel[5], s->amp[5] * frication);
    lips = lips - y2 + y3 - y4 + y5 - y6 - s->amp_bypass * frication;

    if (!(fabs(lips) < HUGE_LEVEL) || !(fabs(voicing) < HUGE_LEVEL)) {
        forget_everything(s);
        return 0.0;
    }
    switch (s->tap) {
    case TAP_VOICING:
        return voicing * OUTPUT_SCALE;
    case TAP_ASPIRATION:
        return aspiration * OUTPUT_SCALE;
    case TAP_FRICATION:
        return frication * OUTPUT_SCALE;
    default:
        break;
    }
    out = lips * OUTPUT_SCALE;
    if (out > OUTPUT_LIMIT)
        out = OUTPUT_LIMIT;
    if (out < -OUTPUT_LIMIT)
        out = -OUTPUT_LIMIT;
    return out;
}

/* ---- the interface ----------------------------------------------------- */

int klatt_state_size(void)
{
    return (int)sizeof(klatt_state);
}

double klatt_full_scale(void)
{
    return FULL_SCALE;
}

void klatt_config_defaults(klatt_config *c)
{
    /* K80 Table I and K90 Table XI */
    c->sample_rate = 10000.0;
    c->samples_per_frame = 50.0;
    c->n_cascade = 5.0;
    c->source = SOURCE_KLGLOTT88;
    c->all_parallel = 0.0;
    c->tap = TAP_OUTPUT;
    c->seed = 8.0;
    c->gain_db = 47.0;
    c->parallel_corrections = 1.0;      /* K80's parallel branch */
}

void klatt_frame_defaults(klatt_frame *f)
{
    /* K90 Table XII; F6 and B6 are K80's, and so is the parallel branch sharing
     * the cascade's bandwidths */
    static const double F[KLATT_FORMANTS] = {500.0, 1500.0, 2500.0, 3250.0, 3700.0, 4900.0};
    static const double B[KLATT_FORMANTS] = {60.0, 90.0, 150.0, 200.0, 200.0, 1000.0};
    int i;
    f->f0 = 100.0;
    f->av = 60.0;
    f->avs = 0.0;
    f->ah = 0.0;
    f->af = 0.0;
    f->oq = 50.0;
    f->tl = 0.0;
    f->fl = 0.0;
    for (i = 0; i < KLATT_FORMANTS; i++) {
        f->f[i] = F[i];
        f->b[i] = B[i];
        f->a[i] = 0.0;
        f->bp[i] = 0.0;
    }
    f->fnp = 280.0;
    f->bnp = 90.0;
    f->fnz = 280.0;
    f->bnz = 90.0;
    f->an = 0.0;
    f->ab = 0.0;
}

int klatt_init(void *state, const klatt_config *c)
{
    klatt_state *s = (klatt_state *)state;
    klatt_frame frame;

    memset(s, 0, sizeof *s);
    if (!(c->sample_rate >= 5000.0 && c->sample_rate <= 20000.0)
        || !whole(c->samples_per_frame, 1.0, 200.0)
        || !whole(c->n_cascade, 1.0, KLATT_FORMANTS)
        || !whole(c->source, SOURCE_IMPULSIVE, SOURCE_KLGLOTT88)
        || !whole(c->all_parallel, 0.0, 1.0)
        || !whole(c->tap, TAP_OUTPUT, TAP_FRICATION)
        || !whole(c->parallel_corrections, 0.0, 1.0)
        || c->seed != c->seed || c->gain_db != c->gain_db)
        return -1;

    s->rate = c->sample_rate;
    s->tick_rate = OVERSAMPLE * c->sample_rate;
    s->per_tick = s->tick_rate / REFERENCE_RATE;
    s->g0 = hold(c->gain_db, 0.0, 80.0);
    s->frame_samples = (int)c->samples_per_frame;
    s->n_cascade = (int)c->n_cascade;
    s->source = (int)c->source;
    s->all_parallel = (int)c->all_parallel;
    s->tap = (int)c->tap;
    s->parallel_corrections = (int)c->parallel_corrections;

    /* the seed is scrambled so that neighbouring seeds give unrelated noise;
     * an xorshift must not start at 0 */
    s->noise = (uint32_t)floor(hold(c->seed, 0.0, 4294967295.0)) * 2654435761u + 1u;
    if (s->noise == 0)
        s->noise = 1;

    design_decimator(s->taps);
    set_tilt(&s->tilt, 0.0, s->tick_rate);
    set_antiresonator(&s->rgz, FGZ, BGZ, s->rate);
    set_resonator(&s->rgs, 0.0, BGS, s->rate);

    klatt_frame_defaults(&frame);
    klatt_set_frame(s, &frame);
    return 0;
}

void klatt_run(void *state, int n, double *out)
{
    klatt_state *s = (klatt_state *)state;
    int i;
    for (i = 0; i < n; i++)
        out[i] = next_sample(s);
}
