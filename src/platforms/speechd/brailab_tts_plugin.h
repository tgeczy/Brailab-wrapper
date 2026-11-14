/*
 * brailab_tts_plugin.h -- what sd_brailab asks of an optional voice plug-in.
 *
 * sd_brailab can offer one more voice, "BraiLab TTS", when a shared library with these six functions is in its
 * data folder (libbrailab_tts.so, or the file BrailabTtsPlugin names).  The plug-in is an optional binary and is
 * not built from this repository; without it the module is exactly what it was.
 *
 * One voice per process, and one thread: every call comes from the thread that called open, and say returns
 * only when the text has been said or the sink has asked for a stop.  The plug-in keeps no thread of its own.
 * MIT.
 */
#ifndef BRAILAB_TTS_PLUGIN_H
#define BRAILAB_TTS_PLUGIN_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BRAILAB_TTS_API 1

/* Samples as they are made: 16-bit mono at brailab_tts_sample_rate().  Return nonzero to stop the message. */
typedef int (*brailab_tts_sink)(void *user, const int16_t *pcm, int n);

/* BRAILAB_TTS_API of the plug-in; the module loads nothing else. */
int brailab_tts_api_version(void);

/* data_dir: the folder with the voice's two data files (binadata.bin, binahank.bin; capitals are found too).
 * 0, or a negative number when the files are not there or are not the right ones. */
int brailab_tts_open(const char *data_dir);
void brailab_tts_close(void);

int brailab_tts_sample_rate(void);

/* tempo 0..9 (4 is the voice's own), pitch -1..1 (0), volume -2..2 (0); values outside are clamped. */
int brailab_tts_set(int tempo, int pitch, int volume);

/* Says UTF-8 text of any length through the sink.  0: said to the end; 1: the sink stopped it (the next say
 * starts clean); negative: nothing was said. */
int brailab_tts_say(const char *utf8, brailab_tts_sink sink, void *user);

#ifdef __cplusplus
}
#endif
#endif
