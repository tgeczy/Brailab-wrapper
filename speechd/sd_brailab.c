/*
 * sd_brailab -- a speech-dispatcher output module: the BraiLab PC's voice, as in the NVDA add-on, in one process
 * with no Python.  The 1991 TALKHUN0.COM runs on MAME's 8086 and drives a model of the Philips PCF8200
 * (talkhun_emu/csrc/brailab_voice.c); this file speaks the protocol.
 *
 * The protocol and its audio (705 blocks, HDLC-escaped, played and flushed by the server) follow speech-dispatcher's
 * module_process.c, as ssi263-speech's sd_ssi263 does, which this is modelled on.  Synthesis is synchronous: stdin
 * is polled for STOP between blocks.  Two voices: "BraiLab PC" and "BraiLab PC furcsa" (the weird voice), Hungarian.
 * Rate, pitch and volume come from SSIP, mapped as the NVDA driver maps its sliders.
 *
 * Config (argv[1], speech-dispatcher's module config; then this user's own file, whose keys win:
 * $XDG_CONFIG_HOME/brailab/sd_brailab.conf, else ~/.config/brailab/sd_brailab.conf; every key optional):
 *   BrailabDataDir "/usr/local/share/brailab"   where TALKHUN0.COM is
 *   BrailabIntonation 1                         0: each clause held at its start pitch
 * BRAILAB_DATADIR overrides the data folder.  TALKHUN0.COM is Arató András's program and not part of this one.
 * MIT.
 */
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <unistd.h>

#include "brailab_voice.h"

#define RATE 10000

/* ---- stdin: one raw buffer for lines and the STOP poll (never stdio on stdin) ---------------------------------- */
static char *rbuf;
static size_t rlen, rcap;
static int r_eof;

static void rappend(const char *p, size_t n)
{
    if (rlen + n + 1 > rcap) {
        size_t cap = rcap ? rcap : 8192;
        while (cap < rlen + n + 1)
            cap *= 2;
        rbuf = (char *)realloc(rbuf, cap);
        if (!rbuf)
            exit(1);
        rcap = cap;
    }
    memcpy(rbuf + rlen, p, n);
    rlen += n;
    rbuf[rlen] = 0;
}

/* The next line, without its \r\n, malloc'd; NULL at EOF. */
static char *readline_sd(void)
{
    for (;;) {
        char *nl = rbuf ? (char *)memchr(rbuf, '\n', rlen) : NULL;
        if (nl) {
            size_t n = (size_t)(nl - rbuf);
            char *line = (char *)malloc(n + 1);
            memcpy(line, rbuf, n);
            line[n] = 0;
            if (n && line[n - 1] == '\r')
                line[n - 1] = 0;
            memmove(rbuf, nl + 1, rlen - n - 1);
            rlen -= n + 1;
            rbuf[rlen] = 0;
            return line;
        }
        if (r_eof)
            return NULL;
        {
            char buf[4096];
            ssize_t k = read(STDIN_FILENO, buf, sizeof buf);
            if (k <= 0) {
                r_eof = 1;
                continue;
            }
            rappend(buf, (size_t)k);
        }
    }
}

/* STOP (or CANCEL or PAUSE) waiting on stdin?  Reads what is there, and leaves it for readline_sd. */
static int poll_stop(void)
{
    fd_set f;
    struct timeval tv = {0, 0};
    FD_ZERO(&f);
    FD_SET(STDIN_FILENO, &f);
    if (select(STDIN_FILENO + 1, &f, NULL, NULL, &tv) > 0) {
        char buf[4096];
        ssize_t k = read(STDIN_FILENO, buf, sizeof buf);
        if (k <= 0) {
            r_eof = 1;
            return 1;
        }
        rappend(buf, (size_t)k);
    }
    return rbuf && (strstr(rbuf, "STOP") || strstr(rbuf, "CANCEL") || strstr(rbuf, "PAUSE"));
}

static void send_line(const char *s)
{
    fputs(s, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

/* 705: 16-bit mono little-endian, the payload HDLC-escaped (0x7D and '\n' become 0x7D, byte ^ 0x20) */
static void send_audio(const int16_t *pcm, int n)
{
    const unsigned char *p = (const unsigned char *)pcm, *end = p + (size_t)n * 2;
    printf("705-bits=16\n705-num_channels=1\n705-sample_rate=%d\n705-num_samples=%d\n705-big_endian=0\n705-AUDIO",
           RATE, n);
    fputc(0, stdout);
    for (; p < end; p++) {
        if (*p == 0x7D || *p == '\n') {
            fputc(0x7D, stdout);
            fputc(*p ^ 0x20, stdout);
        } else {
            fputc(*p, stdout);
        }
    }
    fputs("\n705 AUDIO\n", stdout);
    fflush(stdout);
}

/* ---- text ------------------------------------------------------------------------------------------------------ */

/* SSML tags dropped, XML's five entities decoded. */
static void strip_ssml(char *s)
{
    static const char *ent[][2] = {{"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"}, {"&quot;", "\""}, {"&apos;", "'"}};
    char *r = s, *w = s;
    int tag = 0, k;
    while (*r) {
        if (*r == '<') {
            tag = 1;
            r++;
            continue;
        }
        if (*r == '>' && tag) {
            tag = 0;
            r++;
            continue;
        }
        if (tag) {
            r++;
            continue;
        }
        if (*r == '&') {
            for (k = 0; k < 5; k++) {
                size_t n = strlen(ent[k][0]);
                if (!strncmp(r, ent[k][0], n)) {
                    *w++ = ent[k][1][0];
                    r += n;
                    break;
                }
            }
            if (k < 5)
                continue;
        }
        *w++ = *r++;
    }
    *w = 0;
}

/* TALKHUN0 (1991) reads CWI-2, the Hungarian DOS page from before CP852: CP437, with o and u double acute in
 * the slots of o and u circumflex.  CP437's upper half, as Unicode: */
static const unsigned short CP437[128] = {
    0x00C7, 0x00FC, 0x00E9, 0x00E2, 0x00E4, 0x00E0, 0x00E5, 0x00E7,
    0x00EA, 0x00EB, 0x00E8, 0x00EF, 0x00EE, 0x00EC, 0x00C4, 0x00C5,
    0x00C9, 0x00E6, 0x00C6, 0x00F4, 0x00F6, 0x00F2, 0x00FB, 0x00F9,
    0x00FF, 0x00D6, 0x00DC, 0x00A2, 0x00A3, 0x00A5, 0x20A7, 0x0192,
    0x00E1, 0x00ED, 0x00F3, 0x00FA, 0x00F1, 0x00D1, 0x00AA, 0x00BA,
    0x00BF, 0x2310, 0x00AC, 0x00BD, 0x00BC, 0x00A1, 0x00AB, 0x00BB,
    0x2591, 0x2592, 0x2593, 0x2502, 0x2524, 0x2561, 0x2562, 0x2556,
    0x2555, 0x2563, 0x2551, 0x2557, 0x255D, 0x255C, 0x255B, 0x2510,
    0x2514, 0x2534, 0x252C, 0x251C, 0x2500, 0x253C, 0x255E, 0x255F,
    0x255A, 0x2554, 0x2569, 0x2566, 0x2560, 0x2550, 0x256C, 0x2567,
    0x2568, 0x2564, 0x2565, 0x2559, 0x2558, 0x2552, 0x2553, 0x256B,
    0x256A, 0x2518, 0x250C, 0x2588, 0x2584, 0x258C, 0x2590, 0x2580,
    0x03B1, 0x00DF, 0x0393, 0x03C0, 0x03A3, 0x03C3, 0x00B5, 0x03C4,
    0x03A6, 0x0398, 0x03A9, 0x03B4, 0x221E, 0x03C6, 0x03B5, 0x2229,
    0x2261, 0x00B1, 0x2265, 0x2264, 0x2320, 0x2321, 0x00F7, 0x2248,
    0x00B0, 0x2219, 0x00B7, 0x221A, 0x207F, 0x00B2, 0x25A0, 0x00A0,
};

/* CWI-2's own letters, and the capitals CP437 hasn't got, folded to the lowercase byte: the engine speaks
 * words, not case.  Fed as CP852, every one of these was spelled out as a code ("kod 8b"). */
static const struct { unsigned short cp; unsigned char b; } CWI2[] = {
    {0x0151, 0x93}, {0x0150, 0x93}, {0x0171, 0x96}, {0x0170, 0x96},     /* o, u double acute */
    {0x00C1, 0xA0}, {0x00CD, 0xA1}, {0x00D3, 0xA2}, {0x00DA, 0xA3},     /* capital A, I, O, U acute */
};

/* UTF-8 to CWI-2, in place (it never grows).  A character CWI-2 hasn't got, or a broken sequence, becomes
 * BRAILAB_VOICE_UNKNOWN, one per character, as the NVDA driver's encoding does. */
static int to_cwi2(char *s)
{
    unsigned char *r = (unsigned char *)s, *w = r;
    while (*r) {
        unsigned c = *r, cp;
        int extra, i;
        if (c < 0x80) {
            *w++ = *r++;
            continue;
        }
        extra = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : -1;
        if (extra < 0) {
            *w++ = BRAILAB_VOICE_UNKNOWN;
            r++;
            continue;
        }
        cp = c & (0x3F >> extra);
        for (i = 1; i <= extra; i++) {
            if ((r[i] & 0xC0) != 0x80)
                break;
            cp = (cp << 6) | (r[i] & 0x3F);
        }
        if (i <= extra) {
            *w++ = BRAILAB_VOICE_UNKNOWN;
            r++;
            continue;
        }
        r += extra + 1;
        for (i = 0; i < (int)(sizeof CWI2 / sizeof CWI2[0]) && CWI2[i].cp != cp; i++)
            ;
        if (i < (int)(sizeof CWI2 / sizeof CWI2[0])) {
            *w++ = CWI2[i].b;
            continue;
        }
        for (i = 0; i < 128 && CP437[i] != cp; i++)
            ;
        *w++ = i < 128 ? (unsigned char)(0x80 + i) : BRAILAB_VOICE_UNKNOWN;
    }
    *w = 0;
    return (int)(w - (unsigned char *)s);
}

/* ---- config ---------------------------------------------------------------------------------------------------- */
static char datadir[1024];
static int intonation = 1;

static void read_config(const char *path)
{
    FILE *f = fopen(path, "r");
    char line[1200], key[128], val[1024];
    if (!f)
        return;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#')
            continue;
        if (sscanf(line, "%127s \"%1023[^\"]\"", key, val) != 2 && sscanf(line, "%127s %1023s", key, val) != 2)
            continue;
        if (!strcmp(key, "BrailabDataDir"))
            snprintf(datadir, sizeof datadir, "%s", val);
        else if (!strcmp(key, "BrailabIntonation"))
            intonation = atoi(val) != 0;
    }
    fclose(f);
}

static void read_user_config(void)
{
    char p[1200];
    const char *xdg = getenv("XDG_CONFIG_HOME"), *home = getenv("HOME");
    if (xdg && *xdg)
        snprintf(p, sizeof p, "%s/brailab/sd_brailab.conf", xdg);
    else if (home && *home)
        snprintf(p, sizeof p, "%s/.config/brailab/sd_brailab.conf", home);
    else
        return;
    read_config(p);
}

static unsigned char *load_talkhun(int *len)
{
    const char *env = getenv("BRAILAB_DATADIR");
    char path[1100];
    FILE *f;
    unsigned char *image;
    long n;
    if (env && *env)
        snprintf(datadir, sizeof datadir, "%s", env);
    if (!*datadir)
        snprintf(datadir, sizeof datadir, "/usr/local/share/brailab");
    snprintf(path, sizeof path, "%s/TALKHUN0.COM", datadir);
    f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    image = (unsigned char *)malloc(n > 0 ? (size_t)n : 1);
    if (!image || n <= 0 || fread(image, 1, (size_t)n, f) != (size_t)n) {
        free(image);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *len = (int)n;
    return image;
}

/* ---- speaking -------------------------------------------------------------------------------------------------- */
static const char *VOICES[2] = {"BraiLab PC", "BraiLab PC furcsa"};
static brailab_voice *voice;
static int furcsa = 0;
static int ssip_rate = 0, ssip_pitch = 0, ssip_volume = 100;

static int to100(int ssip)                           /* SSIP -100..100 to the NVDA driver's 0..100 (0 is 50) */
{
    int v = (ssip + 100) / 2;
    return v < 0 ? 0 : v > 100 ? 100 : v;
}

static void speak(char *text)
{
    static int16_t pcm[BRAILAB_VOICE_BLOCK];
    const double rate = to100(ssip_rate), pitch = to100(ssip_pitch), volume = to100(ssip_volume);
    int len, n, stopped = 0;

    strip_ssml(text);
    len = to_cwi2(text);
    if (poll_stop()) {                               /* already stopped (key repeat): nothing to say */
        send_line("200 OK SPEAKING");
        send_line("701 BEGIN");
        send_line("703 STOP");
        return;
    }
    send_line("200 OK SPEAKING");
    send_line("701 BEGIN");
    /* the NVDA driver's _timeScale, _pitchFactor and gain */
    if (brailab_voice_begin(voice, (const uint8_t *)text, len, pow(2.0, (pitch - 50.0) / 100.0),
                            0.9 - 0.55 * (rate / 100.0), furcsa, intonation, 0.25 + volume / 100.0) == 0) {
        while ((n = brailab_voice_read(voice, pcm, BRAILAB_VOICE_BLOCK)) > 0) {
            send_audio(pcm, n);
            if (poll_stop()) {
                stopped = 1;
                break;
            }
        }
    }
    send_line(stopped ? "703 STOP" : "702 END");
}

static char *read_text(void)
{
    char *text = (char *)calloc(1, 1), *line;
    size_t n = 0;
    while ((line = readline_sd()) != NULL) {
        const char *s = line;
        size_t k;
        if (!strcmp(line, ".")) {
            free(line);
            break;
        }
        if (s[0] == '.')                             /* a leading dot is escaped as two */
            s++;
        k = strlen(s);
        text = (char *)realloc(text, n + k + 2);
        if (n)
            text[n++] = ' ';
        memcpy(text + n, s, k);
        n += k;
        text[n] = 0;
        free(line);
    }
    return text;
}

static void set_param(char *key, const char *val)
{
    char *k;
    for (k = key; *k; k++)
        *k = (char)(*k >= 'A' && *k <= 'Z' ? *k + 32 : *k);
    if (!strcmp(key, "rate"))
        ssip_rate = atoi(val);
    else if (!strcmp(key, "pitch"))
        ssip_pitch = atoi(val);
    else if (!strcmp(key, "volume"))
        ssip_volume = atoi(val);
    else if (!strcmp(key, "synthesis_voice")) {      /* "NULL" or a name we haven't got: no change */
        if (!strcmp(val, VOICES[0]))
            furcsa = 0;
        else if (!strcmp(val, VOICES[1]))
            furcsa = 1;
    }
}

int main(int argc, char **argv)
{
    char *cmd;
    unsigned char *image;
    int len = 0;

    setvbuf(stdout, NULL, _IOFBF, 1 << 16);
    signal(SIGPIPE, SIG_IGN);
    if (argc > 1)
        read_config(argv[1]);
    read_user_config();
    cmd = readline_sd();
    if (!cmd || strcmp(cmd, "INIT"))
        return 1;
    free(cmd);
    image = load_talkhun(&len);
    voice = image ? brailab_voice_create(image, len) : NULL;
    if (!voice) {
        char msg[1200];
        snprintf(msg, sizeof msg, image ? "399-TALKHUN0.COM in %s did not install"
                                        : "399-no TALKHUN0.COM in the data folder %s", datadir);
        free(image);
        send_line(msg);
        send_line("399 ERR CANT INIT MODULE");
        return 1;
    }
    free(image);
    send_line("299-the BraiLab PC: TALKHUN0 on an emulated 8086, through a model of the PCF8200");
    send_line("299 OK LOADED SUCCESSFULLY");
    while ((cmd = readline_sd()) != NULL) {
        if (!strcmp(cmd, "SPEAK") || !strcmp(cmd, "CHAR") || !strcmp(cmd, "KEY") || !strcmp(cmd, "SOUND_ICON")) {
            int is_key = !strcmp(cmd, "KEY"), icon = !strcmp(cmd, "SOUND_ICON");
            char *text;
            send_line("202 OK RECEIVING MESSAGE");
            text = read_text();
            if (is_key) {
                char *c;
                for (c = text; *c; c++)
                    if (*c == '_')
                        *c = ' ';
            }
            if (icon || !*text) {                    /* no sound icons: an empty message still completes */
                send_line("200 OK SPEAKING");
                send_line("701 BEGIN");
                send_line("702 END");
            } else {
                speak(text);
            }
            free(text);
        } else if (!strcmp(cmd, "STOP") || !strcmp(cmd, "CANCEL") || !strcmp(cmd, "PAUSE")) {
            /* only between messages here (during one, speak() catches it): nothing is playing */
        } else if (!strcmp(cmd, "SET")) {
            char *line;
            send_line("202 OK RECEIVING MESSAGE");
            while ((line = readline_sd()) != NULL) {
                char *eq;
                if (!strcmp(line, ".")) {
                    free(line);
                    break;
                }
                eq = strchr(line, '=');
                if (eq) {
                    *eq = 0;
                    set_param(line, eq + 1);
                }
                free(line);
            }
            send_line("203 OK SETTINGS RECEIVED");
        } else if (!strcmp(cmd, "AUDIO") || !strcmp(cmd, "LOGLEVEL") || !strcmp(cmd, "DEBUG")) {
            char *line;
            send_line("202 OK RECEIVING MESSAGE");
            while ((line = readline_sd()) != NULL) {
                int end = !strcmp(line, ".");
                free(line);
                if (end)
                    break;
            }
            send_line("203 OK SETTINGS RECEIVED");
        } else if (!strcmp(cmd, "LIST VOICES")) {
            printf("200-%s\thu\tMALE1\n", VOICES[0]);
            printf("200-%s\thu\tMALE2\n", VOICES[1]);
            send_line("249 OK VOICES LISTED");
        } else if (!strcmp(cmd, "QUIT")) {
            free(cmd);
            break;
        } else {
            send_line("300 ERR UNKNOWN COMMAND");
        }
        free(cmd);
    }
    brailab_voice_destroy(voice);
    return 0;
}
