/* pwmtest.c -- does this machine (or emulator) turn timer-2 one-shot PWM into
 * sound?  Plays 1.5 s of 440 Hz then 1.5 s of 880 Hz through the PC speaker
 * using the SPEAKER 1990 method: IRQ0 at 1193182/119 = 10027 Hz, each tick
 * writes one sample as a PIT channel-2 mode-0 count, so the speaker line goes
 * low for `sample` PIT cycles out of every 119.  Chains the old INT 08 every
 * 551st tick so DOS time keeps.  Prints the BIOS tick delta (expect ~55). */
#include <stdio.h>
#include <conio.h>
#include <dos.h>
#include <i86.h>
#include <math.h>

#define DIV      119              /* PIT divisor -> 10027 Hz, 119 levels */
#define CHAIN    551              /* 10027 / 18.2065 */
#define LEVELS   117              /* keep the count strictly below DIV */

static void (__interrupt __far *old08)(void);
static volatile unsigned long ticks;
static unsigned chain;
static unsigned char wave[256];
static unsigned phase, phinc;

static void __interrupt __far isr08(void)
{
    outp(0x42, wave[phase >> 8]);
    phase += phinc;
    ticks++;
    if (++chain >= CHAIN) {
        chain = 0;
        _chain_intr(old08);       /* old handler sends the EOI */
    }
    outp(0x20, 0x20);
}

int main(void)
{
    unsigned long far *bios = (unsigned long far *)MK_FP(0x40, 0x6C);
    unsigned long t0, t1;
    int i;

    for (i = 0; i < 256; i++)
        wave[i] = (unsigned char)(1 + (LEVELS - 1) * (0.5 + 0.5 * sin(i * 6.283185307 / 256.0)));
    printf("pwmtest: 440 Hz then 880 Hz, 3 s total\r\n");
    t0 = *bios;
    old08 = _dos_getvect(8);
    _disable();
    outp(0x43, 0x90);             /* ch2, lobyte only, mode 0 one-shot */
    outp(0x42, LEVELS / 2);
    outp(0x61, inp(0x61) | 3);    /* gate + speaker on */
    _dos_setvect(8, isr08);
    outp(0x43, 0x34);             /* ch0, lo/hi, mode 2 rate generator */
    outp(0x40, DIV & 0xFF);
    outp(0x40, DIV >> 8);
    _enable();

    phinc = (unsigned)(440.0 * 65536.0 / 10027.0);
    while (ticks < 15040) ;
    phinc = (unsigned)(880.0 * 65536.0 / 10027.0);
    while (ticks < 30080) ;

    _disable();
    outp(0x43, 0x34); outp(0x40, 0); outp(0x40, 0);   /* 18.2 Hz again */
    _dos_setvect(8, old08);
    outp(0x61, inp(0x61) & ~3);
    _enable();
    t1 = *bios;
    printf("done: %lu samples, BIOS ticks advanced by %lu (expect ~55)\r\n", ticks, t1 - t0);
    return 0;
}
