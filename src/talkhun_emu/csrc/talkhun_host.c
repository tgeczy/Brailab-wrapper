/* talkhun_host.c -- see talkhun_host.h; the program's interfaces are described in
 * ../talkhun.py.  MIT.
 *
 * DOS is a handful of INT 21h services.  The adapter is read off the code: boundary
 * sees each entry to the byte shifter, the preamble and the postamble.
 */
#include <stdlib.h>
#include <string.h>

#include "cpu.h"
#include "talkhun_host.h"

#define MEM_SIZE 0x100000
#define PROG_SEG 0x0800u
#define SENTINEL_SEG 0x9000u
#define SENTINEL (SENTINEL_SEG * 16u)
#define STACK_TOP 0xFFFEu
#define MAX_STEPS 20000000u

#define LPT_BASE 0x378
#define BIOS_LPT1 0x408
#define BIOS_TICK 0x46C
#define COM4 3
#define STATUS_BUSY 0x10
#define STATUS_READY 0x00
#define FLAG_CF 0x0001
#define FLAG_ZF 0x0040

/* code addresses in the 1991 image */
#define SEND_BYTE 0x1DF8u
#define PREAMBLE 0x1DF0u
#define POSTAMBLE 0x1E1Cu
#define CTRL_WRITE 0x1D2Cu

#define EV_PRE 0x100
#define EV_POST 0x101

struct talkhun {
    uint8_t *mem;
    i86 *cpu;
    int busy;
    int tsr;
    int stop;
    int hooked;
    uint16_t int14_seg, int14_off;
    uint32_t steps;
    uint16_t *events;
    int nevents, cap_events;
    talkhun_item *items;
    int cap_items;
};

static uint8_t rd(void *ctx, uint32_t a) { return ((talkhun *)ctx)->mem[a & 0xFFFFF]; }
static void wr(void *ctx, uint32_t a, uint8_t v) { ((talkhun *)ctx)->mem[a & 0xFFFFF] = v; }

static uint8_t in(void *ctx, uint16_t port)
{
    talkhun *t = (talkhun *)ctx;
    if (port != LPT_BASE + 1)
        return 0xFF;
    if (t->busy) {
        t->busy = 0;
        return STATUS_BUSY;
    }
    return STATUS_READY;
}

static void out(void *ctx, uint16_t port, uint8_t v)
{
    (void)ctx;
    (void)port;
    (void)v;
}

static void event(talkhun *t, int value)
{
    if (t->nevents == t->cap_events) {
        int cap = t->cap_events ? t->cap_events * 2 : 4096;
        uint16_t *e = (uint16_t *)realloc(t->events, (size_t)cap * sizeof *e);
        if (!e)
            return;
        t->events = e;
        t->cap_events = cap;
    }
    t->events[t->nevents++] = (uint16_t)value;
}

static void boundary(void *ctx, uint32_t pc)
{
    talkhun *t = (talkhun *)ctx;
    /* The ready poll times out against the BIOS tick; if that never advances, a
     * poll that is waiting can never give up. */
    if ((++t->steps & 2047) == 0) {
        uint32_t tick = t->steps >> 11;
        memcpy(t->mem + BIOS_TICK, &tick, 4);
    }
    if (pc < PROG_SEG * 16u + CTRL_WRITE || pc > PROG_SEG * 16u + POSTAMBLE)
        return;
    switch (pc - PROG_SEG * 16u) {
    case CTRL_WRITE:
        t->busy = 1;            /* the adapter looks busy until addressed */
        break;
    case SEND_BYTE: {
        i86_regs r;
        i86_regs_get(t->cpu, &r);
        event(t, r.ax & 0xFF);
        break;
    }
    case PREAMBLE:
        event(t, EV_PRE);
        break;
    case POSTAMBLE:
        event(t, EV_POST);
        break;
    }
}

/* DOS and the BIOS.  Anything else is a no-op, as Unicorn's hook made it. */
static int intercept(void *ctx, int vector, int kind)
{
    talkhun *t = (talkhun *)ctx;
    i86_regs r;
    int ah, al;
    (void)kind;
    i86_regs_get(t->cpu, &r);
    ah = r.ax >> 8;
    al = r.ax & 0xFF;
    if (vector == 0x21) {
        switch (ah) {
        case 0x35:              /* get interrupt vector */
            memcpy(&r.bx, t->mem + al * 4, 2);
            memcpy(&r.es, t->mem + al * 4 + 2, 2);
            break;
        case 0x25:              /* set interrupt vector */
            memcpy(t->mem + al * 4, &r.dx, 2);
            memcpy(t->mem + al * 4 + 2, &r.ds, 2);
            if (al == 0x14) {
                t->int14_seg = r.ds;
                t->int14_off = r.dx;
                t->hooked = 1;
            }
            break;
        case 0x31:              /* TSR: installed */
            t->tsr = 1;
            t->stop = 1;
            return 1;
        case 0x4C:
            t->stop = 1;
            return 1;
        }
        r.flags &= (uint16_t)~FLAG_CF;
        i86_regs_set(t->cpu, &r);
    } else if (vector == 0x20) {
        t->stop = 1;
    } else if (vector == 0x16) {    /* keyboard: never a key */
        if (ah == 0x01 || ah == 0x11)
            r.flags |= FLAG_ZF;
        r.ax = 0;
        i86_regs_set(t->cpu, &r);
    }
    return 1;
}

static void push(talkhun *t, i86_regs *r, uint16_t value)
{
    r->sp = (uint16_t)(r->sp - 2);
    memcpy(t->mem + r->ss * 16u + r->sp, &value, 2);
}

/* Run until the sentinel address or a stop; 0 if it got there. */
static int run(talkhun *t, uint32_t until)
{
    uint32_t n;
    t->stop = 0;
    for (n = 0; n < MAX_STEPS; n++) {
        if (until && i86_next_pc(t->cpu) == until)
            return 0;
        i86_step(t->cpu);
        if (t->stop)
            return until ? -1 : 0;
    }
    return -1;
}

static int call_int14(talkhun *t, int ah, int al)
{
    i86_regs r;
    i86_regs_get(t->cpu, &r);
    r.ss = PROG_SEG;
    r.sp = STACK_TOP;
    r.ax = (uint16_t)(((ah & 0xFF) << 8) | (al & 0xFF));
    r.dx = COM4;
    r.cs = t->int14_seg;
    r.ip = t->int14_off;
    /* the handler ends in iret, which pops IP, CS and FLAGS */
    push(t, &r, r.flags);
    push(t, &r, SENTINEL_SEG);
    push(t, &r, 0);
    i86_regs_set(t->cpu, &r);
    return run(t, SENTINEL);
}

talkhun *talkhun_create(const uint8_t *com, int len)
{
    talkhun *t = (talkhun *)calloc(1, sizeof *t);
    cpu_bus bus;
    i86_regs r;
    uint16_t lpt = LPT_BASE;

    if (!t)
        return NULL;
    t->mem = (uint8_t *)calloc(1, MEM_SIZE);
    if (!t->mem || len < 1 || PROG_SEG * 16u + 0x100u + (uint32_t)len > MEM_SIZE) {
        talkhun_destroy(t);
        return NULL;
    }
    memset(&bus, 0, sizeof bus);
    bus.ctx = t;
    bus.read = rd;
    bus.write = wr;
    bus.in = in;
    bus.out = out;
    bus.boundary = boundary;
    bus.intercept = intercept;
    t->cpu = i86_create(&bus, 0.0);
    if (!t->cpu) {
        talkhun_destroy(t);
        return NULL;
    }

    memcpy(t->mem + BIOS_LPT1, &lpt, 2);
    /* a minimal PSP: int 20h at :0000, empty command tail at :0080 */
    t->mem[PROG_SEG * 16u] = 0xCD;
    t->mem[PROG_SEG * 16u + 1] = 0x20;
    memcpy(t->mem + PROG_SEG * 16u + 0x100, com, (size_t)len);

    i86_regs_get(t->cpu, &r);
    r.ax = r.bx = r.cx = r.dx = r.si = r.di = r.bp = 0;
    r.cs = r.ds = r.es = r.ss = PROG_SEG;
    r.sp = STACK_TOP;
    r.ip = 0x100;
    push(t, &r, 0);             /* DOS's .COM return word */
    i86_regs_set(t->cpu, &r);
    if (run(t, 0) || !t->tsr || !t->hooked || talkhun_reset(t)) {
        talkhun_destroy(t);
        return NULL;
    }
    return t;
}

void talkhun_destroy(talkhun *t)
{
    if (!t)
        return;
    if (t->cpu)
        i86_destroy(t->cpu);
    free(t->mem);
    free(t->events);
    free(t->items);
    free(t);
}

int talkhun_reset(talkhun *t)
{
    return call_int14(t, 0, 0);
}

int talkhun_feed(talkhun *t, const uint8_t *text, int len)
{
    int i;
    for (i = 0; i < len; i++)
        if (call_int14(t, 1, text[i]))
            return -1;
    return 0;
}

static int is_delimiter(int c)
{
    return c != 0 && strchr(".,;:?!", c) != NULL;
}

int talkhun_capture(talkhun *t, const uint8_t *text, int len, const talkhun_item **items)
{
    int i, start = -1, count = 0, singles = 0;

    *items = NULL;
    if (len == 0)
        return 0;
    t->nevents = 0;
    if (talkhun_feed(t, text, len))
        return -1;
    if (!is_delimiter(text[len - 1])) {
        static const uint8_t stop = '.';
        if (talkhun_feed(t, &stop, 1))
            return -1;
    }
    if (t->cap_items < t->nevents / 3 + 1) {
        talkhun_item *p = (talkhun_item *)realloc(t->items, (size_t)(t->nevents / 3 + 1) * sizeof *p);
        if (!p)
            return -1;
        t->items = p;
        t->cap_items = t->nevents / 3 + 1;
    }
    /* preamble, a 0x20 marker, the payload, postamble */
    for (i = 0; i < t->nevents; i++) {
        int e = t->events[i], n;
        if (e == EV_PRE) {
            start = i + 1;
            continue;
        }
        if (e != EV_POST)
            continue;
        if (start < 0)
            continue;
        n = i - start - 1;
        if (n >= 1 && t->events[start] == 0x20 && count < t->cap_items) {
            talkhun_item *it = &t->items[count];
            int b;
            for (b = 0; b < n && b < 5; b++)
                it->data[b] = (uint8_t)t->events[start + 1 + b];
            if (n == 5) {
                it->kind = TALKHUN_FRAME;
                count++;
            } else if (n == 2) {
                it->kind = TALKHUN_CTRL;
                count++;
            } else if (n == 1) {
                /* a start sequence sends the settings nibble, then the pitch */
                if (singles & 1) {
                    it->kind = TALKHUN_PITCH;
                    count++;
                }
                singles++;
            }
        }
        start = -1;
    }
    *items = t->items;
    return count;
}
