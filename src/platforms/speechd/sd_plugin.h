/* sd_plugin.h -- the optional voice plug-in, as the module sees it (sd_plugin.c).  MIT. */
#ifndef SD_PLUGIN_H
#define SD_PLUGIN_H

/* file: the plug-in, or NULL or "" for libbrailab_tts.so in datadir, where its data files are looked for too.
 * 1 with the plug-in open; 0 without one, quietly when there simply is no such file. */
int sd_plugin_load(const char *file, const char *datadir);
int sd_plugin_loaded(void);
const char *sd_plugin_why(void);                     /* "" or why a plug-in that was there was not taken */

/* Says UTF-8 text: tempo 0..9, pitch -1..1, the samples multiplied by gain.  Audio goes out through sd_io; the
 * caller sends the lines around it.  Returns sd_poll_stop's answer: SD_GO when it was said to the end. */
int sd_plugin_say(const char *utf8, int tempo, int pitch, double gain);
void sd_plugin_close(void);

#endif
