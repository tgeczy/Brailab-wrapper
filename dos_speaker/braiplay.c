/* BRAIPLAY - plays captured BraiLab PC speech straight into the box on the printer port.

   No TALKHUN, no TSR: this program sends the PCF8200 exactly what TALKHUN.COM would have sent,
   from a recording of TALKHUN's own output that is packed onto the end of this .EXE file
   (make_braiplay.py builds it).  So a whole listening test is one file and one command, the
   text, tempo, pitch and furcsa are fixed when the file is built, and nothing has to be
   configured on the DOS machine.

   The wire is TALKHUN's, instruction for instruction (TALKHUN.COM of 2000, 5271h-538Eh):
     - two printer-port bits carry I2C: data is bit 0 and clock bit 1 of the data port, and the
       same two bits with the clock inverted go to the control port;
     - every transaction is START, the address 20h, the bytes, STOP;
     - status bit 4 clear means the chip wants the next bytes; bit 5 clear is a fault;
       a poll gives up after four BIOS ticks;
     - an utterance starts with a poll.  If it times out the chip is idle, and the start
       sequence follows: the volume byte, then the pitch byte, then 00h and the command (80h,
       plus 10h for furcsa, plus the tempo bits), each after a poll.  Then every 5-byte frame
       after a poll, and 00h A0h (STOP) after the last.

   BRAIPLAY          play, on LPT1
   BRAIPLAY 2        LPT2;  BRAIPLAY 378 names the port address in hex
   Esc stops it.

   When it ends: one long beep = everything was sent; three short beeps = the box stopped
   answering part of the way; five = it never answered (not connected, no power, or TALKHUN
   is loaded and holds the port: reboot and do not load it).  The same is printed.

   Build: wcl -q -bt=dos -ms -0 -os -fe=braiplay.exe braiplay.c   (Open Watcom) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <bios.h>
#include <dos.h>
#include <i86.h>
#include <conio.h>

#define MAGIC "BRAIREC1"
#define MAX_FRAMES 3000

static unsigned base;
static volatile unsigned char far *tick;
static unsigned char frames[MAX_FRAMES * 5];

static void wire(unsigned char v)
{
    v &= 3;
    outp(base, v);
    outp(base + 2, v ^ 2);
}

static void i2c_start(void) { wire(3); wire(2); wire(0); }
static void i2c_stop(void) { wire(0); wire(2); wire(3); }

static void i2c_bit(unsigned char bit)
{
    wire(bit);
    wire(bit | 2);
    wire(bit);
}

static void i2c_byte(unsigned char v)
{
    int i;
    for (i = 0; i < 8; i++) {
        i2c_bit((v & 0x80) ? 1 : 0);
        v <<= 1;
    }
    i2c_bit(1);                         /* the acknowledge slot, data released */
}

static void send(const unsigned char *bytes, int n)
{
    i2c_start();
    i2c_byte(0x20);
    while (n--)
        i2c_byte(*bytes++);
    i2c_stop();
}

static unsigned char last_status;

/* 0 = the chip asks for more, 1 = fault, 2 = four ticks passed */
static int poll(void)
{
    unsigned char t0 = *tick;
    for (;;) {
        last_status = (unsigned char)inp(base + 1);
        if (!(last_status & 0x10))
            return 0;
        if (!(last_status & 0x20))
            return 1;
        if ((unsigned char)(*tick - t0) >= 4)
            return 2;
    }
}

static void wait_ticks(unsigned n)
{
    unsigned char t = *tick;
    while (n) {
        if (*tick != t) {
            t = *tick;
            n--;
        }
    }
}

static void beep(unsigned hz, unsigned ticks)
{
    unsigned div = (unsigned)(1193182L / hz);
    outp(0x43, 0xB6);
    outp(0x42, div & 0xFF);
    outp(0x42, div >> 8);
    outp(0x61, inp(0x61) | 3);
    wait_ticks(ticks);
    outp(0x61, inp(0x61) & ~3);
}

static void beeps(int n)
{
    while (n--) {
        beep(880, 2);
        wait_ticks(2);
    }
}

static int escape_pressed(void)
{
    if (!_bios_keybrd(_KEYBRD_READY))
        return 0;
    return (_bios_keybrd(_KEYBRD_READ) & 0xFF) == 27;
}

static unsigned rd16(FILE *f)
{
    unsigned lo = (unsigned)fgetc(f);
    return lo | ((unsigned)fgetc(f) << 8);
}

int main(int argc, char **argv)
{
    FILE *f;
    unsigned char trailer[12], msg[2];
    unsigned long size, pos, units = 0, sent = 0;
    unsigned errors = 0, first_err_unit = 0, first_err_frame = 0, never = 0;
    unsigned char first_err_status = 0;
    int kind, stopped_by_key = 0;

    tick = (volatile unsigned char far *)MK_FP(0x40, 0x6C);
    base = *(unsigned far *)MK_FP(0x40, 0x08);
    if (argc > 1) {
        unsigned v = (unsigned)strtoul(argv[1], NULL, 16);
        if (v >= 1 && v <= 3)
            base = *(unsigned far *)MK_FP(0x40, 0x08 + 2 * (v - 1));
        else
            base = v;
    }
    if (!base) {
        printf("BRAIPLAY: no printer port.\n");
        beeps(5);
        return 2;
    }

    f = fopen(argv[0], "rb");
    if (!f) {
        printf("BRAIPLAY: cannot open %s\n", argv[0]);
        beeps(5);
        return 2;
    }
    fseek(f, 0L, SEEK_END);
    pos = ftell(f) - 12;
    fseek(f, (long)pos, SEEK_SET);
    if (fread(trailer, 1, 12, f) != 12 || memcmp(trailer, MAGIC, 8)) {
        printf("BRAIPLAY: no speech data in this file.\n");
        beeps(5);
        return 2;
    }
    size = trailer[8] | ((unsigned long)trailer[9] << 8) | ((unsigned long)trailer[10] << 16)
         | ((unsigned long)trailer[11] << 24);
    fseek(f, (long)(pos - size), SEEK_SET);

    printf("BRAIPLAY: port %Xh. Esc stops.\n", base);
    wire(3);                            /* both lines idle high, as TALKHUN leaves them */

    while (!stopped_by_key && (kind = fgetc(f)) != EOF && kind != 'E') {
        if (kind == 'P') {
            unsigned ms = rd16(f);
            wait_ticks((unsigned)((ms + 27) / 55));
            if (escape_pressed())
                stopped_by_key = 1;
        } else if (kind == 'U') {
            unsigned char vol = (unsigned char)fgetc(f), pitch = (unsigned char)fgetc(f);
            unsigned char cmd = (unsigned char)fgetc(f), flags = (unsigned char)fgetc(f);
            unsigned n = rd16(f), i;
            int bad = 0;
            if (n > MAX_FRAMES) {
                printf("BRAIPLAY: a unit of %u frames is too long.\n", n);
                break;
            }
            fread(frames, 5, n, f);
            units++;
            if (poll()) {               /* idle: the start sequence */
                send(&vol, 1);
                if (poll()) {
                    bad = 1;
                    if (units == 1)
                        never = 1;
                } else {
                    send(&pitch, 1);
                    if (poll())
                        bad = 1;
                    else {
                        msg[0] = 0; msg[1] = cmd;
                        send(msg, 2);
                    }
                }
            }
            for (i = 0; !bad && i < n; i++) {
                if (poll()) {
                    bad = 1;
                    break;
                }
                send(frames + 5 * i, 5);
                sent++;
            }
            if (!bad && (flags & 1)) {
                if (poll())
                    bad = 1;
                else {
                    msg[0] = 0; msg[1] = 0xA0;
                    send(msg, 2);
                }
            }
            if (bad) {
                if (!errors) {
                    first_err_unit = (unsigned)units;
                    first_err_frame = i;
                    first_err_status = last_status;
                }
                errors++;
                if (never)
                    break;
            }
            if (escape_pressed())
                stopped_by_key = 1;
        } else {
            printf("BRAIPLAY: bad record %02X.\n", kind);
            break;
        }
    }
    fclose(f);

    if (stopped_by_key) {               /* leave the chip stopped */
        if (!poll()) {
            msg[0] = 0; msg[1] = 0xA0;
            send(msg, 2);
        }
    }
    printf("BRAIPLAY: %lu units, %lu frames sent, %u units cut short.\n", units, sent, errors);
    if (never) {
        printf("The box never answered (status %02Xh). Connected and powered? TALKHUN must not be loaded.\n",
               first_err_status);
        beeps(5);
        return 2;
    }
    if (errors) {
        printf("First trouble: unit %u, frame %u, status %02Xh.\n", first_err_unit, first_err_frame,
               first_err_status);
        beeps(3);
        return 1;
    }
    if (!stopped_by_key)
        beep(660, 9);
    return 0;
}
