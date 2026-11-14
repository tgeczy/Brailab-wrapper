/* sd_io.h -- speech-dispatcher's module protocol on stdin and stdout (sd_io.c).  MIT. */
#ifndef SD_IO_H
#define SD_IO_H

#include <stdint.h>

#define SD_AUDIO_BLOCK 4000                          /* samples in one 705 block: STOP is looked for between blocks */

char *sd_readline(void);                             /* the next line without its end, malloc'd; NULL at end of input */
/* What waits for the message being spoken: nothing, a STOP (or CANCEL, or the end of input), or a PAUSE alone.
 * Reads what is there and consumes nothing. */
enum { SD_GO = 0, SD_STOPPED, SD_PAUSED };
int sd_poll_stop(void);
void sd_send_line(const char *s);
void sd_send_end(int stopped);                      /* 702 END, 703 STOP or 704 PAUSE, from sd_poll_stop's answer */
void sd_send_audio(const int16_t *pcm, int n, int rate);   /* one 705 block: 16-bit mono */

#endif
