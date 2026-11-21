/* sd_text.h -- a message's text made ready for a voice (sd_text.c).  MIT. */
#ifndef SD_TEXT_H
#define SD_TEXT_H

void sd_strip_ssml(char *s);                         /* in place: tags dropped, XML's five entities decoded */
char *sd_key_text(const char *key);                  /* SSIP KEY "control_alt_delete" in Hungarian words, malloc'd */
char *sd_char_text(const char *ch);                  /* SSIP CHAR: "space" as a word, else the character; malloc'd */
int sd_to_cwi2(char *s);                             /* in place: UTF-8 to CWI-2; returns the length in bytes */

#endif
