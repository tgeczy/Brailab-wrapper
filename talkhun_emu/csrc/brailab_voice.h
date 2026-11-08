/* brailab_voice.h -- the whole emulated voice: text in, 16-bit PCM at 10 kHz out.
 *
 * TALKHUN0 on MAME's 8086 feeds the PCF8200 core, clause by clause.  This is what the
 * NVDA add-on's driver does in Python up to 3.2.2, and any front end can use it: it
 * needs no Python, numpy or Unicorn.  The tests hold it to that older pipeline.
 * TALKHUN0 itself is not part of this source, so it is given as bytes.
 * MIT.
 */
#ifndef BRAILAB_VOICE_H
#define BRAILAB_VOICE_H

#include <stdint.h>

#include "talkhun_host.h"

/* The most samples brailab_voice_read gives at a time. */
#define BRAILAB_VOICE_BLOCK 4000

/* In the text, a character CWI-2 hasn't got, such as a dash or a curly quote.  The engine
 * hears '?' for it, as it always has, but it doesn't end a clause as a real '?' does. */
#define BRAILAB_VOICE_UNKNOWN 0x1A

typedef struct brailab_voice brailab_voice;

#ifdef __cplusplus
extern "C" {
#endif

/* NULL if the program doesn't install. */
TALKHUN_API brailab_voice *brailab_voice_create(const uint8_t *com, int len);
TALKHUN_API void brailab_voice_destroy(brailab_voice *v);

/* Start an utterance, dropping any unfinished one.  The text is in CWI-2 (see brailab_voice.encode).
 * pitch: a factor on the engine's own pitch, 1 leaves it.
 * time_scale: on the length of each frame, above 0 and at most 2; 1 leaves it.
 * furcsa: the weird voice.  intonation: 0 holds each clause at its start pitch.
 * gain: on the output, where 1 is 20000 at the chip's full scale.
 * Returns 0, or -1 if a value is out of range. */
TALKHUN_API int brailab_voice_begin(brailab_voice *v, const uint8_t *text, int len, double pitch,
                                    double time_scale, int furcsa, int intonation, double gain);

/* The next samples, into `pcm`, which holds at least BRAILAB_VOICE_BLOCK.  Returns
 * how many, 0 when the utterance is over, or -1 on failure. */
TALKHUN_API int brailab_voice_read(brailab_voice *v, int16_t *pcm, int max);

#ifdef __cplusplus
}
#endif
#endif
