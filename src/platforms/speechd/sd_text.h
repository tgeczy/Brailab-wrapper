/* sd_text.h -- a message's text made ready for a voice (sd_text.c).  MIT. */
#ifndef SD_TEXT_H
#define SD_TEXT_H

void sd_strip_ssml(char *s);                         /* in place: tags dropped, XML's five entities decoded */
int sd_to_cwi2(char *s);                             /* in place: UTF-8 to CWI-2; returns the length in bytes */

#endif
