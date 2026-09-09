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

#define MAGIC        0xB7A1
#define API_INT      0x61
#define PIT_DIV      119            /* 1193182 / 119 = 10027 Hz               */
#define CHAIN_TICKS  551            /* 10027 / 18.2065 -> old INT 08 at 18.2  */
#define FS           10027.0        /* the actual sample rate we run at        */

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
/* butter(4, 2600, 'low', fs=10000) as two second-order sections */
static const double LP_A[5] = {0.10631234573760745, 0.2126246914752149, 0.10631234573760745, 0.06533681044002995, 0.04055215548149342};
static const double LP_B[5] = {1.0, 2.0, 1.0, 0.09087377369825426, 0.4472530945667702};

/* ---- resident state -------------------------------------------------------- */
static unsigned char ring[RING_SIZE];
static volatile unsigned ring_head;          /* ISR reads here                  */
static volatile unsigned ring_tail;          /* synth writes here               */
static volatile unsigned long tick_count;
static unsigned chain_count;
static unsigned char idle_level = 60;

static void (__interrupt __far *old08)(void);
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
static const int FS_SAMPLES[4] = {128, 88, 104, 176};   /* 12.8/8.8/10.4/17.6 ms */

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

static void __interrupt __far isr08(void)
{
    unsigned h;
    /* TALKHUN hooks INT 08 above us after it loads and saved *our* handler as
     * its old vector.  We re-hook on top so it keeps its 18.2 Hz, chain to it
     * every CHAIN_TICKS, and when it chains straight back into us, pass that
     * call on to the BIOS handler instead of running the tick twice. */
    if (in_chain) {
        in_chain = 0;
        _chain_intr(bios08);
    }
    h = ring_head;
    if (h != ring_tail) {
        outp(0x42, ring[h]);
        ring_head = (h + 1) & RING_MASK;
    } else {
        outp(0x42, idle_level);
    }
    tick_count++;
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
    c = (int)(60.0 + v * 57.0);          /* 3..117, strictly inside 1..118   */
    if (c < 2) c = 2; else if (c > 117) c = 117;
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
    n = (chip_timing ? FS_SAMPLES[S.fs & 3] : STD_SAMPLES) * FD_MULT[fd];
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
    if (_dos_getvect(8) != isr08) {
        old08 = _dos_getvect(8);
        _dos_setvect(8, isr08);
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
static int find_resident(unsigned *ds, unsigned *cs, unsigned *psp)
{
    union REGS r;
    void (__interrupt __far *v)(void) = _dos_getvect(API_INT);
    if (v == 0) return 0;
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
    outp(0x43, 0x90);                          /* ch2 lobyte, mode 0 one-shot   */
    outp(0x42, idle_level);
    outp(0x61, inp(0x61) | 3);                 /* gate + speaker data           */
    outp(0x43, 0x34);                          /* ch0 lo/hi, mode 2             */
    outp(0x40, PIT_DIV & 0xFF);
    outp(0x40, PIT_DIV >> 8);
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

static int uninstall(void)
{
    unsigned ds, cs, psp;
    void (__interrupt __far *v08)(void), (__interrupt __far *v61)(void);
    if (!find_resident(&ds, &cs, &psp)) { printf("braispk: not resident\r\n"); return 1; }
    v08 = _dos_getvect(8); v61 = _dos_getvect(API_INT);
    if (FP_SEG(v08) != cs || FP_SEG(v61) != cs) {
        printf("braispk: another program hooked INT 08 or INT 61 after us; cannot unload safely\r\n");
        return 1;
    }
    _disable();
    _dos_setvect(8, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&bios08));
    _dos_setvect(API_INT, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old61));
    _enable();
    pit_normal();
    _dos_freemem(psp);
    printf("braispk: unloaded\r\n");
    return 0;
}

static int report(void)
{
    union REGS r;
    unsigned ds;
    if (!find_resident(&ds, 0, 0)) { printf("braispk: not resident\r\n"); return 1; }
    r.h.ah = 0xFD; int86(API_INT, &r, &r);
    printf("braispk: frames %u  controls %u  pitches %u  queued %u samples\r\n", r.x.ax, r.x.bx, r.x.cx, r.x.dx);
    printf("         polls busy %u  ready %u  ticks %lu  armed %u\r\n",
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_busy),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_ready),
           *(unsigned long far *)MK_FP(ds, (unsigned)&tick_count),
           *(unsigned char far *)MK_FP(ds, (unsigned)&armed));
    return 0;
}

int main(int argc, char **argv)
{
    unsigned sp_now, top, paras;
    unsigned far *bda_lpt1 = (unsigned far *)MK_FP(0x40, 0x08);
    int i;

    for (i = 1; i < argc; i++) {
        if (argv[i][0] == '/' || argv[i][0] == '-') {
            switch (argv[i][1] & 0xDF) {
            case 'U': return uninstall();
            case 'C': chip_timing = 1; break;
            case 'V': if (argv[i][2] >= '0' && argv[i][2] <= '9') out_gain = GAIN_TAB[argv[i][2] - '0']; break;
            case 'S': return report();
            case 'R': { union REGS r; r.h.ah = 0xFC; if (!find_resident(0,0,0)) { printf("not resident\r\n"); return 1; } int86(API_INT, &r, &r); printf("reset\r\n"); return 0; }
            default:
                printf("BRAISPK -- BraiLab speech adapter on the PC speaker\r\n"
                       "  BRAISPK        install (then load TALKHUNS.COM)\r\n"
                       "  BRAISPK /C     chip timing: frame length from the FS bits (8.8 ms at ESC S6)\r\n"
                       "  BRAISPK /Vn    output level 0..9 (5 = as the NVDA voice, 7 = twice)\r\n"
                       "  BRAISPK /S     show counters\r\n"
                       "  BRAISPK /R     reset handshake and queue\r\n"
                       "  BRAISPK /U     unload\r\n");
                return 0;
            }
        }
    }
    if (find_resident(0, 0, 0)) { printf("braispk: already resident\r\n"); return 1; }

    if (*bda_lpt1 == 0) *bda_lpt1 = 0x378;     /* TALKHUN refuses to bind to LPT 0 */
    resident_psp = _psp;
    synth_reset();
    old61 = _dos_getvect(API_INT);
    old08 = bios08 = _dos_getvect(8);
    _dos_setvect(API_INT, isr61);
    pit_speech();
    _dos_setvect(8, isr08);

    /* free the environment, keep PSP..top of our stack resident */
    _dos_freemem(*(unsigned far *)MK_FP(_psp, 0x2C));
    _asm { mov sp_now, sp }
    top = sp_now + 512;                        /* we are near the top of DGROUP  */
    paras = (unsigned)((((unsigned long)FP_SEG((void __far *)&ring_head) << 4) + top - ((unsigned long)_psp << 4) + 15) >> 4);
    printf("braispk: resident, %u KB, 10027 Hz PWM on the PC speaker, API INT %02Xh, level x%d.%02d%s\r\n",
           (paras + 63) / 64, API_INT, (int)out_gain, (int)(out_gain * 100) % 100,
           chip_timing ? ", chip frame timing" : "");
    fflush(stdout);                            /* _dos_keep does not flush     */
    _dos_keep(0, paras);
    return 0;
}
