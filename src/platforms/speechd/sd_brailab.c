/*
 * sd_brailab -- a speech-dispatcher output module: the BraiLab PC's voice, as in the NVDA add-on, in one process
 * with no Python.  The 1991 TALKHUN0.COM runs on MAME's 8086 and drives a model of the Philips PCF8200
 * (src/talkhun_emu/csrc/brailab_voice.c).  This file is the module: its settings, its voices and its command loop.
 * The protocol's plumbing is sd_io.c, the text's preparation sd_text.c, the optional third voice sd_plugin.c.
 *
 * The protocol and its audio (705 blocks, HDLC-escaped, played and flushed by the server) follow speech-dispatcher's
 * module_process.c, as ssi263-speech's sd_ssi263 does, which this is modelled on; every reply line is the one
 * speech-dispatcher's own modules give, which has not changed from 0.11.0 to 0.12.1.  0.11 is the oldest server
 * this can speak on: it is the first that plays a module's audio.  Synthesis is synchronous: stdin
 * is polled for STOP and PAUSE between blocks (a STOP is answered 703, a PAUSE 704, which lets the server speak the
 * message again on RESUME).  Two voices: "BraiLab PC" and "BraiLab PC furcsa" (the weird voice), Hungarian.
 * Rate, pitch and volume come from SSIP, mapped as the NVDA driver maps its sliders.
 *
 * A third voice, "BraiLab TTS", is offered when an optional binary plug-in is in the data folder with its two data
 * files (brailab_tts_plugin.h; the plug-in is not built from this repository).  Either part may be missing: the
 * module loads with whichever voices it finds, and fails only with none.
 *
 * Config (argv[1], speech-dispatcher's module config; then this user's own file, whose keys win:
 * $XDG_CONFIG_HOME/brailab/sd_brailab.conf, else ~/.config/brailab/sd_brailab.conf; every key optional):
 *   BrailabDataDir "/usr/local/share/brailab"   where TALKHUN0.COM is
 *   BrailabIntonation 1                         0: each clause held at its start pitch
 *   BrailabTtsPlugin "/path/to/the/plug-in"     default: libbrailab_tts.so in the data folder
 * BRAILAB_DATADIR overrides the data folder.  TALKHUN0.COM is Arató András's program and not part of this one.
 * MIT.
 */
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "brailab_voice.h"
#include "sd_io.h"
#include "sd_plugin.h"
#include "sd_text.h"

#define RATE 10000

/* ---- config ---------------------------------------------------------------------------------------------------- */
static char datadir[1024];
static char tts_plugin[1024];
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
        else if (!strcmp(key, "BrailabTtsPlugin"))
            snprintf(tts_plugin, sizeof tts_plugin, "%s", val);
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
enum { PC, FURCSA, TTS, NVOICES };
static const char *VOICES[NVOICES] = {"BraiLab PC", "BraiLab PC furcsa", "BraiLab TTS"};
static brailab_voice *voice;
static int which = PC;
static int ssip_rate = 0, ssip_pitch = 0, ssip_volume = 100;

static int have(int v)
{
    return v == TTS ? sd_plugin_loaded() : voice != NULL;
}

static int to100(int ssip)                           /* SSIP -100..100 to the NVDA driver's 0..100 (0 is 50) */
{
    int v = (ssip + 100) / 2;
    return v < 0 ? 0 : v > 100 ? 100 : v;
}

/* The NVDA driver's sliders for this voice: ten tempos (SSIP 0 is the voice's own, 4) and three pitches.  The voice
 * is left at its own level and the samples are turned by the gain the other two voices get. */
static void speak_tts(char *text)
{
    const int rate = to100(ssip_rate), pitch = to100(ssip_pitch);
    int stopped;

    sd_strip_ssml(text);
    sd_send_line("200 OK SPEAKING");
    sd_send_line("701 BEGIN");
    if ((stopped = sd_poll_stop()) != SD_GO) {          /* already stopped (key repeat): nothing to say */
        sd_send_end(stopped);
        return;
    }
    stopped = sd_plugin_say(text, (rate * 9 + 49) / 100, pitch <= 25 ? -1 : pitch >= 75 ? 1 : 0,
                            0.25 + to100(ssip_volume) / 100.0);
    sd_send_end(stopped);
}

static void speak(char *text)
{
    static int16_t pcm[BRAILAB_VOICE_BLOCK];
    const double rate = to100(ssip_rate), pitch = to100(ssip_pitch), volume = to100(ssip_volume);
    const int furcsa = which == FURCSA;
    int len, n, stopped = 0;

    if (which == TTS) {
        speak_tts(text);
        return;
    }
    sd_strip_ssml(text);
    len = sd_to_cwi2(text);
    if ((stopped = sd_poll_stop()) != SD_GO) {          /* already stopped (key repeat): nothing to say */
        sd_send_line("200 OK SPEAKING");
        sd_send_line("701 BEGIN");
        sd_send_end(stopped);
        return;
    }
    sd_send_line("200 OK SPEAKING");
    sd_send_line("701 BEGIN");
    /* the NVDA driver's _timeScale, _pitchFactor and gain */
    if (brailab_voice_begin(voice, (const uint8_t *)text, len, pow(2.0, (pitch - 50.0) / 100.0),
                            0.9 - 0.55 * (rate / 100.0), furcsa, intonation, 0.25 + volume / 100.0) == 0) {
        while ((n = brailab_voice_read(voice, pcm, BRAILAB_VOICE_BLOCK)) > 0) {
            sd_send_audio(pcm, n, RATE);
            if ((stopped = sd_poll_stop()) != SD_GO)
                break;
        }
    }
    sd_send_end(stopped);
}

static char *read_text(void)
{
    char *text = (char *)calloc(1, 1), *line;
    size_t n = 0;
    while ((line = sd_readline()) != NULL) {
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
        int v;
        for (v = 0; v < NVOICES; v++)
            if (have(v) && !strcmp(val, VOICES[v]))
                which = v;
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
    cmd = sd_readline();
    if (!cmd || strcmp(cmd, "INIT"))
        return 1;
    free(cmd);
    image = load_talkhun(&len);
    voice = image ? brailab_voice_create(image, len) : NULL;
    sd_plugin_load(tts_plugin, datadir);
    if (!voice && !sd_plugin_loaded()) {
        char msg[1200];
        snprintf(msg, sizeof msg, image ? "399-TALKHUN0.COM in %s did not install"
                                        : "399-no TALKHUN0.COM in the data folder %s", datadir);
        free(image);
        sd_send_line(msg);
        if (*sd_plugin_why()) {
            snprintf(msg, sizeof msg, "399-BraiLab TTS: %s", sd_plugin_why());
            sd_send_line(msg);
        }
        sd_send_line("399 ERR CANT INIT MODULE");
        return 1;
    }
    free(image);
    if (voice)
        sd_send_line("299-the BraiLab PC: TALKHUN0 on an emulated 8086, through a model of the PCF8200");
    else
        which = TTS;
    if (sd_plugin_loaded()) {
        sd_send_line("299-BraiLab TTS: the optional voice plug-in is loaded");
    } else if (*sd_plugin_why()) {
        char msg[500];
        snprintf(msg, sizeof msg, "299-BraiLab TTS is not offered: %s", sd_plugin_why());
        sd_send_line(msg);
    }
    sd_send_line("299 OK LOADED SUCCESSFULLY");
    while ((cmd = sd_readline()) != NULL) {
        if (!strcmp(cmd, "SPEAK") || !strcmp(cmd, "CHAR") || !strcmp(cmd, "KEY") || !strcmp(cmd, "SOUND_ICON")) {
            int is_key = !strcmp(cmd, "KEY"), icon = !strcmp(cmd, "SOUND_ICON");
            char *text;
            sd_send_line("202 OK RECEIVING MESSAGE");
            text = read_text();
            if (is_key) {
                char *c;
                for (c = text; *c; c++)
                    if (*c == '_')
                        *c = ' ';
            }
            if (icon || !*text) {                    /* no sound icons: an empty message still completes */
                sd_send_line("200 OK SPEAKING");
                sd_send_line("701 BEGIN");
                sd_send_line("702 END");
            } else {
                speak(text);
            }
            free(text);
        } else if (!strcmp(cmd, "STOP") || !strcmp(cmd, "CANCEL") || !strcmp(cmd, "PAUSE")) {
            /* only between messages here (during one, speak() catches it): nothing is playing */
        } else if (!strcmp(cmd, "SET")) {
            char *line;
            sd_send_line("203 OK RECEIVING SETTINGS");
            while ((line = sd_readline()) != NULL) {
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
            sd_send_line("203 OK SETTINGS RECEIVED");
        } else if (!strncmp(cmd, "DEBUG", 5)) {
            /* "DEBUG ON <file>" or "DEBUG OFF", on one line, answered as speech-dispatcher's own modules answer.
             * This module keeps no log of its own, so there is nothing to switch. */
            char word[16] = "", on[8] = "";
            sscanf(cmd, "%15s %7s", word, on);
            if (!strcmp(word, "DEBUG") && !strcmp(on, "ON"))
                sd_send_line("200 OK DEBUGGING ON");
            else if (!strcmp(word, "DEBUG") && !strcmp(on, "OFF"))
                sd_send_line("200 OK DEBUGGING OFF");
            else
                sd_send_line("302 ERROR BAD SYNTAX");
        } else if (!strcmp(cmd, "AUDIO") || !strcmp(cmd, "LOGLEVEL")) {
            /* The server offers to play the audio itself (audio_output_method=server), which is the only way
             * this module speaks; and its log level, which this module has no use for. */
            const int audio = !strcmp(cmd, "AUDIO");
            char *line;
            sd_send_line(audio ? "207 OK RECEIVING AUDIO SETTINGS" : "207 OK RECEIVING LOGLEVEL SETTINGS");
            while ((line = sd_readline()) != NULL) {
                int end = !strcmp(line, ".");
                free(line);
                if (end)
                    break;
            }
            sd_send_line(audio ? "203 OK AUDIO INITIALIZED" : "203 OK LOGLEVEL SET");
        } else if (!strncmp(cmd, "LIST VOICES", 11) && (!cmd[11] || cmd[11] == ' ')) {
            /* "LIST VOICES", and from speech-dispatcher 0.12 "LIST VOICES <language> [<variant>]".  Every voice here
             * is Hungarian: a request for hu (hu-HU, HU_hu) gets them all, one for another language none.  The
             * variant is not looked at. */
            char lang[16] = "";
            int v, any = 0;
            sscanf(cmd + 11, "%15s", lang);
            if (!*lang || ((lang[0] | 32) == 'h' && (lang[1] | 32) == 'u' && (!lang[2] || lang[2] == '-' || lang[2] == '_')))
                for (v = 0; v < NVOICES; v++)
                    if (have(v)) {
                        printf("200-%s\thu\tMALE%d\n", VOICES[v], v + 1);
                        any = 1;
                    }
            sd_send_line(any ? "200 OK VOICE LIST SENT" : "304 CANT LIST VOICES");
        } else if (!strcmp(cmd, "QUIT")) {
            sd_send_line("210 OK QUIT");             /* the server waits for it */
            free(cmd);
            break;
        } else {
            sd_send_line("300 ERR UNKNOWN COMMAND");
        }
        free(cmd);
    }
    if (voice)
        brailab_voice_destroy(voice);
    sd_plugin_close();
    return 0;
}
