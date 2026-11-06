/* talkhun_host.h -- the 1991 TALKHUN0.COM, resident on MAME's 8086.
 *
 * The same host as talkhun.py, which ran it on Unicorn: a .COM image in, the frames
 * it sends to the BraiLab adapter out.  TALKHUN0 itself is not part of this source.
 * MIT.
 */
#ifndef TALKHUN_HOST_H
#define TALKHUN_HOST_H

#include <stdint.h>

#ifdef _WIN32
#define TALKHUN_API __declspec(dllexport)
#else
#define TALKHUN_API __attribute__((visibility("default")))
#endif

enum { TALKHUN_FRAME, TALKHUN_CTRL, TALKHUN_PITCH };

typedef struct {
    int kind;
    uint8_t data[5];        /* 5 bytes of frame, 2 of control, or the pitch byte */
} talkhun_item;

typedef struct talkhun talkhun;

#ifdef __cplusplus
extern "C" {
#endif

/* Runs the program's own installer up to its TSR call, then resets its settings.
 * NULL if that fails. */
TALKHUN_API talkhun *talkhun_create(const uint8_t *com, int len);
TALKHUN_API void talkhun_destroy(talkhun *t);
TALKHUN_API int talkhun_reset(talkhun *t);          /* INT 14h AH=0; 0 = done */
/* INT 14h AH=1: characters into the ESC parser, nothing collected.  0 = done. */
TALKHUN_API int talkhun_feed(talkhun *t, const uint8_t *text, int len);
/* Speak `text` (the program's own character set): the adapter traffic, in order, valid
 * until the next call.  A full stop is added if the text ends without a delimiter,
 * since the program holds a line until one arrives.  Returns the count, or -1. */
TALKHUN_API int talkhun_capture(talkhun *t, const uint8_t *text, int len,
                                const talkhun_item **items);

#ifdef __cplusplus
}
#endif
#endif
