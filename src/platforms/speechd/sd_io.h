/* sd_io.h -- speech-dispatcher's module protocol on stdin and stdout (sd_io.c).  MIT. */
#ifndef SD_IO_H
#define SD_IO_H

#include <stdint.h>

#define SD_AUDIO_BLOCK 4000                          /* samples in one 705 block: STOP is looked for between blocks */

char *sd_readline(void);                             /* the next line without its end, malloc'd; NULL at end of input */
int sd_poll_stop(void);                              /* is a STOP, CANCEL or PAUSE waiting?  Reads, consumes nothing */
void sd_send_line(const char *s);
void sd_send_audio(const int16_t *pcm, int n, int rate);   /* one 705 block: 16-bit mono */

#endif
