/*
 * test_tts_stub.c -- a stand-in voice plug-in for the tests of sd_brailab's plug-in loading.  It is no voice:
 * every byte of the text becomes 80 samples whose value says which byte it was and what the settings were, so
 * a test can tell from the module's audio exactly what the module handed over.  Built as libbrailab_tts.so by
 * build_linux.sh into the test folder only; STUB_API builds one that claims another interface version.  MIT.
 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "brailab_tts_plugin.h"

#ifndef STUB_API
#define STUB_API BRAILAB_TTS_API
#endif
#define CHUNK 80

static int opened, tempo = 4, pitch = 0, volume = 0;

int brailab_tts_api_version(void)
{
    return STUB_API;
}

int brailab_tts_sample_rate(void)
{
    return 10000;
}

int brailab_tts_open(const char *data_dir)           /* like a voice, it wants its data file to be there */
{
    char path[1200];
    FILE *f;
    snprintf(path, sizeof path, "%s/binadata.bin", data_dir);
    f = fopen(path, "rb");
    if (!f)
        return -4;
    fclose(f);
    opened = 1;
    return 0;
}

void brailab_tts_close(void)
{
    opened = 0;
}

int brailab_tts_set(int t, int p, int v)
{
    if (!opened)
        return -1;
    tempo = t;
    pitch = p;
    volume = v;
    return 0;
}

int brailab_tts_say(const char *utf8, brailab_tts_sink sink, void *user)
{
    const unsigned char *s = (const unsigned char *)utf8;
    const struct timespec ms = {0, 1000000};
    if (!opened)
        return -1;
    for (; *s; s++) {
        int16_t pcm[CHUNK];
        const int v = *s * 64 + tempo * 4 + (pitch + 1) + (volume ? 1000 : 0);
        int i;
        for (i = 0; i < CHUNK; i++)
            pcm[i] = (int16_t)(i & 1 ? -v : v);
        nanosleep(&ms, NULL);                        /* a voice takes time: a STOP can arrive while it speaks */
        if (sink(user, pcm, CHUNK))
            return 1;
    }
    return 0;
}
