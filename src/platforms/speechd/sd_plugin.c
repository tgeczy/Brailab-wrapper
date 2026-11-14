/*
 * sd_plugin.c -- the optional voice plug-in (brailab_tts_plugin.h): finding it, loading it, and speaking through
 * it.  The plug-in is a binary that is not built from this repository; when there is none, none of this runs.
 * Its samples come back through a callback, are turned by the volume, and go out in the module's usual blocks,
 * with a look for STOP after each.  MIT.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "brailab_tts_plugin.h"
#include "sd_io.h"
#include "sd_plugin.h"

static struct {
    void *lib;
    int (*open)(const char *);
    void (*close)(void);
    int (*set)(int, int, int);
    int (*say)(const char *, brailab_tts_sink, void *);
    int rate;
    char why[400];                                   /* a plug-in was there and was not taken: the reason */
} tts;

int sd_plugin_load(const char *file, const char *datadir)
{
    char path[1100];
    int (*version)(void), (*rate)(void), ret;
    if (file && *file)
        snprintf(path, sizeof path, "%s", file);
    else
        snprintf(path, sizeof path, "%s/libbrailab_tts.so", datadir);
    if (!strchr(path, '/') || access(path, R_OK) != 0)   /* a bare name would be searched for: never that */
        return 0;
    tts.lib = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!tts.lib) {
        snprintf(tts.why, sizeof tts.why, "%.390s", dlerror());
        return 0;
    }
    version = (int (*)(void))dlsym(tts.lib, "brailab_tts_api_version");
    rate = (int (*)(void))dlsym(tts.lib, "brailab_tts_sample_rate");
    tts.open = (int (*)(const char *))dlsym(tts.lib, "brailab_tts_open");
    tts.close = (void (*)(void))dlsym(tts.lib, "brailab_tts_close");
    tts.set = (int (*)(int, int, int))dlsym(tts.lib, "brailab_tts_set");
    tts.say = (int (*)(const char *, brailab_tts_sink, void *))dlsym(tts.lib, "brailab_tts_say");
    if (!version || !rate || !tts.open || !tts.close || !tts.set || !tts.say)
        snprintf(tts.why, sizeof tts.why, "%.300s is not a BraiLab TTS plug-in", path);
    else if (version() != BRAILAB_TTS_API)
        snprintf(tts.why, sizeof tts.why, "%.250s speaks version %d of the interface, this module version %d", path,
                 version(), BRAILAB_TTS_API);
    else if ((ret = tts.open(datadir)) != 0)
        snprintf(tts.why, sizeof tts.why, "the plug-in did not open on the data folder %.300s (%d)", datadir, ret);
    else if ((tts.rate = rate()) < 4000 || tts.rate > 96000)
        snprintf(tts.why, sizeof tts.why, "the plug-in's sample rate is %d", tts.rate);
    else
        return 1;
    dlclose(tts.lib);
    tts.lib = NULL;
    return 0;
}

/* The plug-in's samples, turned by the volume and gathered into blocks; STOP is polled after each block. */
static struct {
    int16_t pcm[SD_AUDIO_BLOCK];
    int n, stopped;
    double gain;
} out;

static int tts_sink(void *user, const int16_t *pcm, int n)
{
    int i;
    (void)user;
    for (i = 0; i < n; i++) {
        double v = pcm[i] * out.gain;
        v = v > 32767.0 ? 32767.0 : v < -32767.0 ? -32767.0 : v;
        out.pcm[out.n++] = (int16_t)(v >= 0.0 ? v + 0.5 : v - 0.5);
        if (out.n == SD_AUDIO_BLOCK) {
            sd_send_audio(out.pcm, out.n, tts.rate);
            out.n = 0;
            if ((out.stopped = sd_poll_stop()) != SD_GO)
                return 1;
        }
    }
    return 0;
}


int sd_plugin_loaded(void)
{
    return tts.lib != NULL;
}

const char *sd_plugin_why(void)
{
    return tts.why;
}

int sd_plugin_say(const char *utf8, int tempo, int pitch, double gain)
{
    out.n = out.stopped = 0;
    out.gain = gain;
    tts.set(tempo, pitch, 0);
    tts.say(utf8, tts_sink, NULL);
    if (!out.stopped && out.n)
        sd_send_audio(out.pcm, out.n, tts.rate);
    return out.stopped;
}

void sd_plugin_close(void)
{
    if (tts.lib)
        tts.close();
}
