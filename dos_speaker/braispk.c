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
 *   AH = FAh          test tone: BX = Hz (0 = noise), CX = samples wanted
 *                     (<= 1024); AX = samples pushed, 0 = ring has no room
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
/* IRQ0 modes: /I = 1193182/119 = 10027 Hz, one sample per tick, 119 levels;
 * /H = 1193182/60 = 19886 Hz, two ticks per sample (linear interpolation
 * between samples), 58 levels: the carrier is above hearing instead of the
 * 8 kHz television whistle of the RTC route.  The old INT 08 is chained
 * every chain_ticks so the BIOS keeps its 18.2 Hz. */
static unsigned pit_div = 119, chain_ticks = 551;
static unsigned char ticks_per_sample = 1, ramp_mask = 1;
#define RTC_RATE     3              /* CMOS reg 0Ah rate 3 = 8192 Hz (RTC mode) */

/* Which interrupt carries the samples.  RTC (IRQ8) is the default: it leaves
 * PIT channel 0, the BIOS tick, IO.SYS's and TALKHUN's INT 08 hooks alone.
 * On the first real machine (Pentium 166, Windows 98 DOS) the IRQ0 route
 * played the chirp but the BIOS tick stopped advancing while it ran, and the
 * box froze on the first utterance; IO.SYS sits on INT 08 there and DOSBox
 * has nothing on it, so that chain was never exercised before. */
#define CLOCK_RTC    1
#define CLOCK_PIT    0
#define CLOCK_PIT_HI 2
#define CLOCK_CARD   3      /* /A: no speaker at all -- the bytes go to a real
                             * PCF8200 on the PC-ROBOT ISA card (Nikol, 1993) */
static unsigned card_port = 0x100;
static int dac_override = -1;           /* /Gxx: DAC code to send instead of the driver's (70h = max) */
static int card_write(unsigned char b);
static char logbuf[200];
static unsigned char clock_mode = CLOCK_PIT_HI;   /* /8 = RTC, /I = IRQ0 at 10 kHz */
static unsigned char bios_bypass;   /* IRQ0 modes: chain to the BIOS entry, not IO.SYS */
static unsigned char force_bypass;  /* /X: take that path even when nothing hooks INT 08 */
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
#define LP_HZ         2600.0            /* voiced frames: tames F5 on the harmonic source */
/* Noise frames: f, s, c live above 3 kHz; the 2600 Hz cut made "c" and "f"
 * the same dull puff (0.26), 4600 Hz made "sz" too sharp (0.27).  /Jn picks
 * the cutoff, 3600 by default. */
static double noise_lp_hz = 3600.0;
static const double NOISE_LP_TAB[10] = {2600, 3000, 3200, 3400, 3600, 3800, 4000, 4300, 4600, 4950};
#define CUT_HZ        300.0
static double LP_A[5], LP_B[5], LPN_A[5], LPN_B[5], CUT_C[5];
static void hp_design(double fc, double fs, double *C)
{
    double w0 = 2.0 * 3.14159265358979 * fc / fs, c = cos(w0), sn = sin(w0);
    double alpha = sn / (2.0 * 0.7071), a0 = 1.0 + alpha;
    C[0] = (1.0 + c) / 2.0 / a0; C[1] = -(1.0 + c) / a0; C[2] = C[0];
    C[3] = -2.0 * c / a0; C[4] = (1.0 - alpha) / a0;
}
static void lp_design(double fs, double hz, double *LP_A, double *LP_B)
{
    static const double Q[2] = {0.54119610014619701, 1.3065629648763764};
    double w0 = 2.0 * 3.14159265358979 * hz / fs, c = cos(w0), sn = sin(w0);
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
static void (__interrupt __far *orig08)(void);   /* what the IVT held at install */
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
    double cB1[MAX_FORMANTS], cB2[MAX_FORMANTS], ca, cp;   /* the ramped values, per sample */
    double lpA[5], lpB[5];                     /* the output low-pass, ramped per sample too */
    double tilt_y;
    double lz0, lz1, mz0, mz1;
    double hx0, hy0, hx1, hy1, hx2, hy2;
    double cz0, cz1;                           /* the 300 Hz cut's state         */
    unsigned long rng;
    double tilt_a, hp_a;
    int fs;
} S;
static unsigned char chip_timing;                /* /C: honour FS bits */
static double out_gain = 8.0;                   /* /Vn below; default /V8 = x8: a cone wants drive */
static const double GAIN_TAB[10] = {0.5, 0.71, 1.0, 1.41, 2.0, 2.83, 4.0, 5.66, 8.0, 11.3};
static unsigned char full_range;                /* /F: keep the fundamental (no 300 Hz cut) */
static unsigned char gain_set;                  /* /V given: do not apply a mode's default  */
#define OUT_SPEAKER  0
#define OUT_SB       1
#define OUT_LPT      2                          /* /E: an 8-bit DAC on the printer port (Covox) */
static unsigned lpt_port;                       /* 0 = BIOS LPT1                           */
static unsigned char out_dev = OUT_SPEAKER;     /* /B: the Sound Blaster DAC, not the speaker */
static unsigned sb_port = 0x220;
static unsigned char sb_from_env;               /* /B without a port: BLASTER=A... decides */
static unsigned char sb_ver_hi, sb_ver_lo;      /* DSP version (command E1h)               */
static unsigned char mix_master_saved, mix_voice_saved, mix_filter_saved;
static unsigned n_dac_busy;                     /* DSP not ready at a tick: a wait or a lost tick */
static unsigned char dac_playing;
static unsigned char dac_cmd;                   /* command 10h sent, its sample byte still owed  */
static unsigned char dac_next;                  /* that sample byte                              */
static void (__interrupt __far *old2f)(void);   /* Windows start/exit broadcasts           */
static volatile unsigned char suspended;        /* Windows is running: we stay out of it   */
static unsigned n_win;                          /* suspend/resume pairs seen               */
static void pit_speech(void);
static void pit_normal(void);
static void rtc_speech(void);
static void rtc_normal(unsigned ds);
static unsigned char cmos_read(unsigned char reg);
static void cmos_write(unsigned char reg, unsigned char v);
static unsigned char far *dos_con_flag(void);
static unsigned dos_ds;                         /* DOS 7 data segment (INT 21h AH=52h)     */
static unsigned char dos_con_saved;             /* its console flag byte as found          */
static unsigned char dos_con_touch = 1;         /* /T: leave that flag alone               */
#define DOS_CON_FLAG 0x86                       /* IO.SYS 7.1: bit 4 = fast path armed, bit 3 = never arm it */
static unsigned char dac_wide;                  /* /W: a command+sample pair EVERY tick (19886 Hz, interpolated) */
static unsigned char keep_filter;               /* /O: leave the card's output filter as found   */
static unsigned n_dac_wait;                     /* DSP not ready at first look (but within the bound) */
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
        if (ramp > idle_level) { if ((tick_count & ramp_mask) == 0) ramp--; outp(0x42, ramp); }
        else { spk_state = SPK_PLAY; idle_ticks = 0; }
        break;
    case SPK_PLAY:
        if (h != ring_tail) {
            if (ticks_per_sample == 2 && (tick_count & 1)) {
                unsigned n2 = (h + 1) & RING_MASK;           /* odd tick: halfway   */
                unsigned char b = (n2 != ring_tail) ? ring[n2] : ring[h];
                outp(0x42, (unsigned char)(((unsigned)ring[h] + b) >> 1));
                ring_head = n2;
            } else {
                outp(0x42, ring[h]);
                if (ticks_per_sample == 1) ring_head = (h + 1) & RING_MASK;
            }
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
        else if (ramp < RAMP_TOP) { if ((tick_count & ramp_mask) == 0) ramp++; outp(0x42, ramp); }
        else speaker_release();
        break;
    }
    tick_count++;
}

/* ------------------------------------------------------------------------- */
/* /B: the Sound Blaster DAC instead of the speaker.  Direct mode -- DSP      */
/* command 10h, one byte per sample -- paced by the same IRQ0/RTC tick as the */
/* speaker path.  No DMA, no sound-card IRQ, nothing else in the machine      */
/* touched.  The Yamaha OPL3-SA on the Pentium 166 is Sound Blaster Pro       */
/* class; its DSP answered every /Z scan so far (22Ah read AAh, the reset     */
/* signature) -- all after a restart from Windows into DOS mode.              */
/* ------------------------------------------------------------------------- */
static int dsp_write(unsigned char b)
{
    unsigned n;
    for (n = 0; n < 20000; n++)
        if (!(inp(sb_port + 0xC) & 0x80)) { outp(sb_port + 0xC, b); return 1; }
    return 0;
}

static int dsp_read(unsigned char *b)
{
    unsigned n;
    for (n = 0; n < 20000; n++)
        if (inp(sb_port + 0xE) & 0x80) { *b = (unsigned char)inp(sb_port + 0xA); return 1; }
    return 0;
}

static unsigned char mixer_read(unsigned char reg)
{
    outp(sb_port + 4, reg); outp(0x80, 0);
    return (unsigned char)inp(sb_port + 5);
}

static void mixer_write(unsigned char reg, unsigned char v)
{
    outp(sb_port + 4, reg); outp(0x80, 0);
    outp(sb_port + 5, v); outp(0x80, 0);
}

/* Reset the DSP (AAh comes back within 100 us), ask its version, open the
 * output: mixer master and voice to full, the SB Pro output low-pass (about
 * 3 kHz -- that would be "tompa" all over again, from a new cause) bypassed,
 * speaker on, DAC parked at mid-scale. */
static int sb_open(void)
{
    unsigned char b = 0;
    int k;
    outp(sb_port + 6, 1);
    for (k = 0; k < 8; k++) outp(0x80, 0);         /* >= 3 us                       */
    outp(sb_port + 6, 0);
    if (!dsp_read(&b) || b != 0xAA) return 0;
    sb_ver_hi = sb_ver_lo = 0;
    if (dsp_write(0xE1)) { dsp_read(&sb_ver_hi); dsp_read(&sb_ver_lo); }
    mix_master_saved = mixer_read(0x22);
    mix_voice_saved  = mixer_read(0x04);
    mix_filter_saved = mixer_read(0x0E);
    mixer_write(0x22, 0xEE);
    mixer_write(0x04, 0xEE);
    if (!keep_filter) mixer_write(0x0E, mix_filter_saved | 0x20);
    dsp_write(0xD1);                               /* speaker (DAC output) on       */
    dsp_write(0x10); dsp_write(0x80);
    return 1;
}

/* Unload: sb_port and the three saved mixer bytes were fetched from the
 * resident copy by the caller. */
static void sb_close(void)
{
    dsp_write(0x10); dsp_write(0x80);
    dsp_write(0xD3);                               /* speaker off                   */
    mixer_write(0x22, mix_master_saved);
    mixer_write(0x04, mix_voice_saved);
    mixer_write(0x0E, mix_filter_saved);
}

/* The DSP's write buffer must be free before EVERY byte, the command and the
 * sample alike; a byte written while it is busy is simply lost, and after a
 * direct-DAC command the DSP stays busy for tens of microseconds (the
 * documented 23 kHz ceiling for this mode).  Lose a sample byte and the next
 * command byte becomes the sample and the next sample a command: DC and
 * chaos.  So on the 19.9 kHz clock the command goes out on the even tick and
 * the sample on the odd one -- 9943 samples a second, the synth's own rate,
 * no interpolation, no spinning -- and on the one-tick clocks the sample
 * follows the command after a bounded wait.  A sample byte still owed is
 * retried before anything else.  Nothing is written while there is nothing
 * to say: the DAC holds mid-scale, so there is no ramp and no click. */
static int dac_ready(int spins)
{
    if (!(inp(sb_port + 0xC) & 0x80)) return 1;
    n_dac_wait++;
    while (--spins > 0) if (!(inp(sb_port + 0xC) & 0x80)) return 1;
    return 0;
}

static void dac_tick(void)
{
    unsigned char two = (unsigned char)(ticks_per_sample == 2), odd = (unsigned char)(tick_count & 1);
    if (dac_wide && two) {
        /* /W: the pair every tick, 19886 samples a second with the halfway
         * value on the odd ticks, so the DAC's images sit above 15 kHz.  The
         * documented direct-DAC ceiling is 23 kHz, so a real DSP should keep
         * up; the wait count in /S says whether it had to be waited for. */
        unsigned h = ring_head;
        unsigned char s;
        if (dac_cmd) {
            if (dac_ready(40)) { outp(sb_port + 0xC, dac_next); dac_cmd = 0; }
            else { n_dac_busy++; goto done; }
        }
        if (!dac_ready(1)) { n_dac_busy++; goto done; }
        if (h != ring_tail) {
            if (odd) {
                unsigned n2 = (h + 1) & RING_MASK;
                unsigned char b = (n2 != ring_tail) ? ring[n2] : ring[h];
                s = (unsigned char)(((unsigned)ring[h] + b) >> 1);
                ring_head = n2;
            } else s = ring[h];
            dac_playing = 1;
        } else if (dac_playing) { s = 0x80; dac_playing = 0; }
        else goto done;
        outp(sb_port + 0xC, 0x10);
        dac_next = s; dac_cmd = 1;
        if (dac_ready(40)) { outp(sb_port + 0xC, s); dac_cmd = 0; }
        else n_dac_busy++;
        goto done;
    }
    if (dac_cmd && (!two || odd)) {                  /* the byte owed from last time  */
        if (dac_ready(two ? 40 : 60)) { outp(sb_port + 0xC, dac_next); dac_cmd = 0; }
        else n_dac_busy++;
    }
    if (!dac_cmd && (!two || !odd)) {
        unsigned h = ring_head;
        unsigned char s;
        if (h != ring_tail) s = ring[h];
        else if (dac_playing) s = 0x80;                /* drained: park mid-scale       */
        else goto done;
        if (dac_ready(1)) {
            outp(sb_port + 0xC, 0x10);
            dac_cmd = 1; dac_next = s;
            if (h != ring_tail) { ring_head = (h + 1) & RING_MASK; dac_playing = 1; }
            else dac_playing = 0;
            if (!two) {                                /* one-tick clocks: byte now     */
                if (dac_ready(60)) { outp(sb_port + 0xC, s); dac_cmd = 0; }
                else n_dac_busy++;
            }
        } else n_dac_busy++;
    }
done:
    tick_count++;
}

/* /E: a resistor-ladder DAC on the printer port -- Covox Speech Thing and its
 * clones, the way ReadBoard and the Polish readers spoke.  No handshake, no
 * chip: the byte on the data lines IS the voltage.  One OUT per tick, the
 * halfway value on the odd ticks of the 19.9 kHz clock. */
static void lpt_tick(void)
{
    unsigned h = ring_head;
    if (h != ring_tail) {
        unsigned char s;
        if (ticks_per_sample == 2 && (tick_count & 1)) {
            unsigned n2 = (h + 1) & RING_MASK;
            unsigned char b = (n2 != ring_tail) ? ring[n2] : ring[h];
            s = (unsigned char)(((unsigned)ring[h] + b) >> 1);
            ring_head = n2;
        } else {
            s = ring[h];
            if (ticks_per_sample == 1) ring_head = (h + 1) & RING_MASK;
        }
        outp(lpt_port, s);
        dac_playing = 1;
    } else if (dac_playing) {
        outp(lpt_port, 0x80);
        dac_playing = 0;
    }
    tick_count++;
}

static void out_tick(void)
{
    if (out_dev == OUT_SB) dac_tick(); else if (out_dev == OUT_LPT) lpt_tick(); else speaker_tick();
}

/* Windows 3.x/9x announces itself on INT 2Fh: AX=1605h when it starts,
 * 1606h when it exits.  While it runs it owns the timer, the PIC and the
 * sound chip, and on the way out it puts back what it found at start: an
 * 18.2 Hz PIT under a handler expecting 19886 ticks a second, so the BIOS
 * tick and TALKHUN's pump crawled a thousand times too slow and the prompt
 * "froze".  Suspend on the way in (timer normal, DAC parked, DOS console
 * flag put back), resume on the way out (everything re-armed). */
static void win_suspend(void)
{
    unsigned char far *f;
    if (suspended || clock_mode == CLOCK_CARD) return;
    suspended = 1;
    if (clock_mode == CLOCK_RTC) {
        unsigned char b = cmos_read(0x0B);
        cmos_write(0x0B, b & ~0x40);
        cmos_write(0x0A, rtc_rate_saved);
        cmos_read(0x0C);
    } else pit_normal();
    if (out_dev == OUT_SB) sb_close();
    spk_state = SPK_OFF; dac_cmd = 0; dac_playing = 0;
    if (dos_con_touch && (f = dos_con_flag()) != 0) *f = (unsigned char)((*f & ~0x08) | (dos_con_saved & 0x08));
}

static void win_resume(void)
{
    unsigned char far *f;
    if (!suspended) return;
    ring_head = ring_tail; armed = 1;
    chain_count = 0; in_chain = 0;
    if (out_dev == OUT_SB) sb_open();
    if (clock_mode == CLOCK_RTC) {
        unsigned char b;
        cmos_write(0x0A, (rtc_rate_saved & 0xF0) | RTC_RATE);
        b = cmos_read(0x0B); cmos_write(0x0B, b | 0x40);
        cmos_read(0x0C);
        outp(0xA1, inp(0xA1) & ~1); outp(0x21, inp(0x21) & ~4);
    } else pit_speech();
    if (dos_con_touch && (f = dos_con_flag()) != 0) *f = (unsigned char)((*f | 0x08) & ~0x10);
    n_win++;
    suspended = 0;
}

static void __interrupt __far isr2f(union INTPACK r)
{
    if (r.x.ax == 0x1605) win_suspend();
    else if (r.x.ax == 0x1606) win_resume();
    _chain_intr(old2f);
}

/* RTC periodic interrupt, 8192 Hz.  Reading register 0Ch is what lets the
 * chip raise the next one.  Nothing is chained: the BIOS only uses IRQ8 for
 * INT 15h AH=83h/86h waits, which are unavailable while we are resident. */
static void __interrupt __far isr70(void)
{
    if (suspended) _chain_intr(old70);
    outp(0x70, 0x0C);
    inp(0x71);
    out_tick();
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
    if (suspended) {                           /* Windows: a transparent 18.2 Hz hook */
        if (old08 != bios08) in_chain = 1;
        _chain_intr(old08);
    }
    if (IVT08 != isr08) {                      /* hooked above us since last tick: */
        old08 = IVT08;                         /* the newcomer gets 18.2 Hz through */
        IVT08 = isr08;                         /* us, never our 10 kHz             */
    }
    out_tick();
    if (++chain_count >= chain_ticks) {
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
    if (out_dev != OUT_SPEAKER) {        /* DACs: 8-bit unsigned, 80h = silence */
        c = 128 + (int)(v * 127.0);
        if (c < 1) c = 1; else if (c > 255) c = 255;
    } else {
        c = (int)(pwm_mid + v * pwm_amp);    /* strictly inside 1..period-1      */
        if (c < 2) c = 2; else if (c > pwm_top - 2) c = pwm_top - 2;
    }
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
    lp_design(FS, LP_HZ, LP_A, LP_B);
    lp_design(FS, noise_lp_hz, LPN_A, LPN_B);
    { int i; for (i = 0; i < 5; i++) { S.lpA[i] = LP_A[i]; S.lpB[i] = LP_B[i]; } }
    hp_design(CUT_HZ, FS, CUT_C);
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
    double dlA[5], dlB[5];
    const double *tA, *tB;
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
    /* The output low-pass follows the source: 2600 Hz on voiced frames (F5
     * buzz), 4600 Hz on noise frames (the fricatives), ramped across the
     * frame so the switch is not a click. */
    tA = noise ? LPN_A : LP_A; tB = noise ? LPN_B : LP_B;
    for (i = 0; i < 5; i++) { dlA[i] = (tA[i] - S.lpA[i]) / n; dlB[i] = (tB[i] - S.lpB[i]) / n; }
    pt = S.pitch + pi * FD_MULT[fd];
    if (pt < 40.0) pt = 40.0; else if (pt > 400.0) pt = 400.0;

    /* Coefficients, amplitude and pitch are computed at each block's END and
     * ramped to it sample by sample from wherever the previous block left
     * them.  Stepping them once per block (the old way, and the chip's own
     * 8-step staircase) injects a broadband haze -- the "swirl" the NVDA
     * voice was cured of the same way.  Linear steps between two stable
     * (B1, B2) pairs stay inside the stability triangle. */
    for (pos = 0; pos < n; pos += BLOCK) {
        int m = n - pos < BLOCK ? n - pos : BLOCK, k;
        double d1[MAX_FORMANTS], d2[MAX_FORMANTS], da, dp, ae, pe;
        frac = (double)(pos + m) / n;
        for (i = 0; i < nf; i++) {
            double cf = S.prev_fc[i] + (fc[i] - S.prev_fc[i]) * frac;
            double cb = S.prev_bw[i] + (bw[i] - S.prev_bw[i]) * frac;
            double Bc = exp(-3.14159265358979 * cb / FS);
            B1[i] = Bc * 2.0 * cos(two_pi * cf / FS);
            B2[i] = -(Bc * Bc);
            d1[i] = (B1[i] - S.cB1[i]) / m;
            d2[i] = (B2[i] - S.cB2[i]) / m;
        }
        ae = S.prev_amp + (amp - S.prev_amp) * frac;
        pe = S.pitch + (pt - S.pitch) * frac;
        da = (ae - S.ca) / m;
        dp = (pe - S.cp) / m;
        for (k = 0; k < m; k++) {
            S.ca += da; S.cp += dp;
            a = S.ca; p = S.cp;
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
                S.cB1[i] += d1[i]; S.cB2[i] += d2[i];
                x = v + S.cB1[i] * S.y1[i] + S.cB2[i] * S.y2[i];
                S.y2[i] = S.y1[i];
                S.y1[i] = x;
                v = x;
            }
            for (i = 0; i < 5; i++) { S.lpA[i] += dlA[i]; S.lpB[i] += dlB[i]; }
            o = S.lpA[0] * v + S.lz0;
            S.lz0 = S.lpA[1] * v - S.lpA[3] * o + S.lz1;
            S.lz1 = S.lpA[2] * v - S.lpA[4] * o;
            v = S.lpB[0] * o + S.mz0;
            S.mz0 = S.lpB[1] * o - S.lpB[3] * v + S.mz1;
            S.mz1 = S.lpB[2] * o - S.lpB[4] * v;
            S.hy0 = S.hp_a * (S.hy0 + v - S.hx0); S.hx0 = v; v = S.hy0;
            S.hy1 = S.hp_a * (S.hy1 + v - S.hx1); S.hx1 = v; v = S.hy1;
            S.hy2 = S.hp_a * (S.hy2 + v - S.hx2); S.hx2 = v; v = S.hy2;
            if (!full_range) {                 /* 300 Hz cut, transposed form 2 */
                o = CUT_C[0] * v + S.cz0;
                S.cz0 = CUT_C[1] * v - CUT_C[3] * o + S.cz1;
                S.cz1 = CUT_C[2] * v - CUT_C[4] * o;
                v = o;
            }
            push_sample(soft_knee(v * MAKEUP * out_gain));
        }
        for (i = 0; i < nf; i++) { S.cB1[i] = B1[i]; S.cB2[i] = B2[i]; }   /* no drift */
        S.ca = ae; S.cp = pe;
    }
    for (i = 0; i < 5; i++) { S.lpA[i] = tA[i]; S.lpB[i] = tB[i]; }
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
    if (clock_mode == CLOCK_CARD) {            /* the real chip gets the bytes */
        int k;
        if (len == 1 && !(singles & 1) && dac_override >= 0) card_write((unsigned char)dac_override);
        else for (k = 0; k < len; k++) card_write(body[k]);
        if (len == 5) n_frames++;
        else if (len == 2) { n_ctrls++; if ((body[1] & 0xA0) == 0xA0) armed = 1; }
        else if (len == 1) { if (singles & 1) n_pitches++; singles++; }
        return;
    }
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

static unsigned n_card_timeouts;
static unsigned char req_seen;               /* a request was seen and not yet served */
static unsigned char card_last;              /* last status byte read                */
#define TRACE_N 48
static unsigned char trace_b[TRACE_N], trace_s0[TRACE_N], trace_s1[TRACE_N];
static unsigned trace_n;

/* On the 166 the request bit is gone by the time a second read looks for it:
 * whoever sees it must write at once.  So every status read anywhere
 * latches it here, and a write consumes the latch. */
static unsigned char card_status(void)
{
    card_last = (unsigned char)inp(card_port);
    if (!(card_last & 0x80)) req_seen = 1;
    return card_last;
}

/* Hand the chip one byte: at once when it asks (REQN low), or unsolicited
 * when it is idle (BUSY low and nothing requested) -- the 166's trace showed
 * the chip only asks for the second byte of a control write and for frame
 * data; the DAC byte, the pitch and the 00h prefix must simply be written.
 * A short settle after each write, so the next status read sees BUSY rise.
 * 40000 polls is what the Windows driver allowed before giving up. */
static void card_settle(void)
{
    int k;
    for (k = 0; k < 30; k++) outp(0x80, 0);
}

static int card_write(unsigned char b)
{
    unsigned n;
    unsigned char s0;
    for (n = 0; n < 40000U; n++) {
        if (!req_seen) card_status();
        if (req_seen || !(card_last & 0x40)) {
            s0 = card_last;
            req_seen = 0;
            outp(card_port, b);
            card_settle();
            if (trace_n < TRACE_N) { trace_b[trace_n] = b; trace_s0[trace_n] = s0; trace_s1[trace_n] = (unsigned char)inp(card_port); trace_n++; }
            return 1;
        }
    }
    n_card_timeouts++;
    if (trace_n < TRACE_N) { trace_b[trace_n] = b; trace_s0[trace_n] = card_last; trace_s1[trace_n] = 0xEE; trace_n++; }
    return 0;
}

/* The driver's probe: raw zeros until REQN drops (at most six), then BUSY
 * must clear.  Then the chip is put into STOP with the two-byte control
 * write 00h A1h, exactly what the driver does at reset. */
static const char *card_note = "";

/* Present = the port does not read FFh.  Then the driver's sequence is tried
 * and what the chip did with it is recorded, but a present card is always
 * accepted: the real traffic and /S's timeout counter are the better test. */
/* The driver's reset, exactly: a raw 00h, then A1h (STOP) the moment the
 * chip asks for it.  Twice if the first A1h finds no request. */
static int card_probe(void)
{
    int k;
    if (card_status() == 0xFF) return 0;
    n_card_timeouts = 0; req_seen = 0;
    for (k = 0; k < 2; k++) {
        outp(card_port, 0); outp(0x80, 0);
        if (card_write(0xA1)) break;
    }
    card_note = (k == 0) ? "STOP taken after one zero" : (k == 1) ? "STOP taken after a second zero" : "STOP never taken";
    return 1;
}

static unsigned char poll_status(void)
{
    if (clock_mode == CLOCK_CARD) {
        if (!req_seen) card_status();
        if (armed || !(req_seen || !(card_last & 0x40))) { n_polls_busy++; return STATUS_BUSY; }
        n_polls_ready++;
        return STATUS_READY;
    }
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
    if (clock_mode == CLOCK_CARD) { outp(card_port, 0); outp(0x80, 0); card_write(0xA1); return; }   /* STOP the chip */
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
    case 0xFA: {
        static double tone_phase;
        unsigned n = api_cx > 1024 ? 1024 : api_cx, k;
        if (RING_SIZE - 1 - queued() < n) { api_bx = 0; break; }
        _asm {
            clts
            fsave fpu_save
        }
        for (k = 0; k < n; k++) {
            if (api_bx == 0) {
                S.rng = S.rng * 1103515245UL + 12345UL;
                push_sample(0.9 * ((double)((S.rng >> 8) & 0xFFFF) / 32768.0 - 1.0));
            } else {
                tone_phase += 6.28318530717958 * api_bx / FS;
                if (tone_phase > 6.28318530717958) tone_phase -= 6.28318530717958;
                push_sample(0.9 * sin(tone_phase));
            }
        }
        _asm { frstor fpu_save }
        api_bx = n;
        break;
    }
    default:
        _asm {
            clts
            fsave fpu_save
        }
        wire_step(api_ah & 3);
        _asm { frstor fpu_save }
        break;
    }
}

static void __interrupt __far isr61(union INTPACK r)
{
    _asm {
        jmp short sig_end
        db 'B', 'R', 'A', 'I', 'S', 'P', 'K', '!'
    sig_end:
    }
    /* TALKHUN may hook INT 08 above us after we load; it expects 18.2 Hz, we
     * deliver 10 kHz.  Heal by re-hooking on top: its handler becomes the one we
     * chain to.  One vector compare per call. */
    if ((clock_mode == CLOCK_PIT || clock_mode == CLOCK_PIT_HI) && IVT08 != isr08) {   /* IF is clear here */
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
    else if (api_ah == 0xFA) { r.x.ax = api_bx; r.x.bx = api_bx; }
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
        int k, found = 0;
        if (a[0] == 0xCF) return 0;
        if (FP_SEG(v) >= 0xF000) return 0;       /* BIOS-parked dummy routine  */
        for (k = 0; k < 56 && !found; k++)       /* our signature, any version */
            if (a[k] == 'B' && a[k+1] == 'R' && a[k+2] == 'A' && a[k+3] == 'I' &&
                a[k+4] == 'S' && a[k+5] == 'P' && a[k+6] == 'K' && a[k+7] == '!') found = 1;
        if (!found) return -1;
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
    outp(0x40, pit_div & 0xFF);
    outp(0x40, pit_div >> 8);
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
/* Seconds since midnight from the clock chip, for the tick accounting in /S:
 * ticks lost to long interrupts-off stretches are invisible to every counter
 * we own, but not to an independent clock. */
static unsigned long cmos_seconds(void)
{
    unsigned char s, m, h, b, n = 0;
    while ((cmos_read(0x0A) & 0x80) && ++n) ;   /* update in progress          */
    s = cmos_read(0x00); m = cmos_read(0x02); h = cmos_read(0x04) & 0x7F;
    b = cmos_read(0x0B);
    if (!(b & 4)) {                              /* BCD                          */
        s = (s >> 4) * 10 + (s & 15); m = (m >> 4) * 10 + (m & 15); h = (h >> 4) * 10 + (h & 15);
    }
    return (unsigned long)h * 3600UL + (unsigned long)m * 60UL + s;
}
static unsigned long install_sec, install_ticks;

/* DOS 7's console writes the screen directly: IO.SYS tests bit 4 of the byte
 * at DOS-data:86h and, if set, stores the character at B800h itself; only
 * control characters and the last character of each write go through INT 10h
 * AH=0Eh.  A screen reader hooking INT 10h therefore hears the tail of every
 * line and nothing else ("ver" = "2]").  The write routine arms bit 4 at the
 * start of each write unless bit 3 is set.  Set bit 3 and every character
 * takes the DOS 6 route through the BIOS, where TALKHUN reads it.  ANSI.SYS
 * consults the same bit.  Found by disassembling the machine's own IO.SYS. */
static unsigned char far *dos_con_flag(void)
{
    union REGS r;
    struct SREGS s;
    if (_osmajor < 7) return 0;
    if (!dos_ds) {
        segread(&s);
        r.h.ah = 0x52;
        int86x(0x21, &r, &r, &s);
        dos_ds = s.es;
    }
    return (unsigned char far *)MK_FP(dos_ds, DOS_CON_FLAG);
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
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) != CLOCK_CARD) {
        if (FP_SEG(_dos_getvect(0x2F)) != cs) {
            printf("braispk: another program hooked INT 2Fh after us; cannot unload safely\r\n");
            return 1;
        }
        _dos_setvect(0x2F, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old2f));
    }
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_CARD) {
        _dos_setvect(API_INT, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&old61));
    } else if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) != CLOCK_RTC) {
        if (v08 != *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&bios08)) {
            printf("braispk: another program hooked INT 08 after us; cannot unload safely\r\n");
            return 1;
        }
        _disable();
        if (*(unsigned char far *)MK_FP(ds, (unsigned)&spk_state)) { outp(0x61, inp(0x61) & ~3); outp(0x43, 0xB6); }
        _dos_setvect(8, *(void (__interrupt __far **)(void))MK_FP(ds, (unsigned)&orig08));
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
    if (*(unsigned far *)MK_FP(ds, (unsigned)&dos_ds) && *(unsigned char far *)MK_FP(ds, (unsigned)&dos_con_touch)) {
        unsigned char far *f = (unsigned char far *)MK_FP(*(unsigned far *)MK_FP(ds, (unsigned)&dos_ds), DOS_CON_FLAG);
        *f = (unsigned char)((*f & ~0x08) | (*(unsigned char far *)MK_FP(ds, (unsigned)&dos_con_saved) & 0x08));
    }
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&out_dev) == OUT_SB) {
        sb_port          = *(unsigned far *)MK_FP(ds, (unsigned)&sb_port);
        mix_master_saved = *(unsigned char far *)MK_FP(ds, (unsigned)&mix_master_saved);
        mix_voice_saved  = *(unsigned char far *)MK_FP(ds, (unsigned)&mix_voice_saved);
        mix_filter_saved = *(unsigned char far *)MK_FP(ds, (unsigned)&mix_filter_saved);
        sb_close();
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
    static const unsigned char settings[2] = {0x20, 0x70};   /* DAC gain 3.5x, as TALKHUN */
    static const unsigned char pitch[2]    = {0x20, 46};           /* 112 Hz  */
    static const unsigned char ctl_go[3]   = {0x20, 0x00, 0x80};
    static const unsigned char ctl_stop[3] = {0x20, 0x00, 0xA0};
    unsigned char frame[6] = {0x20, 0x75, 0x40, 0x3F, 0x4D, 0x93};  /* an /a/, AM 15 */
    int k;
    union REGS r;
    unsigned ds = 0, cport = 0;
    unsigned long t_start = 0;
    if (find_resident(&ds, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_CARD)
        cport = *(unsigned far *)MK_FP(ds, (unsigned)&card_port);
    lg("P1 self-test: DAC 70h (or /G), pitch 2Eh, command 00 80");
    i2c_xfer(settings, 2);
    i2c_xfer(pitch, 2);
    i2c_xfer(ctl_go, 3);
    lg("P2 four sounds, 1 s each: /a/ voiced, /a/ on noise, low buzz, /i/ voiced");
    {
        volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
        t_start = *bios;
    }
    for (k = 0; k < 4 * 100; k++) {
        int part = k / 100, j = k % 100;
        if (!wait_ready()) { lg("P! adapter never became ready"); printf("braispk: adapter never became ready\r\n"); return 1; }
        switch (part) {
        case 0:  frame[1] = 0x75; frame[2] = 0x40; frame[3] = 0x3F; frame[4] = 0x4D; frame[5] = 0x93; break;  /* /a/ 112 Hz */
        case 1:  frame[1] = 0x75; frame[2] = 0x50; frame[3] = 0x3F; frame[4] = 0x4D; frame[5] = 0x93; break;  /* same, PI=16 noise */
        case 2:  frame[1] = 0x40; frame[2] = 0x40; frame[3] = 0x0F; frame[4] = 0x40; frame[5] = 0x01; break;  /* F1 100 Hz, F2 500, wide */
        default: frame[1] = 0x64; frame[2] = 0x40; frame[3] = 0x6F; frame[4] = 0x5C; frame[5] = 0xAB; break;  /* /i/: F1 258, F2 2328 */
        }
        if (j < 78) { /* sound */ }
        else frame[3] &= 0xF0;                                     /* AM 0: the gap      */
        if (k == 0) frame[3] &= 0xF0;                              /* silent dummy first */
        i2c_xfer(frame, 6);
        if (k == 1) lg("P3 first voiced frame taken");
        if (k == 100) lg("P4 noise part");
        if (k == 200) lg("P5 low buzz part");
        if (k == 300) lg("P6 /i/ part");
    }
    {
        volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
        unsigned long ticks = *bios - t_start;
        sprintf(logbuf, "P6b 400 frames took %lu BIOS ticks = %lu ms; at 12.8 ms a frame that is %lu ms, so the chip runs at %lu%% of its nominal clock",
                ticks, ticks * 55, 400UL * 128 / 10, ticks ? (400UL * 128 / 10) * 100 / (ticks * 55) : 0);
        lg(logbuf);
    }
    i2c_xfer(ctl_stop, 3);
    do { r.h.ah = 0xFD; int86(API_INT, &r, &r); } while (r.x.dx);
    if (cport) {
        volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
        unsigned long t0 = *bios;
        unsigned char s1, s2, s3;
        s1 = (unsigned char)inp(cport);
        while (*bios - t0 < 4) ; s2 = (unsigned char)inp(cport);
        while (*bios - t0 < 22) ; s3 = (unsigned char)inp(cport);
        sprintf(logbuf, "P7 status after STOP: at once %02Xh, 0.2 s %02Xh, 1.2 s %02Xh (9Fh = stopped by the user, BFh = bad stop, DFh = still busy)", s1, s2, s3);
        lg(logbuf);
    }
    lg("P8 self-test done");
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

/* /K: 200, 440, 1000, 2000, 3000 Hz and noise, 0.7 s each with gaps, at
 * 90% modulation, straight into the ring.  Which of these come out of the
 * cone says where the low end goes missing. */
static int tone_ladder(void)
{
    static const unsigned hz[6] = {200, 440, 1000, 2000, 3000, 0};
    volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
    union REGS r;
    int i;
    if (find_resident(0, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
    for (i = 0; i < 6; i++) {
        long left = 5700, guard = 0;           /* ~0.7 s at 8192 Hz         */
        unsigned long t0;
        while (left > 0 && guard < 2000000L) {
            r.h.ah = 0xFA; r.x.bx = hz[i]; r.x.cx = (unsigned)(left > 1024 ? 1024 : left);
            int86(API_INT, &r, &r);
            if (r.x.bx) left -= r.x.bx; else guard++;
        }
        do { r.h.ah = 0xFD; int86(API_INT, &r, &r); } while (r.x.dx);
        t0 = *bios; while (*bios - t0 < 6) ;    /* a third of a second of silence */
        printf("%u Hz\r\n", hz[i]);
    }
    printf("braispk: tone ladder done (200 440 1000 2000 3000 Hz, noise)\r\n");
    return 0;
}

/* /Z: which I/O addresses answer at all.  A card on the wrong jumpers shows
 * up as an unexplained block of four; the onboard devices are known. */
static int port_scan(void)
{
    unsigned p, n = 0;
    char line[160];
    int pos = 0;
    logging = 1;
    lg("Z port scan 100h-3FFh, addresses that do not read FFh:");
    for (p = 0x100; p < 0x400; p++) {
        unsigned char v = (unsigned char)inp(p);
        if (v == 0xFF) continue;
        pos += sprintf(line + pos, " %03X=%02X", p, v);
        n++;
        if (pos > 140) { lg(line); pos = 0; }
    }
    if (pos) lg(line);
    sprintf(line, "Z %u addresses answered", n);
    lg(line);
    printf("braispk: %u addresses answered; see BRAISPK.LOG\r\n", n);
    return 0;
}

static int report(void)
{
    union REGS r;
    unsigned ds;
    if (find_resident(&ds, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
    r.h.ah = 0xFD; int86(API_INT, &r, &r);
    printf("braispk: %s; frames %u  controls %u  pitches %u  queued %u samples\r\n",
           *(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_PIT ? "IRQ0 10027 Hz clock" :
           *(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_PIT_HI ? "IRQ0 19886 Hz clock" :
           *(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_CARD ? "PC-ROBOT card" : "RTC 8192 Hz clock",
           r.x.ax, r.x.bx, r.x.cx, r.x.dx);
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&out_dev) == OUT_LPT)
        printf("         printer-port DAC at %03Xh\r\n", *(unsigned far *)MK_FP(ds, (unsigned)&lpt_port));
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&out_dev) == OUT_SB)
        printf("         Sound Blaster DAC at %03Xh, DSP version %u.%02u, %s; DSP waited for %u times, not ready in time %u times\r\n",
               *(unsigned far *)MK_FP(ds, (unsigned)&sb_port),
               *(unsigned char far *)MK_FP(ds, (unsigned)&sb_ver_hi), *(unsigned char far *)MK_FP(ds, (unsigned)&sb_ver_lo),
               *(unsigned char far *)MK_FP(ds, (unsigned)&dac_wide) ? "19886 Hz pairs (/W)" : "9943 Hz, command and sample on alternate ticks",
               *(unsigned far *)MK_FP(ds, (unsigned)&n_dac_wait),
               *(unsigned far *)MK_FP(ds, (unsigned)&n_dac_busy));
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) == CLOCK_CARD) {
        unsigned k, tn = *(unsigned far *)MK_FP(ds, (unsigned)&trace_n);
        printf("         card port %03Xh status now %02Xh (bit7 REQN, bit6 BUSY)  write timeouts %u  request latched %u\r\n",
               *(unsigned far *)MK_FP(ds, (unsigned)&card_port), inp(*(unsigned far *)MK_FP(ds, (unsigned)&card_port)),
               *(unsigned far *)MK_FP(ds, (unsigned)&n_card_timeouts), *(unsigned char far *)MK_FP(ds, (unsigned)&req_seen));
        printf("         first writes (byte: status seen -> status after; EE = timed out):");
        for (k = 0; k < tn; k++)
            printf("%s %02X:%02X>%02X", (k % 8) ? "" : "\r\n          ",
                   *(unsigned char far *)MK_FP(ds, (unsigned)&trace_b[k]),
                   *(unsigned char far *)MK_FP(ds, (unsigned)&trace_s0[k]),
                   *(unsigned char far *)MK_FP(ds, (unsigned)&trace_s1[k]));
        printf("\r\n");
    }
    if (*(unsigned far *)MK_FP(ds, (unsigned)&dos_ds))
        printf("         DOS console flag at %04X:%04X: was %02X, now %02X (bit 3 = screen through INT 10h, bit 4 = direct write armed)\r\n",
               *(unsigned far *)MK_FP(ds, (unsigned)&dos_ds), DOS_CON_FLAG,
               *(unsigned char far *)MK_FP(ds, (unsigned)&dos_con_saved),
               *(unsigned char far *)MK_FP(*(unsigned far *)MK_FP(ds, (unsigned)&dos_ds), DOS_CON_FLAG));
    if (*(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode) != CLOCK_CARD) {
        unsigned char cm = *(unsigned char far *)MK_FP(ds, (unsigned)&clock_mode);
        unsigned long rate = cm == CLOCK_RTC ? 8192UL : 1193182UL / *(unsigned far *)MK_FP(ds, (unsigned)&pit_div);
        unsigned long secs = (cmos_seconds() + 86400UL - *(unsigned long far *)MK_FP(ds, (unsigned)&install_sec)) % 86400UL;
        unsigned long got = *(unsigned long far *)MK_FP(ds, (unsigned)&tick_count) - *(unsigned long far *)MK_FP(ds, (unsigned)&install_ticks);
        printf("         ticks since install %lu in %lu s = %lu a second, the clock rate is %lu: about %ld ticks %s (a second's worth of slack is %lu)\r\n",
               got, secs, secs ? got / secs : 0UL, rate,
               (long)(secs * rate) - (long)got, (long)(secs * rate) - (long)got >= 0 ? "LOST" : "extra", rate);
    }
    printf("         Windows start/exit pairs seen %u, suspended now %u\r\n",
           *(unsigned far *)MK_FP(ds, (unsigned)&n_win), *(unsigned char far *)MK_FP(ds, (unsigned)&suspended));
    printf("         polls busy %u  ready %u  ticks %lu  armed %u  underruns %u  overruns %u\r\n",
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_busy),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_polls_ready),
           *(unsigned long far *)MK_FP(ds, (unsigned)&tick_count),
           *(unsigned char far *)MK_FP(ds, (unsigned)&armed),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_underrun),
           *(unsigned far *)MK_FP(ds, (unsigned)&n_overrun));
    return 0;
}


/* Windows 98's DOS leaves CR0.TS (task switched) and CR0.MP set, the lazy
 * FPU-switch state of the VMM.  In real mode that makes the first x87
 * instruction trap to INT 7, whose handler on the Pentium 166 evidently
 * skips the instruction as if no coprocessor existed: the Watcom runtime
 * concluded "no 8087" (control word read back as 0000) and every double in
 * the synth became garbage until a math loop spun.  DOSBox never sets TS.
 * CLTS is legal in real mode on a 286 and up. */
extern unsigned char _8087, _real87;
static unsigned clear_ts(void)
{
    unsigned msw;
    _asm {
        clts
        smsw ax
        mov  msw, ax
    }
    _8087 = 3;                                 /* 387 or better, and it is real */
    _real87 = 3;
    return msw;
}

int main(int argc, char **argv)
{
    unsigned sp_now, top, paras;
    unsigned far *bda_lpt1 = (unsigned far *)MK_FP(0x40, 0x08);
    int i;

    clear_ts();
    _control87(_MCW_EM, _MCW_EM);              /* no FPU traps, whatever Windows left */
    for (i = 1; i < argc; i++) {
        if (argv[i][0] == '/' || argv[i][0] == '-') {
            switch (argv[i][1] & 0xDF) {
            case 'U': return uninstall();
            case 'C': chip_timing = 1; break;
            case 'V': if (argv[i][2] >= '0' && argv[i][2] <= '9') { out_gain = GAIN_TAB[argv[i][2] - '0']; gain_set = 1; } break;
            case 'W': dac_wide = 1; break;
            case 'T': dos_con_touch = 0; break;
            case 'J': if (argv[i][2] >= '0' && argv[i][2] <= '9') noise_lp_hz = NOISE_LP_TAB[argv[i][2] - '0']; break;
            case 'E': out_dev = OUT_LPT;
                      if (argv[i][2]) lpt_port = (unsigned)strtoul(argv[i] + 2, 0, 16);
                      break;
            case 'Q': {                       /* rehearse Windows: broadcast start, then exit */
                union REGS r; struct SREGS s;
                if (find_resident(0, 0, 0) != 1) { printf("braispk: not resident\r\n"); return 1; }
                segread(&s); s.es = 0; s.ds = 0;
                r.x.ax = 0x1605; r.x.bx = 0; r.x.si = 0; r.x.cx = 0; r.x.dx = 0; r.x.di = 0x30A;
                int86x(0x2F, &r, &r, &s);
                printf("braispk: Windows-start broadcast sent (timer normal, DAC parked)\r\n");
                segread(&s);
                r.x.ax = 0x1606; r.x.dx = 0;
                int86x(0x2F, &r, &r, &s);
                printf("braispk: Windows-exit broadcast sent (re-armed); speech should work again\r\n");
                return 0;
            }
            case 'O': keep_filter = 1; break;
            case 'B': out_dev = OUT_SB;
                      if (argv[i][2]) { sb_port = (unsigned)strtoul(argv[i] + 2, 0, 16); sb_from_env = 0; }
                      else sb_from_env = 1;
                      break;
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
            case 'K': return tone_ladder();
            case 'Z': return port_scan();
            case 'L': {
                unsigned msw;
                double two = 2.0, root;
                long check;
                logging = 1;
                _asm {
                    smsw ax
                    mov  msw, ax
                }
                root = sqrt(two);
                check = (long)(root * 1000.0);
                sprintf(logbuf, "--- braispk 0.29: %s  DOS %d.%02d  PSP %04X  MSW now %04X  FPU CW %04X SW %04X  sqrt2*1000=%ld (want 1414)",
                        argv[0], _osmajor, _osminor, _psp, msw, _control87(0, 0), _clear87(), check);
                lg(logbuf);
                break;
            }
            case 'N': lg("N alive, one beep, exit"); beeps(1); return 0;
            case 'I': clock_mode = CLOCK_PIT; break;
            case 'H': clock_mode = CLOCK_PIT_HI; break;
            case '8': clock_mode = CLOCK_RTC; break;
            case 'A': clock_mode = CLOCK_CARD;
                      if (argv[i][2]) card_port = (unsigned)strtoul(argv[i] + 2, 0, 16);
                      break;
            case 'G': if (argv[i][2]) dac_override = (int)strtoul(argv[i] + 2, 0, 16) & 0xFF; break;
            case 'X': force_bypass = 1; break;          /* test: bypass even without an OS hook */
            case 'F': full_range = 1; break;
            case 'R': { union REGS r; r.h.ah = 0xFC; if (find_resident(0,0,0) != 1) { printf("not resident\r\n"); return 1; } int86(API_INT, &r, &r); printf("reset\r\n"); return 0; }
            default:
                printf("BRAISPK -- BraiLab speech adapter on the PC speaker\r\n"
                       "  BRAISPK        install (then load TALKHUNS.COM)\r\n"
                       "  BRAISPK /C     chip timing: frame length from the FS bits (8.8 ms at ESC S6)\r\n"
                       "  BRAISPK /Vn    output level 0..9 (8 = default x8, 2 = the NVDA voice's level)\r\n"
                       "  BRAISPK /F     full range: keep the voice fundamental instead of the 300 Hz cut\r\n"
                       "  BRAISPK /P     self-test: a vowel through the synth, no TALKHUN needed\r\n"
                       "  BRAISPK /K     tone ladder: 200 440 1000 2000 3000 Hz, then noise\r\n"
                       "  BRAISPK /B[p]  Sound Blaster DAC at port p (220) instead of the speaker; level x2, full range\r\n"
                       "  BRAISPK /E[p]  8-bit DAC on the printer port (Covox), p = 378 etc., default LPT1\r\n"
                       "  BRAISPK /B /W  the DAC at 19886 Hz (a pair every tick) instead of 9943 Hz\r\n"
                       "  BRAISPK /B /O  leave the card's output filter as found (default: bypassed)\r\n"
                       "  BRAISPK /Jn    consonant brightness 0..9: low-pass on noise frames 2600 (0, dull) ..\r\n"
                       "                 3600 (4, default) .. 4600 (8, sharp) .. 4950 (9) Hz\r\n"
                       "  BRAISPK /Q     rehearse a Windows start and exit (INT 2Fh broadcasts) while resident\r\n"
                       "  BRAISPK /T     leave DOS 7's console alone (it writes the screen directly; by default\r\n"
                       "                 BRAISPK makes it go through INT 10h so TALKHUN hears ver, dir, prompts)\r\n"
                       "  BRAISPK /8     clock the samples from the RTC at 8192 Hz (audible carrier; safest)\r\n"
                       "  BRAISPK /A[p]  no speaker: feed the real PCF8200 on the PC-ROBOT card at port p (100)\r\n"
                       "  BRAISPK /Z     scan I/O 100h-3FFh into BRAISPK.LOG: where does anything answer\r\n"
                       "  BRAISPK /Gxx   card mode: DAC gain code instead of the driver's 70 (20 = 0 dB, 40 = -6 dB)\r\n"
                       "  BRAISPK /I     IRQ0 at 10027 Hz, one sample per tick\r\n"
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
    if (i == 1) { printf("braispk: already resident (a new version needs a reboot first)\r\n"); beeps(2); return 1; }
    if (i == -1) { printf("braispk: INT %02Xh is already in use by another program; not installing\r\n", API_INT); beeps(3); return 1; }

    if (*bda_lpt1 == 0) *bda_lpt1 = 0x378;     /* TALKHUN refuses to bind to LPT 0 */
    resident_psp = _psp;
    synth_reset();
    old61 = _dos_getvect(API_INT);
    orig08 = old08 = bios08 = _dos_getvect(8);
    if (clock_mode == CLOCK_CARD) {
        unsigned char st0 = card_status();
        int ok = card_probe();
        if (logging) {
            sprintf(logbuf, "4 PC-ROBOT card at %03Xh: status before %02Xh, %s, %s, timeouts %u, status after %02Xh, request latched %u",
                    card_port, st0, ok ? "present" : "ABSENT (reads FFh)", card_note, n_card_timeouts, (unsigned char)inp(card_port), req_seen);
            lg(logbuf);
        }
        if (!ok) {
            printf("braispk: no PC-ROBOT card answering at %03Xh (status %02Xh)\r\n", card_port, card_status());
            beeps(6);
            return 1;
        }
        _dos_setvect(API_INT, isr61);
        lg("3 INT 61h hooked, card mode");
        beeps(1);
        goto resident;
    }
    if (out_dev == OUT_SB) {
        int ok;
        if (sb_from_env) {                         /* BLASTER=A220 I5 D1 T4: only A matters */
            const char *e = getenv("BLASTER"), *p = e ? strchr(e, 'A') : 0;
            if (p && p[1]) sb_port = (unsigned)strtoul(p + 1, 0, 16);
        }
        ok = sb_open();
        if (logging) {
            sprintf(logbuf, "4 Sound Blaster at %03Xh: %s, DSP version %u.%02u, mixer master/voice/filter were %02X/%02X/%02X, now %02X/%02X/%02X",
                    sb_port, ok ? "DSP reset answered AAh" : "NO DSP (no AAh after reset)", sb_ver_hi, sb_ver_lo,
                    mix_master_saved, mix_voice_saved, mix_filter_saved, mixer_read(0x22), mixer_read(0x04), mixer_read(0x0E));
            lg(logbuf);
        }
        if (!ok) {
            printf("braispk: no Sound Blaster DSP answering at %03Xh\r\n", sb_port);
            beeps(7);
            return 1;
        }
        full_range = 1;                            /* the 300 Hz cut was for the cone */
        if (!gain_set) out_gain = 2.0;
    }
    if (out_dev == OUT_LPT) {
        if (!lpt_port) lpt_port = *bda_lpt1 ? *bda_lpt1 : 0x378;
        if (logging) {
            sprintf(logbuf, "4 printer-port DAC at %03Xh (Covox): no handshake, the byte is the voltage", lpt_port);
            lg(logbuf);
        }
        outp(lpt_port, 0x80);
        full_range = 1;
        if (!gain_set) out_gain = 2.0;
    }
    _dos_setvect(API_INT, isr61);
    old2f = _dos_getvect(0x2F);
    _dos_setvect(0x2F, isr2f);
    lg("3 INT 61h hooked, INT 2Fh hooked for the Windows start/exit broadcasts");
    if (clock_mode != CLOCK_RTC) {
        /* An operating-system hook on INT 08 (Windows 98's IO.SYS sits there)
         * did not pass our 10 kHz-paced chain on to the BIOS tick on the real
         * machine.  Chain to the BIOS's own compatibility entry instead; the
         * hook is simply not called while we are resident. */
        if (FP_SEG(orig08) < 0xF000 || force_bypass) {
            /* Watcom turns a far data pointer cast to a far function pointer
             * into segment 0: on the 166 that sent IRQ0 into the vector table
             * and hung the box solid.  Build the pointer from its bits. */
            union { void (__interrupt __far *f)(void); unsigned long l; } u;
            const unsigned char far *b;
            u.l = 0xF000FEA5UL;
            b = (const unsigned char far *)u.f;
            /* The compatibility entry should start like a handler.  If it
             * does not, this BIOS has none there: fall back to the RTC. */
            if (b[0] == 0xFB || b[0] == 0xE9 || b[0] == 0xEB || b[0] == 0xEA ||
                b[0] == 0xFA || b[0] == 0x50 || b[0] == 0x1E || b[0] == 0x9C || b[0] == 0x60) {
                old08 = bios08 = u.f;
                bios_bypass = 1;
            } else {
                if (logging) {
                    sprintf(logbuf, "4 no BIOS handler at F000:FEA5 (bytes %02X %02X %02X %02X): using the RTC instead",
                            b[0], b[1], b[2], b[3]);
                    lg(logbuf);
                }
                printf("braispk: this BIOS has no timer entry at F000:FEA5; using the RTC clock\r\n");
                clock_mode = CLOCK_RTC;
            }
        }
    }
    if (clock_mode != CLOCK_RTC) {
        if (clock_mode == CLOCK_PIT) {
            fs_hz = 10027.0; pit_div = 119; chain_ticks = 551; ticks_per_sample = 1; ramp_mask = 1;
            pwm_top = 119; pwm_mid = 60; pwm_amp = 57; idle_level = 60;
        } else {
            fs_hz = 1193182.0 / 60.0 / 2.0; pit_div = 60; chain_ticks = 1092; ticks_per_sample = 2; ramp_mask = 3;
            pwm_top = 58; pwm_mid = 29; pwm_amp = 27; idle_level = 29;
        }
        synth_reset();
        if (logging) {
            const unsigned char far *b = (const unsigned char far *)bios08;
            sprintf(logbuf, "4 IRQ0 at %u Hz: chaining to %04X:%04X (%s), bytes there %02X %02X %02X %02X",
                    (unsigned)(1193182L / pit_div), FP_SEG(bios08), FP_OFF(bios08),
                    bios_bypass ? "BIOS entry, IO.SYS bypassed" : "the vector as found",
                    b[0], b[1], b[2], b[3]);
            lg(logbuf);
        }
        pit_speech();
        _dos_setvect(8, isr08);
        lg("4 PIT channel 0 reprogrammed, INT 08 hooked");
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
    install_sec = cmos_seconds(); install_ticks = tick_count;
resident:
    lg("7 going resident");
    if (dos_con_touch) {
        unsigned char far *f = dos_con_flag();
        if (f) {
            dos_con_saved = *f;
            if (logging) {
                sprintf(logbuf, "7b DOS %d.%02d console flag at %04X:%04X was %02X, setting bit 3: the screen is written through INT 10h from now on",
                        _osmajor, _osminor, dos_ds, DOS_CON_FLAG, dos_con_saved);
                lg(logbuf);
            }
            *f = (unsigned char)((dos_con_saved | 0x08) & ~0x10);
        }
    }

    /* free the environment, keep PSP..top of our stack resident */
    _dos_freemem(*(unsigned far *)MK_FP(_psp, 0x2C));
    _asm { mov sp_now, sp }
    top = sp_now + 512;                        /* we are near the top of DGROUP  */
    paras = (unsigned)((((unsigned long)FP_SEG((void __far *)&ring_head) << 4) + top - ((unsigned long)_psp << 4) + 15) >> 4);
    if (clock_mode == CLOCK_CARD)
        printf("braispk: resident, %u KB, PC-ROBOT card (PCF8200) at %03Xh, API INT %02Xh\r\n",
               (paras + 63) / 64, card_port, API_INT);
    else if (out_dev == OUT_LPT)
    printf("braispk: resident, %u KB, %s -> printer-port DAC at %03Xh, API INT %02Xh, level x%d.%02d%s\r\n",
           (paras + 63) / 64, clock_mode == CLOCK_PIT ? "10027 Hz IRQ0" : clock_mode == CLOCK_PIT_HI ? "19886 Hz IRQ0" : "8192 Hz RTC",
           lpt_port, API_INT, (int)out_gain, (int)(out_gain * 100) % 100, chip_timing ? ", chip frame timing" : "");
    else if (out_dev == OUT_SB)
    printf("braispk: resident, %u KB, %s -> Sound Blaster DAC at %03Xh (DSP %u.%02u)%s%s, API INT %02Xh, level x%d.%02d%s\r\n",
           (paras + 63) / 64, clock_mode == CLOCK_PIT ? "10027 Hz IRQ0" : clock_mode == CLOCK_PIT_HI ? "19886 Hz IRQ0" : "8192 Hz RTC",
           sb_port, sb_ver_hi, sb_ver_lo, dac_wide ? ", pairs every tick" : "", keep_filter ? ", filter as found" : "",
           API_INT, (int)out_gain, (int)(out_gain * 100) % 100,
           chip_timing ? ", chip frame timing" : "");
    else
    printf("braispk: resident, %u KB, %s PWM on the PC speaker, API INT %02Xh, level x%d.%02d%s\r\n",
           (paras + 63) / 64, clock_mode == CLOCK_PIT ? "10027 Hz IRQ0" : clock_mode == CLOCK_PIT_HI ? "19886 Hz IRQ0" : "8192 Hz RTC",
           API_INT, (int)out_gain, (int)(out_gain * 100) % 100,
           chip_timing ? ", chip frame timing" : "");
    fflush(stdout);                            /* _dos_keep does not flush     */
    _dos_keep(0, paras);
    return 0;
}
