/* say.c -- feed text to the resident TALKHUN through its INT 14h API.
 *
 *   SAY text to speak.        speak (a delimiter is appended if missing)
 *   SAY /R                    AH=0 reset to the driver's defaults
 *   SAY /C                    send the standard configuration TALKHUN got
 *                             from HUN.BAT (ESC defaults, BIOS10BE): DOSBox's
 *                             "copy X com4" never reaches the INT 14h hook,
 *                             so this does it in-process.
 *   SAY /E<seq>               raw ESC sequence, e.g. /EF1 = furcsa on
 *   SAY /F file               speak the file's text (CP852), line by line
 *   SAY /T                    self-test: beep, speak a sentence, wait, beep
 *
 * The API, recovered from the 1991 handler: INT 14h with DL=3 (COM4),
 * AH=0 reset, AH=1 AL=char feed one byte, AH=3 status (AX=0x30 when the
 * driver is resident).  Text is CP852 on the wire; the DOS code page of the
 * console is what you type, so no conversion is done here. */
#include <stdio.h>
#include <string.h>
#include <dos.h>
#include <i86.h>
#include <conio.h>

static int present(void)
{
    union REGS r;
    r.h.ah = 3; r.h.dl = 3; r.x.ax = 0x0300;
    int86(0x14, &r, &r);
    return r.x.ax == 0x30;
}

static void feed(const char *s)
{
    union REGS r;
    while (*s) {
        r.h.ah = 1; r.h.al = (unsigned char)*s++; r.h.dl = 3;
        int86(0x14, &r, &r);
    }
}

static void beep(void)
{
    volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
    unsigned long t0 = *bios;
    outp(0x43, 0xB6); outp(0x42, 0xA9); outp(0x42, 0x04);       /* ~1 kHz */
    outp(0x61, inp(0x61) | 3);
    while (*bios - t0 < 5) ;
    outp(0x61, inp(0x61) & ~3);
}

static unsigned queued(void)
{
    union REGS r;
    r.h.ah = 0xFD; int86(0x61, &r, &r);
    return r.x.dx;
}

static void reset(void)
{
    union REGS r;
    r.h.ah = 0; r.h.dl = 3;
    int86(0x14, &r, &r);
}

int main(int argc, char **argv)
{
    char buf[512];
    int i, n = 0;

    if (!present()) {
        printf("say: TALKHUN is not resident (INT 14h AH=3 DL=3 != 0x30)\r\n");
        return 1;
    }
    if (argc < 2) {
        printf("usage: SAY text | /R | /C | /Eseq\r\n");
        return 1;
    }
    if (argv[1][0] == '/') {
        switch (argv[1][1] & 0xDF) {
        case 'R': reset(); printf("reset\r\n"); return 0;
        case 'C':
            feed("\x1bP*\x1bS6\x1bF0\x1bR0\x1bC1\x1bE1\x1bK1");   /* DEFAULT */
            feed("\x1bAF");                                     /* BIOS10BE */
            feed("\x1bT0");                                     /* ECHOKI */
            printf("configured\r\n");
            return 0;
        case 'F': {
            FILE *fp = fopen(argc > 2 ? argv[2] : argv[1] + 2, "rb");
            if (!fp) { printf("say: cannot open file\r\n"); return 1; }
            while (fgets(buf, sizeof buf - 2, fp)) {
                n = strlen(buf);
                while (n && (buf[n-1] == '\r' || buf[n-1] == '\n')) buf[--n] = 0;
                if (!n) continue;
                if (!strchr(".,;:?!", buf[n - 1])) { buf[n++] = '.'; buf[n] = 0; }
                feed(buf);
            }
            fclose(fp);
            return 0;
        }
        case 'T': {
            volatile unsigned long far *bios = (volatile unsigned long far *)MK_FP(0x40, 0x6C);
            unsigned long t0;
            while (queued()) ;                       /* let anything earlier finish */
            t0 = *bios; while (*bios - t0 < 6) ;
            beep();
            t0 = *bios; while (*bios - t0 < 6) ;
            feed("Ez egy pr\xa2ba, a hangsz\xa2r\xa2 j\xa2l sz\xa2l.");   /* CP852 */
            while (queued()) ;
            t0 = *bios; while (*bios - t0 < 2) ;     /* a jingle 110 ms after the text */
            beep();
            return 0;
        }
        case 'E':
            buf[0] = 0x1b; strcpy(buf + 1, argv[1] + 2); feed(buf);
            printf("sent ESC %s\r\n", argv[1] + 2);
            return 0;
        }
    }
    for (i = 1; i < argc; i++) {
        int l = strlen(argv[i]);
        if (n + l + 2 >= sizeof buf) break;
        if (n) buf[n++] = ' ';
        memcpy(buf + n, argv[i], l); n += l;
    }
    buf[n] = 0;
    if (n && !strchr(".,;:?!", buf[n - 1])) { buf[n++] = '.'; buf[n] = 0; }
    feed(buf);
    return 0;
}
