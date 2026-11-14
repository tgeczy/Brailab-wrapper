/* brailab_voice.c -- see brailab_voice.h.
 *
 * Each clause is captured and rendered on its own, from a fresh core: the engine's
 * own intonation units are the only safe places to split, since each one carries its
 * own contour.  Fades go only at the very start and end of an utterance, never between
 * blocks or clauses, so one block is held back to know which is the last.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "brailab_voice.h"
#include "pcf8200.h"
#include "pcf8200_tables.h"

#define MAX_FRAME (2 * PCF8200_MAX_FRAME_SAMPLES)
#define START_PITCH_BYTE 46
#define OUT_SCALE 20000.0
#define FADE_SAMPLES 40
#define HALF_PI 1.5707963267948966

struct brailab_voice {
    talkhun *engine;
    pcf8200_params params;

    uint8_t *text, *clause;     /* the utterance, and a clause as the engine gets it */
    int len, pos, cap;
    double pitch, time_scale, gain;
    int furcsa, flat_pitch;
    int failed;

    const talkhun_item *items;  /* the clause */
    int count, item, in_clause;
    pcf8200_core core;
    pcf8200_tracker tracker;

    double amp[MAX_FRAME], hz[MAX_FRAME], out[MAX_FRAME];     /* the frame */
    uint8_t voiced[MAX_FRAME];
    double fc[PCF8200_MAX_FORMANTS * MAX_FRAME], bw[PCF8200_MAX_FORMANTS * MAX_FRAME];
    int frame_len, frame_pos;

    double block[2][BRAILAB_VOICE_BLOCK];
    int held, held_len;         /* the block waiting for its successor */
    int first;
};

static int is_delimiter(uint8_t c)
{
    return c != 0 && strchr(".,;:?!", c) != NULL;
}

/* What Python's str.strip() drops, as CWI-2 (CP437): 0xFF is the no-break space. */
static int is_blank(uint8_t c)
{
    return c == ' ' || (c >= 9 && c <= 13) || (c >= 0x1C && c <= 0x1F) || c == 0xFF;
}

static int has_text(const uint8_t *s, int n)
{
    int i;
    for (i = 0; i < n; i++)
        if (!is_blank(s[i]))
            return 1;
    return 0;
}

/* Capture the next clause that has anything in it.  0 when there is none left. */
static int next_clause(brailab_voice *v)
{
    while (v->pos < v->len) {
        const int start = v->pos;
        uint8_t esc[3] = {27, 'F', 0};
        int n, i, female = 0;

        while (v->pos < v->len && !is_delimiter(v->text[v->pos]))
            v->pos++;
        if (v->pos < v->len)
            v->pos++;
        n = v->pos - start;
        if (!has_text(v->text + start, n))
            continue;
        for (i = 0; i < n; i++) {
            const uint8_t c = v->text[start + i];
            v->clause[i] = c == BRAILAB_VOICE_UNKNOWN ? '?' : c;
        }
        /* A lone capital reads as a Roman numeral ("I" is "first"); a trailing
         * space makes the engine read it as the letter. */
        if (n == 1)
            v->clause[n++] = ' ';
        /* An unknown character says '?' but ends nothing, so the clause still needs
         * its full stop, which talkhun_capture wouldn't add after a '?'. */
        else if (v->text[v->pos - 1] == BRAILAB_VOICE_UNKNOWN)
            v->clause[n++] = '.';
        esc[2] = v->furcsa ? '1' : '0';
        if (talkhun_feed(v->engine, esc, 3))
            return v->failed = 1, 0;
        v->count = talkhun_capture(v->engine, v->clause, n, &v->items);
        if (v->count < 0)
            return v->failed = 1, 0;
        for (i = 0; i < v->count; i++) {
            const uint8_t b = v->items[i].data[1];
            if (v->items[i].kind == TALKHUN_CTRL && !(b & 0x20) && (b & 0x10))
                female = 1;
        }
        pcf8200_tracker_init(&v->tracker, &v->params, female, 0, v->flat_pitch, v->time_scale,
                             START_PITCH_BYTE);
        pcf8200_init(&v->core, v->tracker.nf, &v->params);
        v->item = 0;
        v->in_clause = 1;
        v->frame_len = v->frame_pos = 0;
        return 1;
    }
    return 0;
}

/* Render the clause's next frame.  0 when there is none left. */
static int next_frame(brailab_voice *v)
{
    while (v->item < v->count) {
        const talkhun_item *it = &v->items[v->item++];
        if (it->kind == TALKHUN_PITCH) {
            int byte = it->data[0];
            if (v->pitch != 1.0) {
                byte = (int)rint(byte * v->pitch);
                byte = byte < 1 ? 1 : byte > 255 ? 255 : byte;
            }
            pcf8200_tracker_pitch(&v->tracker, byte);
        } else if (it->kind == TALKHUN_FRAME) {
            const int n = pcf8200_tracker_frame(&v->tracker, it->data, v->amp, v->hz, v->voiced,
                                                v->fc, v->bw, MAX_FRAME);
            /* pcf8200_run wants its rows n apart */
            int i;
            for (i = 1; i < v->tracker.nf; i++) {
                memmove(v->fc + i * n, v->fc + i * MAX_FRAME, (size_t)n * sizeof(double));
                memmove(v->bw + i * n, v->bw + i * MAX_FRAME, (size_t)n * sizeof(double));
            }
            pcf8200_run(&v->core, v->amp, v->hz, v->voiced, v->fc, v->bw, n, v->out);
            v->frame_len = n;
            v->frame_pos = 0;
            return 1;
        }
    }
    return 0;
}

/* The next block: full, or what ends a clause.  0 when the utterance is out. */
static int next_block(brailab_voice *v, double *out)
{
    for (;;) {
        int n = 0;
        while (v->in_clause && n < BRAILAB_VOICE_BLOCK) {
            int take;
            if (v->frame_pos == v->frame_len && !next_frame(v)) {
                v->in_clause = 0;
                break;
            }
            take = v->frame_len - v->frame_pos;
            if (take > BRAILAB_VOICE_BLOCK - n)
                take = BRAILAB_VOICE_BLOCK - n;
            memcpy(out + n, v->out + v->frame_pos, (size_t)take * sizeof(double));
            v->frame_pos += take;
            n += take;
        }
        if (n)
            return n;
        if (!next_clause(v))
            return 0;
    }
}

static void fade(double *x, int n, int in, int out)
{
    const int nf = n / 2 < FADE_SAMPLES ? n / 2 : FADE_SAMPLES;
    int i;
    if (nf < 2)
        return;
    for (i = 0; i < nf; i++) {
        const double s = i == nf - 1 ? 1.0 : sin(i * (HALF_PI / (nf - 1)));
        const double w = s * s;
        if (in)
            x[i] *= w;
        if (out)
            x[n - 1 - i] *= w;
    }
}

brailab_voice *brailab_voice_create(const uint8_t *com, int len)
{
    static const pcf8200_params device = PCF8200_DEVICE_PARAMS;
    brailab_voice *v = (brailab_voice *)calloc(1, sizeof *v);
    if (!v)
        return NULL;
    v->params = device;
    v->engine = talkhun_create(com, len);
    if (!v->engine) {
        free(v);
        return NULL;
    }
    return v;
}

void brailab_voice_destroy(brailab_voice *v)
{
    if (!v)
        return;
    talkhun_destroy(v->engine);
    free(v->text);
    free(v->clause);
    free(v);
}

int brailab_voice_begin(brailab_voice *v, const uint8_t *text, int len, double pitch,
                        double time_scale, int furcsa, int intonation, double gain)
{
    if (len < 0 || pitch <= 0.0 || time_scale <= 0.0 || time_scale > 2.0)
        return -1;
    if (len > v->cap) {
        uint8_t *p = (uint8_t *)realloc(v->text, (size_t)len);
        if (!p)
            return -1;
        v->text = p;
        p = (uint8_t *)realloc(v->clause, (size_t)len + 2);
        if (!p)
            return -1;
        v->clause = p;
        v->cap = len;
    }
    if (len)
        memcpy(v->text, text, (size_t)len);
    v->len = len;
    v->pos = 0;
    v->pitch = pitch;
    v->time_scale = time_scale;
    v->furcsa = furcsa;
    v->flat_pitch = !intonation;
    v->gain = gain;
    v->failed = 0;
    v->in_clause = 0;
    v->held = 0;
    v->held_len = 0;
    v->first = 1;
    return 0;
}

int brailab_voice_read(brailab_voice *v, int16_t *pcm, int max)
{
    const double scale = OUT_SCALE * v->gain;
    double *x;
    int n, next, i;

    if (max < BRAILAB_VOICE_BLOCK)
        return -1;
    if (!v->held_len)
        v->held_len = next_block(v, v->block[v->held]);
    if (v->failed)
        return -1;
    n = v->held_len;
    if (!n)
        return 0;
    next = next_block(v, v->block[!v->held]);
    if (v->failed)
        return -1;
    x = v->block[v->held];
    fade(x, n, v->first, next == 0);
    v->first = 0;
    for (i = 0; i < n; i++) {
        double y = x[i] * scale;
        y = y < -32767.0 ? -32767.0 : y > 32767.0 ? 32767.0 : y;
        pcm[i] = (int16_t)y;
    }
    v->held = !v->held;
    v->held_len = next;
    return n;
}
