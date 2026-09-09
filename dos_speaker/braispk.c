/* braispk.c -- a BraiLab speech adapter that lives in 16-bit DOS memory and
 * talks through the PC speaker.
 *
 * TALKHUN.COM (BraiLab's 1991-2003 DOS screen reader) drives a PCF8200 speech
 * chip on a home-built printer-port adapter: an I2C-style 2-wire bit-bang on
 * data bits 0/1, and a ready poll on the status port.  TALKHUNS.COM is the
 * same program with those two touch points redirected to INT 61h (see
 * patch_talkhun.py).  This TSR answers INT 61h:
 *
 *   AH = FFh          ready poll:  AL = 30h busy / 20h ready (bit 5 always set;
 *                     TALKHUN reads a clear bit 5 as a broken adapter)
 *   AH = FEh          identify:    AX = MAGIC, BX = resident DS, CX = CS,
 *                                  DX = resident PSP
 *   AH = FDh          counters:    AX = frames, BX = controls, CX = pitches,
 *                                  DX = samples queued
 *   AH = FCh          reset the handshake and forget queued audio
 *   any other AH      one wire step, bits AH&3 = (clock<<1)|data
 *
 * Bytes assemble into transactions exactly as the adapter saw them: five bytes
 * are a speech frame, two a control write, one a start-sequence single
 * (settings nibble, then pitch).  A frame is synthesised at once -- the chip's
 * five-formant cascade at its own 10 kHz rate, the same model as
 * talkhun_emu/chip_synth.py -- into a ring of 8-bit PWM counts.
 *
 * Output is the SPEAKER 1990 method: IRQ0 reprogrammed to 1193182/119 =
 * 10027 Hz, and every tick writes one count into PIT channel 2 in mode 0, so
 * the speaker line goes low for `count` cycles out of 119.  The old INT 08 is
 * chained every 551st tick, so DOS time and TALKHUN's own timer hook keep
 * running at 18.2 Hz.
 *
 * The BUSY line is what paced BraiLab's games: it reads busy while more than
 * ~100 ms of audio is queued (the real adapter's FIFO; TALKHUN's poll gives up
 * after four BIOS ticks), busy at rest until the first transaction of an
 * utterance (that is what lets the start sequence carrying the pitch go out),
 * and back at rest after a STOP control.
 *
 * Build: see build.sh (Open Watcom, 16-bit small model, x87 code).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <conio.h>
#include <dos.h>
#include <i86.h>
#include <io.h>
#include <fcntl.h>
#include <float.h>

/* The INT 08 vector, read and written directly.  Resident code must not call
 * DOS: INT 61h can arrive from inside TALKHUN's INT 21h and INT 10h hooks. */
#define IVT08        (*(void (__interrupt __far * __far *)(void))MK_FP(0, 0x20))

#define MAGIC        0xB7A1
#define API_INT      0x61
#define PIT_DIV      119            /* 1193182 / 119 = 10027 Hz  (IRQ0 mode)   */
#define CHAIN_TICKS  551            /* 10027 / 18.2065 -> old INT 08 at 18.2  */
#define RTC_RATE     3              /* CMOS reg 0Ah rate 3 = 8192 Hz (RTC mode) */

/* Which interrupt carries the samples.  RTC (IRQ8) is the default: it leaves
 * PIT channel 0, the BIOS tick, IO.SYS's and TALKHUN's INT 08 hooks alone.
 * On the first real machine (Pentium 166, Windows 98 DOS) the IRQ0 route
 * played the chirp but the BIOS tick stopped advancing while it ran, and the
 * box froze on the first utterance; IO.SYS sits on INT 08 there and DOSBox
 * has nothing on it, so that chain was never exercised before. */
#define CLOCK_RTC    1
#define CLOCK_PIT    0
static unsigned char clock_mode = CLOCK_RTC;
static double fs_hz = 8192.0;       /* the actual sample rate we run at        */
#define FS           fs_hz
/* PWM: one PIT channel-2 mode-0 count per tick; the count must stay below the
 * tick period in PIT cycles (145.6 at 8192 Hz, 119 at 10027 Hz). */
static int pwm_top = 144, pwm_mid = 72, pwm_amp = 69;

#define RING_SIZE    4096           /* samples (power of two), ~400 ms         */
#define RING_MASK    (RING_SIZE - 1)
#define FIFO_BUSY    1000           /* > this many queued -> report busy (~100 ms) */

#define STATUS_BUSY  0x30
#define STATUS_READY 0x20

#define STD_SAMPLES  128            /* one standard 12.8 ms frame at 10 kHz    */
#define BLOCK        8              /* coefficient update granularity          */
#define MAX_FORMANTS 5

/* ---- the chip's quantisation ROM (pcf8200_tables.py) -------------------- */
static const int MALE_F1[32] = {100,109,119,130,141,154,168,183,199,217,237,258,282,307,335,365,398,433,472,515,561,612,667,727,793,864,942,1027,1119,1220,1330,1450};
static const int MALE_F2[32] = {500,526,554,583,614,646,680,716,754,793,835,879,925,974,1025,1079,1136,1195,1258,1324,1394,1467,1545,1626,1711,1801,1896,1996,2101,2211,2328,2450};
static const int MALE_F3[8]  = {1500,1690,1903,2143,2414,2719,3063,3450};
static const int MALE_F4[8]  = {2550,2766,2999,3253,3528,3826,4149,4500};
static const int MALE_F5[2]  = {3900,4600};
static const int MALE_B1[8]  = {3000,600,303,153,77,39,20,10};
static const int MALE_B2[8]  = {3000,800,433,234,126,68,37,20};
static const int MALE_B3[4]  = {3000,600,190,60};
static const int MALE_B4[4]  = {3000,700,265,100};
static const int MALE_B5[4]  = {3000,800,335,140};
static const int FEM_F1[32]  = {100,110,121,134,147,162,179,197,217,239,263,290,319,351,387,426,469,517,569,627,691,761,838,923,1017,1120,1234,1359,1497,1649,1816,2000};
static const int FEM_F2[32]  = {500,529,561,594,629,666,705,747,791,837,886,939,994,1053,1115,1180,1250,1323,1401,1484,1571,1664,1762,1866,1976,2092,2216,2346,2484,2631,2786,2950};
static const int FEM_F3[8]   = {2050,2251,2473,2715,2982,3275,3597,3950};
static const int FEM_F4[8]   = {3500,3662,3831,4007,4192,4386,4588,4800};
static const int FEM_B1[8]   = {3000,700,414,245,145,86,51,30};
static const int FEM_B2[8]   = {3000,1000,626,391,245,153,96,60};
static const int FEM_B3[4]   = {3000,700,265,100};
static const int FEM_B4[4]   = {3000,800,322,130};
static const float AMPL[16]  = {0.0f,0.0078125f,0.01171875f,0.015625f,0.021484375f,0.03125f,0.044921875f,0.0625f,0.087890625f,0.125f,0.17578125f,0.25f,0.353515625f,0.5f,0.70703125f,1.0f};
static const float PI_TAB[32] = {0.0f,1.2f,2.4f,3.7f,4.9f,6.1f,7.3f,8.5f,9.8f,11.0f,13.4f,15.9f,19.5f,25.6f,34.2f,45.2f,0.0f,-45.2f,-34.2f,-25.6f,-19.5f,-15.9f,-13.4f,-11.0f,-9.8f,-8.5f,-7.3f,-6.1f,-4.9f,-3.7f,-2.4f,-1.2f};
static const int FD_MULT[4]  = {1, 2, 3, 5};
#define PITCH_HZ_PER_UNIT (10000.0 / 4096.0)
#define PI_NOISE 16

/* ---- the ear-matched output stage (chip_synth.py) ------------------------ */
#define TILT_HZ       600.0
#define HIGHPASS_HZ   90.0
#define MAKEUP        0.9315
#define SOFTKNEE      0.75
/* butter(4, 2600, 'low') as two second-order sections, designed at run time
 * for the rate in use: Butterworth Qs 0.5412 and 1.3066, RBJ bilinear form.
 * At 10 kHz this reproduces the table the NVDA voice was tuned with. */
#define LP_HZ         2600.0
static double LP_A[5], LP_B[5];
static void lp_design(double fs)
{
    static const double Q[2] = {0.54119610014619701, 1.3065629648763764};
    double w0 = 2.0 * 3.14159265358979 * LP_HZ / fs, c = cos(w0), sn = sin(w0);
    double alpha, a0, g = 1.0;
    int k;
    for (k = 0; k < 2; k++) {
        double *A = k ? LP_B : LP_A;
        alpha = sn / (2.0 * Q[k]);
        a0 = 1.0 + alpha;
        A[0] = (1.0 - c) / 2.0 / a0; A[1] = (1.0 - c) / a0; A[2] = A[0];
        A[3] = -2.0 * c / a0; A[4] = (1.0 - alpha) / a0;
    }
    /* fold section 2's numerator gain into section 1, as the table did */
    g = LP_B[0]; LP_B[0] = 1.0; LP_B[1] /= g; LP_B[2] /= g;
    LP_A[0] *= g; LP_A[1] *= g; LP_A[2] *= g;
}

/* ---- resident state -------------------------------------------------------- */
static unsigned char ring[RING_SIZE];
static volatile unsigned ring_head;          /* ISR reads here                  */
static volatile unsigned ring_tail;          /* synth writes here               */
static volatile unsigned long tick_count;
static unsigned chain_count;
static unsigned char idle_level = 72;

static void (__interrupt __far *old08)(void);
static void (__interrupt __far *old70)(void);
static unsigned char rtc_rate_saved, pic1_saved, pic2_saved;
static void (__interrupt __far *old61)(void);
static unsigned resident_psp;

/* wire decoder */
static unsigned char w_clock, w_data, w_active;
static unsigned char w_bits, w_nbits;
static unsigned char w_cur[16];
static unsigned char w_ncur;
static unsigned char armed = 1;
static unsigned singles;

/* counters for the /S report */
static unsigned n_frames, n_ctrls, n_pitches, n_polls_busy, n_polls_ready;

/* synth */
static struct {
    int furcsa;
    double anchor, pitch;
    double phase;
    double prev_fc[MAX_FORMANTS], prev_bw[MAX_FORMANTS], prev_amp;
    int have_prev;
    double y1[MAX_FORMANTS], y2[MAX_FORMANTS];
    double tilt_y;
    double lz0, lz1, mz0, mz1;
    double hx0, hy0, hx1, hy1, hx2, hy2;
    unsigned long rng;
    double tilt_a, hp_a;
    int fs;
} S;
static unsigned char chip_timing;                /* /C: honour FS bits */
static double out_gain = 1.0;                   /* /Vn: 0.25 .. 5.6 */
static const double GAIN_TAB[10] = {0.25, 0.35, 0.5, 0.71, 1.0, 1.41, 2.0, 2.83, 4.0, 5.66};
static const int FS_MS10[4] = {128, 88, 104, 176};      /* 12.8/8.8/10.4/17.6 ms, in 0.1 ms */

static unsigned char fpu_save[108];
static unsigned char api_stack[3072];
static unsigned saved_ss, saved_sp;
static volatile unsigned char in_api;
static unsigned char api_ah, api_al;
static unsigned api_bx, api_cx, api_dx;

/* ------------------------------------------------------------------------- */
/* timer: one PWM sample per tick, old handler every CHAIN_TICKS              */
/* ------------------------------------------------------------------------- */
static void (__interrupt __far *bios08)(void);   /* the vector at install */
static volatile unsigned char in_chain;
static volatile unsigned char spk_state;         /* SPK_* below                    */
static unsigned idle_ticks;
static unsigned n_underrun;
static unsigned n_overrun;                       /* ring full: sample dropped      */
static unsigned char ramp;
#define RELEASE_TICKS 500                        /* mid-utterance silence before giving it back (~50 ms) */
#define SPK_OFF      0                           /* channel 2 and the gate are not ours */
#define SPK_RAMP_IN  1                           /* easing the line from off to idle    */
#define SPK_PLAY     2
#define SPK_RAMP_OUT 3
#define RAMP_TOP     pwm_top                     /* a full period low = the gated-off level */

/* The speaker is ours only while there is something to say.  A game's own
 * beeps program channel 2 in mode 3; touching 42h while idle would wreck
 * them, and a 50% carrier on a real cone is not silence.  The line is eased
 * between the off level and the idle level over ~12 ms so that taking and
 * releasing the speaker does not thump the cone. */
static void speaker_acquire(void)
{
    outp(0x43, 0x90);                          /* ch2 lobyte, mode 0 one-shot   */
    outp(0x42, RAMP_TOP);
    outp(0x61, inp(0x61) | 3);                 /* gate + speaker data           */
    ramp = RAMP_TOP;
    spk_state = SPK_RAMP_IN;
}

static void speaker_release(void)
{
    outp(0x61, inp(0x61) & ~3);
    outp(0x43, 0xB6);                          /* ch2 back to square-wave mode  */
    spk_state = SPK_OFF;
}

static void speaker_tick(void)
{
    unsigned h = ring_head;
    switch (spk_state) {
    case SPK_OFF:
        if (h != ring_tail) speaker_acquire();
        break;
    case SPK_RAMP_IN:
        if (ramp > idle_level) { if (tick_count & 1) ramp--; outp(0x42, ramp); }
        else { spk_state = SPK_PLAY; idle_ticks = 0; }
        break;
    case SPK_PLAY:
        if (h != ring_tail) {
            outp(0x42, ring[h]);
            ring_head = (h + 1) & RING_MASK;
            idle_ticks = 0;
        } else {
            /* Drained.  After a STOP (armed) the utterance is over: give the
             * speaker back at once, so a game's jingle right after the text
             * finds channel 2 free.  Mid-utterance starvation waits a little. */
            outp(0x42, idle_level);
            if (armed || ++idle_ticks >= RELEASE_TICKS) { spk_state = SPK_RAMP_OUT; ramp = idle_level; }
        }
        break;
    default: /* SPK_RAMP_OUT */
        if (h != ring_tail) spk_state = SPK_RAMP_IN;          /* more to say: ease back in */
        else if (ramp < RAMP_TOP) { if (tick_count & 1) ramp++; outp(0x42, ramp); }
        else speaker_release();
        break;
    }
    tick_count++;
}

/* RTC periodic interrupt, 8192 Hz.  Reading register 0Ch is what lets the
 * chip raise the next one.  Nothing is chained: the BIOS only uses IRQ8 for
 * INT 15h AH=83h/86h waits, which are unavailable while we are resident. */
static void __interrupt __far isr70(void)
{
    outp(0x70, 0x0C);
    inp(0x71);
    speaker_tick();
    outp(0xA0, 0x20);
    outp(0x20, 0x20);
}

/* IRQ0 at 10027 Hz (/I).  TALKHUN hooks INT 08 above us after it loads and
 * saves *our* handler as its old vector.  We re-hook on top so it keeps its
 * 18.2 Hz, chain to it every CHAIN_TICKS, and when it chains straight back
 * into us, pass that call on to the BIOS handler instead of running the tick
 * twice. */
static void __interrupt __far isr08(void)
{
    if (in_chain) {
        in_chain = 0;
        _chain_intr(bios08);
    }
    if (IVT08 != isr08) {                      /* hooked above us since last tick: */
        old08 = IVT08;                         /* the newcomer gets 18.2 Hz through */
        IVT08 = isr08;                         /* us, never our 10 kHz             */
    }
    speaker_tick();
    if (++chain_count >= CHAIN_TICKS) {
        chain_count = 0;
        if (old08 != bios08) in_chain = 1;
        _chain_intr(old08);
    }
    outp(0x20, 0x20);
}

static unsigned queued(void)
{
    return (ring_tail - ring_head) & RING_MASK;
}

static void push_sample(double v)
{
    int c;
    if (v > 1.0) v = 1.0; else if (v < -1.0) v = -1.0;
    c = (int)(pwm_mid + v * pwm_amp);    /* strictly inside 1..period-1      */
    if (c < 2) c = 2; else if (c > pwm_top - 2) c = pwm_top - 2;
    if (((ring_tail + 1) & RING_MASK) == ring_head) { n_overrun++; return; }
    ring[ring_tail] = (unsigned char)c;
    ring_tail = (ring_tail + 1) & RING_MASK;
}

/* ------------------------------------------------------------------------- */
/* synthesis                                                                   */
/* ------------------------------------------------------------------------- */
static void synth_reset(void)
{
    memset(&S, 0, sizeof S);
    S.anchor = S.pitch = 46 * PITCH_HZ_PER_UNIT;
    S.rng = 12345UL;
    S.tilt_a = exp(-2.0 * 3.14159265358979 * TILT_HZ / FS);
    S.hp_a = exp(-2.0 * 3.14159265358979 * HIGHPASS_HZ / FS);
    lp_design(FS);
}

static double soft_knee(double x)
{
    double a = x < 0 ? -x : x, z, t;
    if (a <= SOFTKNEE) return x;
    z = (a - SOFTKNEE) / (1.0 - SOFTKNEE);
    t = 1.0 - 2.0 / (exp(2.0 * z) + 1.0);          /* tanh(z) */
    a = SOFTKNEE + (1.0 - SOFTKNEE) * t;
    return x < 0 ? -a : a;
}

static void frame_params(const unsigned char *f, int furcsa,
                         double *fc, double *bw, double *amp, double *pi, int *noise, int *fd)
{
    int b0 = f[0], b1 = f[1], b2 = f[2], b3 = f[3], b4 = f[4];
    int B1 = (b0 >> 5) & 7, F1 = b0 & 0x1F;
    int F5 = (b1 >> 7) & 1, B5 = (b1 >> 5) & 3, PI = b1 & 0x1F;
    int FD = (((b2 >> 7) & 1) << 1) | ((b3 >> 7) & 1);
    int F3 = (b2 >> 4) & 7, AM = b2 & 0x0F;
    int B3 = (b3 >> 5) & 3, F2 = b3 & 0x1F;
    int B4 = (b4 >> 6) & 3, F4 = (b4 >> 3) & 7, B2 = b4 & 7;
    if (furcsa) {
        fc[0] = FEM_F1[F1]; bw[0] = FEM_B1[B1];
        fc[1] = FEM_F2[F2]; bw[1] = FEM_B2[B2];
        fc[2] = FEM_F3[F3]; bw[2] = FEM_B3[B3];
        fc[3] = FEM_F4[F4]; bw[3] = FEM_B4[B4];
    } else {
        fc[0] = MALE_F1[F1]; bw[0] = MALE_B1[B1];
        fc[1] = MALE_F2[F2]; bw[1] = MALE_B2[B2];
        fc[2] = MALE_F3[F3]; bw[2] = MALE_B3[B3];
        fc[3] = MALE_F4[F4]; bw[3] = MALE_B4[B4];
        fc[4] = MALE_F5[F5]; bw[4] = MALE_B5[B5];
    }
    *amp = AMPL[AM];
    *pi = PI_TAB[PI];
    *noise = (PI == PI_NOISE);
    *fd = FD;
}

/* 2-point PolyBLEP: a band-limited step correction for the sawtooth reset */
static double polyblep(double ph, double dt)
{
    double x;
    if (ph < dt) { x = ph / dt; return x + x - x * x - 1.0; }
    if (ph > 1.0 - dt) { x = (ph - 1.0) / dt; return x * x + x + x + 1.0; }
    return 0.0;
}

static void synth_frame(const unsigned char *f)
{
    double fc[MAX_FORMANTS], bw[MAX_FORMANTS], amp, pi;
    double B1[MAX_FORMANTS], B2[MAX_FORMANTS];
    int noise, fd, nf, n, pos, i;
    double pt, p, a, frac, v, o, x;
    const double two_pi = 6.28318530717958;
    nf = S.furcsa ? 4 : 5;

    frame_params(f, S.furcsa, fc, bw, &amp, &pi, &noise, &fd);
    if (!S.have_prev) {
        for (i = 0; i < nf; i++) { S.prev_fc[i] = fc[i]; S.prev_bw[i] = bw[i]; }
        S.prev_amp = amp;
        S.have_prev = 1;
    }
    n = (int)((chip_timing ? FS_MS10[S.fs & 3] : STD_SAMPLES) * fs_hz / 10000.0 + 0.5) * FD_MULT[fd];
    pt = S.pitch + pi * FD_MULT[fd];
    if (pt < 40.0) pt = 40.0; else if (pt > 400.0) pt = 400.0;

    for (pos = 0; pos < n; pos += BLOCK) {
        int m = n - pos < BLOCK ? n - pos : BLOCK, k;
        frac = (pos + m * 0.5) / n;
        for (i = 0; i < nf; i++) {
            double cf = S.prev_fc[i] + (fc[i] - S.prev_fc[i]) * frac;
            double cb = S.prev_bw[i] + (bw[i] - S.prev_bw[i]) * frac;
            double Bc = exp(-3.14159265358979 * cb / FS);
            B1[i] = Bc * 2.0 * cos(two_pi * cf / FS);
            B2[i] = -(Bc * Bc);
        }
        a = S.prev_amp + (amp - S.prev_amp) * frac;
        p = S.pitch + (pt - S.pitch) * frac;
        for (k = 0; k < m; k++) {
            if (noise) {
                S.rng = S.rng * 1103515245UL + 12345UL;
                v = ((double)((S.rng >> 8) & 0xFFFF) / 65536.0 - 0.5);
            } else {
                double dt = p / FS;
                S.phase += dt;
                if (S.phase >= 1.0) S.phase -= 1.0;
                v = (2.0 * S.phase - 1.0) - polyblep(S.phase, dt);
                v = -0.5 * v;
                S.tilt_y = (1.0 - S.tilt_a) * v + S.tilt_a * S.tilt_y;
                v = S.tilt_y;
            }
            v *= a;
            for (i = 0; i < nf; i++) {
                x = v + B1[i] * S.y1[i] + B2[i] * S.y2[i];
                S.y2[i] = S.y1[i];
                S.y1[i] = x;
                v = x;
            }
            o = LP_A[0] * v + S.lz0;
            S.lz0 = LP_A[1] * v - LP_A[3] * o + S.lz1;
            S.lz1 = LP_A[2] * v - LP_A[4] * o;
            v = LP_B[0] * o + S.mz0;
            S.mz0 = LP_B[1] * o - LP_B[3] * v + S.mz1;
            S.mz1 = LP_B[2] * o - LP_B[4] * v;
            S.hy0 = S.hp_a * (S.hy0 + v - S.hx0); S.hx0 = v; v = S.hy0;
            S.hy1 = S.hp_a * (S.hy1 + v - S.hx1); S.hx1 = v; v = S.hy1;
            S.hy2 = S.hp_a * (S.hy2 + v - S.hx2); S.hx2 = v; v = S.hy2;
            push_sample(soft_knee(v * MAKEUP * out_gain));
        }
    }
    S.pitch = pt;
    for (i = 0; i < nf; i++) { S.prev_fc[i] = fc[i]; S.prev_bw[i] = bw[i]; }
    S.prev_amp = amp;
}

/* ------------------------------------------------------------------------- */
/* the wire: I2C-style start/stop framing, 8 bits MSB first + ack             */
/* ------------------------------------------------------------------------- */
static void transaction_done(void)
{
    const unsigned char *body = w_cur + 1;     /* drop the 0x20 device address */
    int len = (int)w_ncur - 1;
    if (len <= 0) return;
    if (len == 5) {
        n_frames++;
        if (spk_state == SPK_PLAY && idle_ticks) n_underrun++;   /* ring ran dry between frames */
        synth_frame(body);
    } else if (len == 2) {
        unsigned char c = body[1];
        n_ctrls++;
        if (c & 0x80) {
            if (c & 0x20) {                    /* STOP: back at rest            */
                armed = 1;
            } else {
                S.furcsa = (c & 0x10) != 0;    /* M/F: female table, 4 formants */
                S.fs = c & 3;
            }
        }
    } else if (len == 1) {
        if (singles & 1) {                     /* settings nibble, then pitch   */
            n_pitches++;
            S.anchor = S.pitch = body[0] * PITCH_HZ_PER_UNIT;
        }
        singles++;
    }
}

static void wire_step(unsigned char bits)
{
    unsigned char data = bits & 1, clock = (bits >> 1) & 1;
    if (clock && w_clock) {                    /* clock held high: framing     */
        if (w_data && !data) {                 /* START (or repeated START)     */
            if (w_active) transaction_done();
            armed = 0;                         /* addressed: no longer at rest  */
            w_nbits = 0; w_bits = 0; w_ncur = 0; w_active = 1;
        } else if (data && !w_data) {          /* STOP                          */
            if (w_active) transaction_done();
            w_nbits = 0; w_bits = 0; w_ncur = 0; w_active = 0;
        }
    } else if (clock && !w_clock) {            /* rising edge: sample a bit     */
        if (w_nbits < 8) w_bits = (unsigned char)((w_bits << 1) | data);
        if (++w_nbits == 9) {
            if (w_ncur < sizeof w_cur) w_cur[w_ncur++] = w_bits;
            w_nbits = 0; w_bits = 0;
        }
    }
    w_clock = clock;
    w_data = data;
}

static unsigned char poll_status(void)
{
    if (queued() > FIFO_BUSY || armed) { n_polls_busy++; return STATUS_BUSY; }
    n_polls_ready++;
    return STATUS_READY;
}

static void handshake_reset(void)
{
    _disable();
    ring_head = ring_tail = 0;
    _enable();
    armed = 1; singles = 0;
    w_clock = w_data = w_active = 0; w_nbits = w_bits = w_ncur = 0;
    synth_reset();
}

static void __interrupt __far isr61(union INTPACK r);
static void lg(const char *line);

/* Runs on the private stack.  Reads api_ah/api_al, leaves results in api_*. */
static void __cdecl api_dispatch(void)
{
    switch (api_ah) {
    case 0xFF: api_al = poll_status(); break;
    case 0xFE: api_bx = FP_SEG((void __far *)&ring_head); api_cx = FP_SEG((void __far *)isr61); api_dx = resident_psp; break;
    case 0xFD: api_bx = n_ctrls; api_cx = n_pitches; api_dx = queued(); break;
    case 0xFC: handshake_reset(); break;
    default:
        _asm { fsave fpu_save }
        wire_step(api_ah & 3);
        _asm { frstor fpu_save }
        break;
    }
}

static void __interrupt __far isr61(union INTPACK r)
{
    /* TALKHUN may hook INT 08 above us after we load; it expects 18.2 Hz, we
     * deliver 10 kHz.  Heal by re-hooking on top: its handler becomes the one we
     * chain to.  One vector compare per call. */
    if (clock_mode == CLOCK_PIT && IVT08 != isr08) {   /* IF is clear here */
        old08 = IVT08;
        IVT08 = isr08;
    }
    api_ah = r.h.ah; api_al = r.h.al;
    api_bx = r.x.bx; api_cx = r.x.cx; api_dx = r.x.dx;
    if (in_api) {
        api_dispatch();                        /* nested: stay on this stack    */
    } else {
        in_api = 1;
        _asm {
            cli
            mov saved_ss, ss
            mov saved_sp, sp
            mov ax, ds
            mov ss, ax
            mov sp, offset api_stack + 3070
            sti
        }
        api_dispatch();
        _asm {
            cli
            mov ss, saved_ss
            mov sp, saved_sp
            sti
        }
        in_api = 0;
    }
    if (api_ah == 0xFE) { r.x.ax = MAGIC; r.x.bx = api_bx; r.x.cx = api_cx; r.x.dx = api_dx; }
    else if (api_ah == 0xFD) { r.x.ax = n_frames; r.x.bx = api_bx; r.x.cx = api_cx; r.x.dx = api_dx; }
    else r.h.al = api_al;
}

/* ------------------------------------------------------------------------- */
/* install / uninstall / report                                              */
/* ------------------------------------------------------------------------- */
/* 1 = ours is resident, 0 = vector free, -1 = someone else owns INT 61h.
 * The resident copy is this same executable, so its handler starts with the
 * same bytes as ours; compare before calling anything. */
static int find_resident(unsigned *ds, unsigned *cs, unsigned *psp)
{
    union REGS r;
    void (__interrupt __far *v)(void) = _dos_getvect(API_INT);
    if (v == 0) return 0;
    {
        /* Same code as ours?  The resident copy is this executable, so the
         * handler bytes match except the two segment words the loader
         * relocates (mov ax,DGROUP in the prologue, and the CS compare in the
         * INT 08 self-heal).  A bare IRET means the vector is merely parked. */
        const unsigned char far *a = (const unsigned char far *)v;
        const unsigned char far *b = (const unsigned char far *)isr61;
        int k, diff = 0;
        if (a[0] == 0xCF) return 0;
        if (FP_SEG(v) >= 0xF000) return 0;       /* BIOS-parked dummy routine  */
        for (k = 0; k < 32; k++) if (a[k] != b[k]) diff++;
        if (diff > 4) return -1;
    }
    r.h.ah = 0xFE; r.h.al = 0;
    int86(API_INT, &r, &r);
    if (r.x.ax != MAGIC) return 0;
    if (ds) *ds = r.x.bx;
    if (cs) *cs = r.x.cx;
    if (psp) *psp = r.x.dx;
    return 1;
}

static void pit_speech(void)
{
    _disable();
    outp(0x43, 0x34);                          /* ch0 lo/hi, mode 2             */
    outp(0x40, PIT_DIV & 0xFF);
    outp(0x40, PIT_DIV >> 8);
    _enable();
}

static unsigned char cmos_read(unsigned char reg)
{
    outp(0x70, reg);
    outp(0x80, 0);                             /* I/O delay: fast CPU, slow RTC */
    return (unsigned char)inp(0x71);
}
static void cmos_write(unsigned char reg, unsigned char v)
{
    outp(0x70, reg);
    outp(0x80, 0);
    outp(0x71, v);
    outp(0x80, 0);
}
static unsigned char pic_reg(unsigned port, unsigned char ocw3)
{
    outp(port, ocw3);                          /* 0Ah = IRR, 0Bh = ISR         */
    return (unsigned char)inp(port);
}

/* RTC periodic interrupt at 8192 Hz on IRQ8: rate nibble 3, PIE on, IRQ8 and
 * the IRQ2 cascade unmasked.  Vector hooked before the chip is told to fire. */
static void rtc_speech(void)
{
    unsigned char b;
    _disable();
    old70 = _dos_getvect(0x70);
    _dos_setvect(0x70, isr70);
    rtc_rate_saved = cmos_read(0x0A);
    cmos_write(0x0A, (rtc_rate_saved & 0xF0) | RTC_RATE);
    b = cmos_read(0x0B);
    cmos_write(0x0B, b | 0x40);
    cmos_read(0x0C);                           /* clear whatever is pending     */
    pic2_saved = (unsigned char)inp(0xA1); outp(0xA1, pic2_saved & ~1);
    pic1_saved = (unsigned char)inp(0x21); outp(0x21, pic1_saved & ~4);
    _enable();
}

static void rtc_normal(unsigned ds)
{
    unsigned char b;
    _disable();
    b = cmos_read(0x0B);
    cmos_write(0x0B, b & ~0x40);
    cmos_write(0x0A, *(unsigned char far *)MK_FP(ds, (unsigned)&rtc_rate_saved));
    cmos_read(0x0C);
    outp(0xA1, (inp(0xA1) & ~1) | (*(unsigned char far *)MK_FP(ds, (unsigned)&pic2_saved) & 1));
    outp(0x21, (inp(0x21) & ~4) | (*(unsigned char far *)MK_FP(ds, (unsigned)&pic1_saved) & 4));
    _dos_setvect(0x70, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old70));
    outp(0x61, inp(0x61) & ~3);
    outp(0x43, 0xB6);
    _enable();
}

static void pit_normal(void)
{
    _disable();
    outp(0x43, 0x34); outp(0x40, 0); outp(0x40, 0);
    outp(0x61, inp(0x61) & ~3);
    outp(0x43, 0xB6);                          /* ch2 back to square-wave mode  */
    _enable();
}

/* Plain mode-3 beeps for the installer's own messages -- the user of this has
 * no monitor on that machine.  n short beeps, ~90 ms each. */
static void beeps(int n)
{
    volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
    unsigned long t;
    while (n-- > 0) {
        outp(0x43, 0xB6); outp(0x42, 0xA9); outp(0x42, 0x04);   /* ~1 kHz */
        outp(0x61, inp(0x61) | 3);
        t = *bios; while (*bios - t < 2) ;
        outp(0x61, inp(0x61) & ~3);
        t = *bios; while (*bios - t < 2) ;
    }
}

static int uninstall(void)
{
    unsigned ds, cs, psp;
    void (__interrupt __far *v08)(void), (__interrupt __far *v61)(void);
    if (find_resident(&ds, &cs, &psp) != 1) { printf("braispk: not resident\r\n"); return 1; }
    {   /* TALKHUNS still loaded?  Its next utterance would hit a dead INT 61h
         * and its INT 08 hook would be orphaned.  Refuse; reboot instead. */
        union REGS r;
        r.h.ah = 3; r.h.al = 0; r.x.dx = 3; int86(0x14, &r, &r);
        if (r.x.ax == 0x30) {
            printf("braispk: TALKHUNS is still loaded; reboot instead of unloading\r\n");
            return 1;
        }
    }
    v08 = *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old08);
    v61 = _dos_getvect(API_INT);
    if (FP_SEG(v61) != cs) {
        printf("braispk: another program hooked INT 61h after us; cannot unload safely\r\n");
        return 1;
    }
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_PIT) {
        if (v08 != *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&bios08)) {
            printf("braispk: another program hooked INT 08 after us; cannot unload safely\r\n");
            return 1;
        }
        _disable();
        if (*(unsigned char far *)MK_FP(ds, (unsigned)&spk_state)) { outp(0x61, inp(0x61) & ~3); outp(0x43, 0xB6); }
        _dos_setvect(8, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&bios08));
        _dos_setvect(API_INT, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old61));
        _enable();
        pit_normal();
    } else {
        if (FP_SEG(_dos_getvect(0x70)) != cs) {
            printf("braispk: another program hooked INT 70h after us; cannot unload safely\r\n");
            return 1;
        }
        rtc_normal(ds);
        _dos_setvect(API_INT, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old61));
    }
    _dos_freemem(psp);
    printf("braispk: unloaded\r\n");
    return 0;
}

/* /P: a vowel through the whole path -- start sequence, 40 frames, STOP -- fed
 * over INT 61h exactly as TALKHUNS feeds it, with the busy handshake.  Proves
 * the synth and this machine's x87 without loading TALKHUN. */
static void wire(unsigned bits)
{
    union REGS r;
    r.h.ah = (unsigned char)bits; r.h.al = 0;
    int86(API_INT, &r, &r);
}

static void i2c_xfer(const unsigned char *p, int n)
{
    int k, b;
    wire(3); wire(2); wire(0);                 /* idle, START, clock low        */
    for (k = 0; k < n; k++) {
        for (b = 7; b >= 0; b--) { unsigned d = (p[k] >> b) & 1; wire(d); wire(2 | d); wire(d); }
        wire(1); wire(3); wire(1);             /* ack slot                      */
    }
    wire(0); wire(2); wire(3);                 /* STOP                          */
}

static int wait_ready(void)
{
    volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
    unsigned long t0 = *bios, n = 0;
    union REGS r;
    for (;;) {
        r.h.ah = 0xFF; r.h.al = 0; int86(API_INT, &r, &r);
        if (r.h.al == STATUS_READY) return 1;
        if (*bios - t0 > 18 || ++n > 200000L) return 0;
    }
}

static int selftest(void)
{
    static const unsigned char settings[2] = {0x20, 0x00};
    static const unsigned char pitch[2]    = {0x20, 46};           /* 112 Hz  */
    static const unsigned char ctl_go[3]   = {0x20, 0x00, 0x80};
    static const unsigned char ctl_stop[3] = {0x20, 0x00, 0xA0};
    unsigned char frame[6] = {0x20, 0x75, 0x40, 0x3D, 0x4D, 0x93};  /* an /a/  */
    int k;
    union REGS r;
    if (find_resident(0, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
    lg("P1 self-test: start sequence");
    i2c_xfer(settings, 2);
    i2c_xfer(pitch, 2);
    i2c_xfer(ctl_go, 3);
    lg("P2 start sequence sent, frames follow");
    for (k = 0; k < 40; k++) {
        if (!wait_ready()) { lg("P! adapter never became ready"); printf("braispk: adapter never became ready\r\n"); return 1; }
        frame[2] = (unsigned char)(k < 30 ? 0x40 : 0x5D);          /* PI: fall at the end */
        i2c_xfer(frame, 6);
        if (k == 0) lg("P3 first frame synthesised");
        if (k == 9) lg("P4 ten frames");
        if (k == 29) lg("P5 thirty frames");
    }
    lg("P6 all forty frames sent, STOP follows");
    i2c_xfer(ctl_stop, 3);
    do { r.h.ah = 0xFD; int86(API_INT, &r, &r); } while (r.x.dx);
    lg("P7 drained, self-test done");
    printf("braispk: self-test played\r\n");
    return 0;
}

/* /L: breadcrumbs for a machine with no monitor.  One open/write/close per
 * line, so the directory entry is up to date if the next step freezes the
 * box; the file is read back under Windows after the reboot. */
static int logging, log_failed;
static void lg(const char *line)
{
    int h;
    unsigned n;
    if (!logging) return;
    if (_dos_open("BRAISPK.LOG", O_WRONLY, &h) != 0 &&
        _dos_creat("BRAISPK.LOG", _A_NORMAL, &h) != 0) {
        if (!log_failed) { log_failed = 1; beeps(4); }
        return;
    }
    lseek(h, 0L, SEEK_END);
    _dos_write(h, line, strlen(line), &n);
    _dos_write(h, "\r\n", 2, &n);
    _dos_close(h);
}

static int report(void)
{
    union REGS r;
    unsigned ds;
    if (find_resident(&ds, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
    r.h.ah = 0xFD; int86(API_INT, &r, &r);
    printf("braispk: %s clock; frames %u  controls %u  pitches %u  queued %u samples\r\n",
           *(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_PIT ? "IRQ0 10027 Hz" : "RTC 8192 Hz",
           r.x.ax, r.x.bx, r.x.cx, r.x.dx);
    printf("         polls busy %u  ready %u  ticks %lu  armed %u  underruns %u  overruns %u\r\n",
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_busy),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_ready),
           *(unsigned long far *)MK_FP(ds, (unsigned)&tick_count),
           *(unsigned char far *)MK_FP(ds, (unsigned)&armed),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_underrun),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_overrun));
    return 0;
}

static char logbuf[160];

int main(int argc, char **argv)
{
    unsigned sp_now, top, paras;
    unsigned far *bda_lpt1 = (unsigned far *)MK_FP(0x40, 0x08);
    int i;

    _control87(_MCW_EM, _MCW_EM);              /* no FPU traps, whatever Windows left */
    for (i = 1; i < argc; i++) {
        if (argv[i][0] == '/' || argv[i][0] == '-') {
            switch (argv[i][1] & 0xDF) {
            case 'U': return uninstall();
            case 'C': chip_timing = 1; break;
            case 'V': if (argv[i][2] >= '0' && argv[i][2] <= '9') out_gain = GAIN_TAB[argv[i][2] - '0']; break;
            case 'S': return report();
            case 'D': {                       /* debug: what does the resident check see */
                union REGS r; int k;
                void (__interrupt __far *v)(void) = _dos_getvect(API_INT);
                const unsigned char far *a = (const unsigned char far *)v;
                const unsigned char far *b = (const unsigned char far *)isr61;
                printf("vector %04X:%04X  ours %04X:%04X\r\n", FP_SEG(v), FP_OFF(v), FP_SEG(b), FP_OFF(b));
                printf("at vector:"); for (k = 0; k < 32; k++) printf(" %02X", a[k]); printf("\r\n");
                printf("ours     :"); for (k = 0; k < 32; k++) printf(" %02X", b[k]); printf("\r\n");
                r.h.ah = 0xFE; r.h.al = 0; int86(API_INT, &r, &r);
                printf("identify AX=%04X BX=%04X CX=%04X DX=%04X  find=%d\r\n", r.x.ax, r.x.bx, r.x.cx, r.x.dx, find_resident(0,0,0));
                return 0;
            }
            case 'P': return selftest();
            case 'L': {
                unsigned msw;
                logging = 1;
                _asm {
                    smsw ax
                    mov  msw, ax
                }
                sprintf(logbuf, "--- braispk 0.7: %s  DOS %d.%02d  PSP %04X  MSW %04X  FPU CW %04X SW %04X",
                        argv[0], _osmajor, _osminor, _psp, msw, _control87(0, 0), _clear87());
                lg(logbuf);
                break;
            }
            case 'N': lg("N alive, one beep, exit"); beeps(1); return 0;
            case 'I': clock_mode = CLOCK_PIT; break;
            case 'R': { union REGS r; r.h.ah = 0xFC; if (find_resident(0,0,0) != 1) { printf("not resident\r\n"); return 1; } int86(API_INT, &r, &r); printf("reset\r\n"); return 0; }
            default:
                printf("BRAISPK -- BraiLab speech adapter on the PC speaker\r\n"
                       "  BRAISPK        install (then load TALKHUNS.COM)\r\n"
                       "  BRAISPK /C     chip timing: frame length from the FS bits (8.8 ms at ESC S6)\r\n"
                       "  BRAISPK /Vn    output level 0..9 (5 = as the NVDA voice, 7 = twice)\r\n"
                       "  BRAISPK /P     self-test: a vowel through the synth, no TALKHUN needed\r\n"
                       "  BRAISPK /I     clock the samples from IRQ0 at 10027 Hz instead of the RTC at 8192\r\n"
                       "  BRAISPK /L     install with breadcrumbs in BRAISPK.LOG (no monitor)\r\n"
                       "  BRAISPK /N     do nothing but beep once: proves the program runs\r\n"
                       "  BRAISPK /S     show counters\r\n"
                       "  BRAISPK /R     reset handshake and queue\r\n"
                       "  BRAISPK /U     unload\r\n"
                       "  BRAISPK /D     debug: show what the resident check sees\r\n");
                return 0;
            }
        }
    }
    i = find_resident(0, 0, 0);
    if (logging) {
        void (__interrupt __far *v)(void) = _dos_getvect(API_INT);
        sprintf(logbuf, "2 INT 61h vector %04X:%04X -> %s; INT 08 vector %04X:%04X; BDA LPT1 %04X",
                FP_SEG(v), FP_OFF(v), i == 0 ? "free" : i == 1 ? "ours" : "FOREIGN",
                FP_SEG(_dos_getvect(8)), FP_OFF(_dos_getvect(8)), *bda_lpt1);
        lg(logbuf);
    }
    if (i == 1) { printf("braispk: already resident\r\n"); beeps(2); return 1; }
    if (i == -1) { printf("braispk: INT %02Xh is already in use by another program; not installing\r\n", API_INT); beeps(3); return 1; }

    if (*bda_lpt1 == 0) *bda_lpt1 = 0x378;     /* TALKHUN refuses to bind to LPT 0 */
    resident_psp = _psp;
    synth_reset();
    old61 = _dos_getvect(API_INT);
    old08 = bios08 = _dos_getvect(8);
    _dos_setvect(API_INT, isr61);
    lg("3 INT 61h hooked");
    if (clock_mode == CLOCK_PIT) {
        fs_hz = 10027.0; pwm_top = 119; pwm_mid = 60; pwm_amp = 57; idle_level = 60;
        synth_reset();
        pit_speech();
        _dos_setvect(8, isr08);
        lg("4 PIT channel 0 at 10027 Hz, INT 08 hooked");
    } else {
        fs_hz = 8192.0; pwm_top = 144; pwm_mid = 72; pwm_amp = 69; idle_level = 72;
        synth_reset();
        if (logging) {
            sprintf(logbuf, "4 RTC: INT 70h was %04X:%04X, reg 0Ah %02X, reg 0Bh %02X, PIC masks %02X/%02X",
                    FP_SEG(_dos_getvect(0x70)), FP_OFF(_dos_getvect(0x70)),
                    cmos_read(0x0A), cmos_read(0x0B), inp(0x21), inp(0xA1));
            lg(logbuf);
        }
        rtc_speech();
        if (logging) {
            sprintf(logbuf, "4 RTC on: reg 0Ah now %02X (want x3), reg 0Bh now %02X (bit 6 set), PIC masks %02X/%02X, INT 70h %04X:%04X",
                    cmos_read(0x0A), cmos_read(0x0B), inp(0x21), inp(0xA1),
                    FP_SEG(_dos_getvect(0x70)), FP_OFF(_dos_getvect(0x70)));
            lg(logbuf);
        }
    }
    if (logging) {                             /* does the interrupt reach us; does the BIOS tick go on */
        volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
        unsigned long t0 = *bios, n = 0, c0 = tick_count;
        while (tick_count - c0 < 3000 && ++n < 5000000L) ;
        sprintf(logbuf, "5 after %lu loops: our ticks %lu, BIOS ticks +%lu (want 3000 and 5..7); PIC IRR/ISR master %02X/%02X slave %02X/%02X",
                n, tick_count - c0, *bios - t0,
                pic_reg(0x20, 0x0A), pic_reg(0x20, 0x0B), pic_reg(0xA0, 0x0A), pic_reg(0xA0, 0x0B));
        lg(logbuf);
    }
    {                                          /* audible "resident" chirp       */
        int k;
        for (k = 0; k < 700; k++) push_sample(0.6 * sin(k * 6.28318530717958 * 440.0 / FS));
        for (k = 0; k < 700; k++) push_sample(0.6 * sin(k * 6.28318530717958 * 660.0 / FS));
    }
    if (logging) {                             /* did the chirp drain: the speaker path ran */
        volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
        unsigned long t0 = *bios, n = 0;
        while (queued() && *bios - t0 < 18 && ++n < 2000000L) ;
        sprintf(logbuf, "6 chirp: %u samples still queued after %lu BIOS ticks, speaker state %u",
                queued(), *bios - t0, spk_state);
        lg(logbuf);
    }
    lg("7 going resident");

    /* free the environment, keep PSP..top of our stack resident */
    _dos_freemem(*(unsigned far *)MK_FP(_psp, 0x2C));
    _asm { mov sp_now, sp }
    top = sp_now + 512;                        /* we are near the top of DGROUP  */
    paras = (unsigned)((((unsigned long)FP_SEG((void __far *)&ring_head) << 4) + top - ((unsigned long)_psp << 4) + 15) >> 4);
    printf("braispk: resident, %u KB, %s PWM on the PC speaker, API INT %02Xh, level x%d.%02d%s\r\n",
           (paras + 63) / 64, clock_mode == CLOCK_PIT ? "10027 Hz IRQ0" : "8192 Hz RTC",
           API_INT, (int)out_gain, (int)(out_gain * 100) % 100,
           chip_timing ? ", chip frame timing" : "");
    fflush(stdout);                            /* _dos_keep does not flush     */
    _dos_keep(0, paras);
    return 0;
}
