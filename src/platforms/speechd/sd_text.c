/*
 * sd_text.c -- a message's text made ready for a voice: SSML taken off, and UTF-8 turned into the BraiLab PC's
 * own character set.  MIT.
 */
#include <string.h>

#include "brailab_voice.h"
#include "sd_text.h"

/* SSML tags dropped, XML's five entities decoded. */
void sd_strip_ssml(char *s)
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
int sd_to_cwi2(char *s)
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
