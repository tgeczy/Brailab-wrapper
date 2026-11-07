// i86_mame.cpp -- cpu.h's 8086 on MAME's 8086 core: the CORRECTED path (CONTRACT.md 1-2, 4-7, 9).
//
// One translation unit: MAME's code (i86_mame_machine.cpp, generated) is included here, so its helpers are seen by the
// step driver and inline into it.  Build this file; never i86_mame_machine.cpp alone.
//
// The driver is ours.  It follows MAME's i8086_cpu_device::execute_run (i86.cpp, the revision in mame_i86/PINNED.txt)
// one step at a time, in the contract's phases:
//   A  execute_run's loop head for an instruction start: the saved IP; a pending NMI, else INTR if IF is set, unless
//      the interrupt shadow is active (m_no_interrupt: after STI, POP SS, MOV sreg, LOCK); an INTR acceptance pushes
//      FLAGS, clears IF and TF, reads the vector (irq_ack byte 0), pushes CS and IP, jumps.  Either leaves HALT.  A
//      halted core stops here (no trap, no shadow count), as execute_run returns.  Then the single-step trap: armed
//      by POPF/IRET with TF set, it fires (INT 1) at the second boundary after, i.e. after one instruction, and not
//      while the shadow is active.  i86_pc() is the interrupted address (where execution resumes) throughout A.
//   B  the acceptance T-states, Intel's (MAME charges none): INTR 61, NMI 50, the single-step trap 50, each with
//      4 more per push at an odd SP (I86_INTR_T and the others, i86_mame.hpp; CONTRACT.md 4).
//   C  the shadow ends: m_no_interrupt counts down (not while halted).
//   D  steps++, the saved PC (the first prefix's address), bus->boundary.
//   E  prefixes and one instruction -- a segment override is MAME's own loop turn (no interrupt between it and its
//      instruction), here run in the same step; or one HALT slot of 2 T-states (model).  An INT n / INT 3 / INTO /
//      divide error is offered to bus->intercept first (CONTRACT.md 4).
//   F  its T-states.  (Nothing is on-chip: G is empty.)
//
// A REP string instruction is one ITERATION per step: MAME loops while its slice has cycles left and otherwise puts
// IP back on the first prefix; every step here starts with none left, so each iteration ends the step, interrupts
// are sampled between iterations (the 8086 does too), and the next step re-fetches the prefixes.  The T-states are
// Intel's 9 + n per repetition (CHANGED): the first pass pays the 9 and its segment override, a pass continuing the
// same instruction only its repetition (the re-fetched prefixes are not charged again); after an interrupt the
// resumed instruction is a first pass again (model).  All prefixes survive an interruption (IP back to the first),
// not the real 8086's one.
//
// Forward progress (CONTRACT.md 4): every step costs at least 2 T-states -- every path charges an entry of Intel's
// table, the smallest being 2 -- so i86_run(budget) returns.  Before these counts an INT n (0 T in MAME), a divide
// error by AAM 0 (0 T), and a REP before a non-string instruction (0 T) could each make a step of 0 T, and an INT
// whose vector pointed at itself kept i86_run(1) looping for ever (Astra, Reply 104).
//
// Differences from MAME, each deliberate (the generated file marks those made there 'CHANGED'):
//   - HLT charges its own 2 T-states; a halted core does 2-T slots (MAME ends the slice).  A WAIT is Intel's 3 + 5n
//     (Astra, Reply 106): its entry 3 T, then a recheck of 5 T a step while TEST is inactive, IP held on it; an
//     interrupt between rechecks pushes the WAIT's address and it is entered again (3) after (MAME ends the slice).
//   - The INT seam (bus->intercept) in interrupt(), for interrupts raised by the instruction at E only.
//   - Every NMI rising edge counts (MAME ignores one at machine time 0).
//   - The `JMP $` cycle skip (i_jmp_d8's m_icount %= 12) never fires: a step starts with no cycles left.
//   - Clock counts from Intel's manual (Astra, Reply 104; Table 2-21 of the 8086 Family User's Manual, Oct 1979):
//     INT n 51, INT 3 52, INTO 53 taken, IRET 24 (MAME 0, 2, 2, 44); an intercepted one the same; the divide error's
//     entry 51 (a model: no figure in the manual); INTR 61, NMI 50, the trap 50 (MAME 0); REP string forms 9 + n
//     (MOVS 17, CMPS 22, SCAS 15, LODS 13, STOS 10); a REP before a non-string instruction 2; NOP 3, LOCK 2, ESC 2 or
//     8 + EA; 4 more for every word transfer at an odd address (MAME: none).
//   - One CPU, the 8086 (Astra, Reply 106): MAME's 8088-flavoured rows (its stack, word-port, LDS/LES and word
//     MUL/DIV rows had the 8088's 4 per word transfer built in) and its returns (matching neither CPU) are Intel's
//     8086 figures: PUSH r16 11, PUSH mem 16 + EA, PUSH sreg 10, PUSHF 10, POP r16 8, POP mem 17 + EA, POP sreg 8,
//     POPF 8, IN/OUT AX 10 (imm8) and 8 (DX), RET 8, RET n 12, RETF 18, RETF n 17, LDS/LES 16 + EA, MUL/IMUL/DIV/IDIV
//     m16 124/134/150/171 + EA; the odd-address 4 is then added once per actual word transfer.
// Known limits (MAME's, kept): MAME's undefined-flag results (e.g. OF after a rotate by CL is left alone); MUL/DIV
// are one figure, Intel's lowest, not its data-dependent ranges; a word access at FFFFh wraps linearly, not inside
// the segment.
#include "i86_mame_machine.cpp"

#include <new>

enum { I86_HALT_SLOT_T = 2 };             // CONTRACT.md 6 (model)

// ---- the driver's pieces, as members ----------------------------------------------------------------------------

int i8086_common_cpu_device::drv_accept()
{
    m_icount = 0;
    m_prev_ip = m_ip;                      // execute_run: an instruction start
    m_seg_prefix = false;
    if (m_pending_irq && (m_no_interrupt == 0)) {
        if (m_pending_irq & NMI_IRQ) {
            interrupt(I8086_NMI_INT_VECTOR);
            m_icount -= I86_NMI_T;
            m_pending_irq &= ~NMI_IRQ;
            m_halt = false;
        } else if (m_IF) {
            interrupt(-1);                 // the vector is read after FLAGS is pushed and IF cleared, as upstream
            m_icount -= I86_INTR_T;
            m_halt = false;
        }
    }
    if (m_halt)
        return -m_icount;
    if (m_fire_trap) {
        if ((m_fire_trap >= 2) && (m_no_interrupt == 0)) {
            m_fire_trap = 0;
            interrupt(1);
            m_icount -= I86_TRAP_T;
        } else
            m_fire_trap++;
    }
    return -m_icount;
}

void i8086_common_cpu_device::drv_shadow()
{
    if (!m_halt && m_no_interrupt)
        m_no_interrupt--;
}

static inline bool i86_alias(uint8_t op)
{
    return op == 0x0f || (op >= 0x60 && op <= 0x6f) || op == 0xc0 || op == 0xc1 || op == 0xc8 || op == 0xc9 || op == 0xf1;
}

int i8086_common_cpu_device::drv_instruction()
{
    m_icount = 0;
    if (m_halt)
        return I86_HALT_SLOT_T;           // a HALT slot (CONTRACT.md 6)
    uint32_t start = ((m_sregs[CS] << 4) + m_ip) & 0xfffff;
    m_rep_continue = m_rep_pending && start == m_rep_at;   // the REP the previous step left, and nothing between:
    m_rep_pending = m_rep_ran = false;    // after an acceptance this step's instruction is the handler's
    m_wait_continue = m_wait_pending && start == m_wait_at;   // likewise a WAIT left waiting: this step rechecks
    m_wait_pending = false;
    m_in_instruction = true;
    for (;;) {
        uint32_t at = ((m_sregs[CS] << 4) + m_ip) & 0xfffff;
        uint8_t op = fetch_op();
        if (i86_alias(op)) {
            m_aliased++;
            m_alias_addr = at;
            m_alias_op = op;
        }
        execute_op(op);
        if (!m_seg_prefix_next)
            break;
        m_seg_prefix = true;              // execute_run's loop head after a prefix: no dispatch, no saved IP
        m_seg_prefix_next = false;
    }
    m_in_instruction = false;
    if (m_rep_ran && m_ip == m_prev_ip) { // the REP put IP back on its first prefix: the next pass continues it
        m_rep_pending = true;
        m_rep_at = start;
    }
    return -m_icount;
}

bool i8086_common_cpu_device::drv_intercept(int int_num, int trap)
{
    if (!m_in_instruction || !m_bus->intercept || int_num < 0)
        return false;
    return m_bus->intercept(m_bus->ctx, int_num, trap ? I86_INT_EXCEPTION : I86_INT_SOFTWARE) != 0;
}

// execute_run's switch falls through to common_op for everything else (the generated execute_op)

// ---- cpu.h ------------------------------------------------------------------------------------------------------

struct i86 {
    cpu_bus bus;
    i8086_common_cpu_device *dev;
    uint64_t cycles, steps;
    uint32_t pc;
};

static inline uint32_t i86_linear(const i8086_common_cpu_device &d)
{
    return ((uint32_t)(d.m_sregs[i8086_common_cpu_device::CS] << 4) + d.m_ip) & 0xfffff;
}

extern "C" {

i86 *i86_create(const cpu_bus *bus, double clock_hz)
{
    (void)clock_hz;                       // the core counts T-states; the board turns them into time
    i86 *c = new (std::nothrow) i86();
    if (!c)
        return nullptr;
    c->bus = *bus;
    c->dev = new (std::nothrow) i8086_common_cpu_device(&c->bus);
    if (!c->dev) {
        delete c;
        return nullptr;
    }
    i86_reset(c);                         // the general registers stay as the constructor zeroed them
    return c;
}

void i86_destroy(i86 *c)
{
    if (!c)
        return;
    delete c->dev;
    delete c;
}

// Reset (CONTRACT.md 9): MAME's device_reset -- CS:IP = FFFF:0000, DS = ES = SS = 0, the flags cleared (IF off), a
// pending NMI edge dropped, the shadow and the trap cleared, HALT left -- with the lines kept as they are: a held
// INTR is sampled again at the next A.
void i86_reset(i86 *c)
{
    c->dev->device_reset();
    c->dev->m_in_instruction = false;
    c->dev->m_rep_pending = false;
    c->dev->m_wait_pending = false;
    c->cycles = c->steps = 0;
    c->pc = i86_linear(*c->dev);
}

int i86_step(i86 *c)
{
    i8086_common_cpu_device &d = *c->dev;
    c->pc = i86_linear(d);                // A's callbacks see where execution resumes
    int acc = d.drv_accept();             // A
    c->cycles += (uint64_t)acc;           // B
    d.drv_shadow();                       // C

    c->steps++;                           // D
    c->pc = i86_linear(d);
    if (c->bus.boundary)
        c->bus.boundary(c->bus.ctx, c->pc);

    int ins = d.drv_instruction();        // E
    c->cycles += (uint64_t)ins;           // F
    return acc + ins;
}

// Returns: every step costs at least 2 T-states (forward progress, CONTRACT.md 4; test_i86_contract.c's
// forward_progress and step_cost_floor)
uint64_t i86_run(i86 *c, uint64_t budget)
{
    uint64_t done = 0;
    while (done < budget)
        done += (uint64_t)i86_step(c);
    return done;
}

void i86_set_irq(i86 *c, int line, int asserted)
{
    int state = asserted ? ASSERT_LINE : CLEAR_LINE;
    if (line == I86_INTR)
        c->dev->execute_set_input(INPUT_LINE_INT0, state);
    else if (line == I86_NMI)
        c->dev->execute_set_input(INPUT_LINE_NMI, state);
    else if (line == I86_TEST)
        c->dev->execute_set_input(INPUT_LINE_TEST, state);
}

uint64_t i86_cycles(const i86 *c) { return c->cycles; }
uint64_t i86_steps(const i86 *c) { return c->steps; }
uint32_t i86_pc(const i86 *c) { return c->pc; }
uint32_t i86_next_pc(const i86 *c) { return i86_linear(*c->dev); }

void i86_regs_get(const i86 *c, i86_regs *out)
{
    typedef i8086_common_cpu_device D;
    const D &d = *c->dev;
    out->ax = d.m_regs.w[D::AX]; out->cx = d.m_regs.w[D::CX]; out->dx = d.m_regs.w[D::DX]; out->bx = d.m_regs.w[D::BX];
    out->sp = d.m_regs.w[D::SP]; out->bp = d.m_regs.w[D::BP]; out->si = d.m_regs.w[D::SI]; out->di = d.m_regs.w[D::DI];
    out->es = d.m_sregs[D::ES]; out->cs = d.m_sregs[D::CS]; out->ss = d.m_sregs[D::SS]; out->ds = d.m_sregs[D::DS];
    out->ip = d.m_ip;
    out->flags = d.CompressFlags();
    out->halted = d.m_halt ? 1 : 0;
}

void i86_regs_set(i86 *c, const i86_regs *in)
{
    typedef i8086_common_cpu_device D;
    D &d = *c->dev;
    d.m_regs.w[D::AX] = in->ax; d.m_regs.w[D::CX] = in->cx; d.m_regs.w[D::DX] = in->dx; d.m_regs.w[D::BX] = in->bx;
    d.m_regs.w[D::SP] = in->sp; d.m_regs.w[D::BP] = in->bp; d.m_regs.w[D::SI] = in->si; d.m_regs.w[D::DI] = in->di;
    d.m_sregs[D::ES] = in->es; d.m_sregs[D::CS] = in->cs; d.m_sregs[D::SS] = in->ss; d.m_sregs[D::DS] = in->ds;
    d.m_ip = in->ip;
    if (!d.m_in_instruction)
        d.m_prev_ip = in->ip;
    d.ExpandFlags((uint16_t)(in->flags | 0xf000));   // the 8086's bits 12-15 are 1, as POPF sets them
    if (!d.m_in_instruction)
        c->pc = i86_linear(d);
}

uint64_t i86_aliased(const i86 *c, uint32_t *last_addr, uint8_t *last_op)
{
    if (last_addr)
        *last_addr = c->dev->m_alias_addr;
    if (last_op)
        *last_op = c->dev->m_alias_op;
    return c->dev->m_aliased;
}

}  // extern "C"
