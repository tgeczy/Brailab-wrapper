/*
 * sd_io.c -- speech-dispatcher's module protocol on stdin and stdout: lines in, lines and audio out.
 *
 * stdin is one raw buffer for both the line reader and the STOP poll (never stdio on stdin: mixing the two loses
 * commands).  Audio goes out as 705 blocks, HDLC-escaped, played and flushed by the server, as speech-dispatcher's
 * module_process.c has it.  MIT.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <unistd.h>

#include "sd_io.h"

static char *rbuf;
static size_t rlen, rcap;
static int r_eof;

static void rappend(const char *p, size_t n)
{
    if (rlen + n + 1 > rcap) {
        size_t cap = rcap ? rcap : 8192;
        while (cap < rlen + n + 1)
            cap *= 2;
        rbuf = (char *)realloc(rbuf, cap);
        if (!rbuf)
            exit(1);
        rcap = cap;
    }
    memcpy(rbuf + rlen, p, n);
    rlen += n;
    rbuf[rlen] = 0;
}

/* The next line, without its \r\n, malloc'd; NULL at EOF. */
char *sd_readline(void)
{
    for (;;) {
        char *nl = rbuf ? (char *)memchr(rbuf, '\n', rlen) : NULL;
        if (nl) {
            size_t n = (size_t)(nl - rbuf);
            char *line = (char *)malloc(n + 1);
            memcpy(line, rbuf, n);
            line[n] = 0;
            if (n && line[n - 1] == '\r')
                line[n - 1] = 0;
            memmove(rbuf, nl + 1, rlen - n - 1);
            rlen -= n + 1;
            rbuf[rlen] = 0;
            return line;
        }
        if (r_eof)
            return NULL;
        {
            char buf[4096];
            ssize_t k = read(STDIN_FILENO, buf, sizeof buf);
            if (k <= 0) {
                r_eof = 1;
                continue;
            }
            rappend(buf, (size_t)k);
        }
    }
}

/* STOP (or CANCEL or PAUSE) waiting on stdin?  Reads what is there, and leaves it for sd_readline. */
int sd_poll_stop(void)
{
    fd_set f;
    struct timeval tv = {0, 0};
    FD_ZERO(&f);
    FD_SET(STDIN_FILENO, &f);
    if (select(STDIN_FILENO + 1, &f, NULL, NULL, &tv) > 0) {
        char buf[4096];
        ssize_t k = read(STDIN_FILENO, buf, sizeof buf);
        if (k <= 0) {
            r_eof = 1;
            return 1;
        }
        rappend(buf, (size_t)k);
    }
    return rbuf && (strstr(rbuf, "STOP") || strstr(rbuf, "CANCEL") || strstr(rbuf, "PAUSE"));
}

void sd_send_line(const char *s)
{
    fputs(s, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

/* 705: 16-bit mono little-endian, the payload HDLC-escaped (0x7D and '\n' become 0x7D, byte ^ 0x20) */
void sd_send_audio(const int16_t *pcm, int n, int rate)
{
    const unsigned char *p = (const unsigned char *)pcm, *end = p + (size_t)n * 2;
    printf("705-bits=16\n705-num_channels=1\n705-sample_rate=%d\n705-num_samples=%d\n705-big_endian=0\n705-AUDIO",
           rate, n);
    fputc(0, stdout);
    for (; p < end; p++) {
        if (*p == 0x7D || *p == '\n') {
            fputc(0x7D, stdout);
            fputc(*p ^ 0x20, stdout);
        } else {
            fputc(*p, stdout);
        }
    }
    fputs("\n705 AUDIO\n", stdout);
    fflush(stdout);
}
