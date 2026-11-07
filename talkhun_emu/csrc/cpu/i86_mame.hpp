// i86_mame.hpp -- the class MAME's 8086 code compiles against, without the MAME framework.
//
// MAME's machine code (i86_mame_machine.cpp, generated from i86.cpp and i86inline.h by extract_i86_machine.py) is
// written as members of `i8086_common_cpu_device` (and a few of `i8086_cpu_device`, its 8086/8088 subclass).  This
// header declares ONE class with the member names that code uses, taken from MAME's i86.h at the revision in
// mame_i86/PINNED.txt (`i8086_cpu_device` is an alias of it: no virtual functions, only the 8086 is built), and
// replaces what the framework provided:
//
//   MAME                                   here
//   address spaces (program, opcodes,      the cpu_bus callbacks with their ctx, one 20-bit memory: read, write,
//   stack, code, extra), m_or8             fetch (NULL: read).  A word is two byte accesses, low byte first, at
//                                          consecutive 20-bit addresses (the 8088's bus; upstream's unaligned read)
//   m_io                                   cpu_bus in/out, bytes: a word port access is two, port then port + 1
//   write_port_byte_al                     an OUT of AL to the port (upstream: a masked word write on the 16-bit bus)
//   standard_irq_callback                  cpu_bus.irq_ack(ctx, I86_INTR, 0): the vector byte of the INTA cycle;
//                                          -1 or none = FFh
//   access_to_be_redone (I/O wait retry)   false: our buses never wait-state a cycle
//   m_lock_handler, m_out_if_func,         unconnected outputs
//   m_esc_opcode_handler/data_handler      no coprocessor: ESC reads its operand (if any) and does nothing
//   total_cycles() (NMI edge at time 0)    never 0: every rising NMI edge counts, from reset on
//   logerror, debugger hooks               discarded
//   the constructor                        ours: the power-on values of upstream's initialiser lists, the timing
//                                          tables copied as i8086_cpu_device's constructor does, then init_tables()
//
// i86_mame.cpp holds our step driver and the cpu.h API.  Licence: this header is ours (MIT) but restates MAME's
// declarations (BSD-3-Clause, copyright-holders: Carl; see mame_i86/LICENSE-BSD-3-Clause.txt).
#ifndef SSI263_I86_MAME_HPP
#define SSI263_I86_MAME_HPP

#include <cstdint>
#include <cstring>

#include "cpu.h"

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "the byte-register layout below is a little-endian host's, as MAME's NATIVE_ENDIAN_VALUE_LE_BE picks on one"
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;

enum { CLEAR_LINE = 0, ASSERT_LINE = 1 };
enum { INPUT_LINE_IRQ0 = 0, INPUT_LINE_NMI = 32 };     // outside the 8086's own lines, as in MAME
#define INPUT_LINE_INT0 INPUT_LINE_IRQ0
#define INPUT_LINE_TEST 20                               // i86.h

struct i86_unconnected {                                  // m_lock_handler: an output nobody listens to
    void operator()(int) const {}
};
struct i86_no_esc {                                       // m_esc_opcode_handler, m_esc_data_handler
    void operator()(u32) const {}
};

// ---- the class --------------------------------------------------------------------------------------------------
// Everything is public: the step driver (i86_mame.cpp) is part of the core and reads the registers directly.
class i8086_common_cpu_device {
public:
    explicit i8086_common_cpu_device(const cpu_bus *bus) : m_bus(bus)
    {
        // upstream's initialiser lists (i8086_common_cpu_device, i8086_cpu_device)
        m_ip = 0;
        m_TF = 0;
        m_int_vector = 0;
        m_pending_irq = 0;
        m_nmi_state = 0;
        m_test_state = 1;
        m_pc = 0;
        m_lock = false;
        // i8086_cpu_device's constructor
        memcpy(m_timing, m_i8086_timing, sizeof(m_i8086_timing));
        memcpy(m_ea_timing, m_i8086_ea_timing, sizeof(m_i8086_ea_timing));
        m_icount = 0;
        m_prev_ip = 0;
        m_no_interrupt = 0;
        m_fire_trap = 0;
        m_halt = false;
        m_in_instruction = false;
        m_aliased = 0;
        m_alias_addr = 0;
        m_alias_op = 0;
        m_rep_ran = m_rep_continue = m_rep_pending = false;
        m_rep_at = 0;
        m_wait_continue = m_wait_pending = false;
        m_wait_at = 0;
        init_tables();            // the constructor's body (generated file)
    }

    // ---- our step driver's pieces (i86_mame.cpp) ----
    const cpu_bus *m_bus;
    bool m_in_instruction;                // phase E: an interrupt raised now is the instruction's (the INT seam)
    uint64_t m_aliased;                   // opcodes whose meaning differs on the 80186 and later (i86_aliased)
    uint32_t m_alias_addr;
    u8 m_alias_op;
    int drv_accept();                     // phase A; returns the acceptance T-states
    void drv_shadow();                    // phase C
    int drv_instruction();                // phase E: prefixes and one instruction, or a HALT slot
    bool drv_intercept(int int_num, int trap);
    void execute_op(uint8_t op);          // the generated file: execute_run's own opcodes, then common_op
    void init_tables();                   // the generated file: the constructor's body

    // ---- clock counts from Intel's manual (Astra, Replies 104 and 106; CONTRACT.md 4).  The 8086 Family User's
    // Manual, Oct 1979, Table 2-21, as printed page / PDF page.  Upstream charges none of these.
    enum {
        I86_INTR_T = 61,                  // INTR acceptance, 7 transfers with the two INTA cycles (2-56/PDF 79)
        I86_NMI_T = 50,                   // NMI (2-60/PDF 83)
        I86_TRAP_T = 50,                  // SINGLE STEP: 50 in Table 2-21 (2-66/PDF 89) and in the 1985 iAPX
                                          // 86/88, 186/188 User's Manual's Table 1-42 (printed 1-121/PDF 137);
                                          // the 1979 manual's AP-67 (printed A-28/PDF 332) says 51.  The sources
                                          // disagree and nothing here measured it: 50 is a model choice, NOT a
                                          // resolved figure (Astra, Reply 106)
        I86_ODD_WORD_T = 4,               // "For the 8086, add four clocks for each 16-bit word transfer with an
                                          //  odd address" (every page of the table)
        I86_WAIT_RECHECK_T = 5            // WAIT: each recheck of TEST after the entry's 3 (3 + 5n, 2-67/PDF 90;
    };                                    //  "retests the TEST line at five-clock intervals", 2-18/PDF 41)

    // A word transfer at an odd address: 4 more T-states (the 8086's bus does it as two cycles).  Every memory and
    // port word access goes through read_word/write_word/read_port_word/write_port_word below; instruction fetches
    // do not (the prefetch queue).  Upstream: none.
    void odd_word(uint32_t addr) { if (addr & 1) m_icount -= I86_ODD_WORD_T; }

    // A REP string instruction is one pass per step (i86_mame.cpp).  Intel charges 9 once and a count per repetition
    // (MOVS 9 + 17/rep, ...): the first pass pays the 9 (with any segment override before it, 2), a pass that
    // continues the same instruction pays only its repetition -- its prefixes, re-fetched by the step, were paid on
    // the first.  A pass after an interrupt is a first pass again (the 8086 re-decodes the instruction; a model).
    bool m_rep_ran;                       // this step ran a REP pass
    bool m_rep_continue;                  // ... continuing the one the previous step left (IP back on its prefix)
    bool m_rep_pending;                   // the previous step left a REP to run again from m_rep_at
    uint32_t m_rep_at;
    void rep_first(uint8_t base)
    {
        m_rep_ran = true;
        if (m_rep_continue)
            m_icount = 0;                 // this step's re-fetched prefixes: paid on the first pass
        else
            m_icount -= m_timing[base];
    }
    void rep_count(uint8_t one, uint8_t count)
    {
        m_icount += m_timing[one];        // the pass charged the plain instruction's entry (i_movsb and the like) ...
        m_icount -= m_timing[count];      // ... a repetition costs the table's count instead
    }

    // WAIT (Astra, Reply 106): Intel's 3 + 5n.  One step is the entry or one recheck: the entry costs WAIT's row, 3
    // (2-67/PDF 90), and tests TEST at once -- active, the WAIT is done in 3 (n = 0); inactive, IP goes back on the
    // WAIT and each following step is a recheck of 5 that tests TEST again, ending the WAIT when it is active.  An
    // interrupt is accepted between rechecks ("after any ... wait test cycle", 2-24/PDF 47) and pushes the WAIT's
    // address; after its handler the WAIT is entered again: 3 (a model: "the WAIT instruction is again fetched prior
    // to servicing the interrupt", the 1985 iAPX 86/88 manual's 1.7.8, printed 1-122/PDF 138).  Which step is a
    // recheck: the one right after a step that left this WAIT waiting, with nothing between (as the REP
    // continuation).
    bool m_wait_continue;                 // this step's WAIT is a recheck of the one the previous step left waiting
    bool m_wait_pending;                  // the previous step left a WAIT waiting at m_wait_at
    uint32_t m_wait_at;
    void wait_clk()
    {
        m_icount -= m_wait_continue ? (int)I86_WAIT_RECHECK_T : m_timing[WAIT];
    }
    void wait_hold()
    {
        m_ip--;                           // upstream's: IP back on the WAIT -- on its 9Bh byte, after any prefix: a
                                          // prefixed WAIT rechecks and is interrupted without it (a documented
                                          // limitation, not a hardware claim: test wait_prefixed; Reply 110)
        m_wait_pending = true;
        m_wait_at = ((m_sregs[CS] << 4) + m_ip) & 0xfffff;
    }

    // ---- the framework's calls, answered ----
    template <typename... T> void logerror(T &&...) const {}
    void debugger_exception_hook(int) const {}
    bool access_to_be_redone() const { return false; }
    uint64_t total_cycles() const { return 1; }
    u8 standard_irq_callback(int, u32)
    {
        int v = m_bus->irq_ack ? m_bus->irq_ack(m_bus->ctx, I86_INTR, 0) : -1;
        return v < 0 ? 0xff : (u8)v;
    }
    i86_unconnected m_lock_handler;
    i86_no_esc m_esc_opcode_handler, m_esc_data_handler;

    // ---- memory and I/O (i86.cpp's accessors, restated on the cpu_bus) ----
    uint8_t read_byte(uint32_t addr) { return m_bus->read(m_bus->ctx, addr & 0xfffff); }
    uint16_t read_word(uint32_t addr) { odd_word(addr); return (uint16_t)(read_byte(addr) | (read_byte(addr + 1) << 8)); }
    void write_byte(uint32_t addr, uint8_t data) { m_bus->write(m_bus->ctx, addr & 0xfffff, data); }
    void write_word(uint32_t addr, uint16_t data) { odd_word(addr); write_byte(addr, (uint8_t)data); write_byte(addr + 1, (uint8_t)(data >> 8)); }
    uint8_t read_port_byte(uint16_t port) { return m_bus->in(m_bus->ctx, port); }
    uint16_t read_port_word(uint16_t port) { odd_word(port); return (uint16_t)(read_port_byte(port) | (read_port_byte((uint16_t)(port + 1)) << 8)); }
    void write_port_byte(uint16_t port, uint8_t data) { m_bus->out(m_bus->ctx, port, data); }
    void write_port_byte_al(uint16_t port) { write_port_byte(port, m_regs.b[AL]); }
    void write_port_word(uint16_t port, uint16_t data) { odd_word(port); write_port_byte(port, (uint8_t)data); write_port_byte((uint16_t)(port + 1), (uint8_t)(data >> 8)); }
    uint32_t update_pc() { return m_pc = (m_sregs[CS] << 4) + m_ip; }
    uint8_t fetch()
    {
        uint32_t a = update_pc() & 0xfffff;
        uint8_t data = m_bus->fetch ? m_bus->fetch(m_bus->ctx, a) : m_bus->read(m_bus->ctx, a);
        m_ip++;
        return data;
    }

    // ---- from i86.h (the revision in mame_i86/PINNED.txt) ----
    enum
    {
        EXCEPTION, IRET,                                /* EXCEPTION, iret */
        INT3, INT_IMM, INTO_NT, INTO_T,                 /* intS */
        OVERRIDE,                                       /* SEGMENT OVERRIDES */
        FLAG_OPS, LAHF, SAHF,                           /* FLAG OPERATIONS */
        AAA, AAS, AAM, AAD,                             /* ARITHMETIC ADJUSTS */
        DAA, DAS,                                       /* DECIMAL ADJUSTS */
        CBW, CWD,                                       /* SIGN EXTENSION */
        HLT, LOAD_PTR, LEA, NOP, WAIT, XLAT,            /* MISC */

        JMP_SHORT, JMP_NEAR, JMP_FAR,                   /* DIRECT jmpS */
        JMP_R16, JMP_M16, JMP_M32,                      /* INDIRECT jmpS */
        CALL_NEAR, CALL_FAR,                            /* DIRECT callS */
        CALL_R16, CALL_M16, CALL_M32,                   /* INDIRECT callS */
        RET_NEAR, RET_FAR, RET_NEAR_IMM, RET_FAR_IMM,   /* RETURNS */
        JCC_NT, JCC_T, JCXZ_NT, JCXZ_T,                 /* CONDITIONAL jmpS */
        LOOP_NT, LOOP_T, LOOPE_NT, LOOPE_T,             /* LOOPS */

        IN_IMM8, IN_IMM16, IN_DX8, IN_DX16,             /* PORT READS */
        OUT_IMM8, OUT_IMM16, OUT_DX8, OUT_DX16,         /* PORT WRITES */

        MOV_RR8, MOV_RM8, MOV_MR8,                      /* MOVE, 8-BIT */
        MOV_RI8, MOV_MI8,                               /* MOVE, 8-BIT IMMEDIATE */
        MOV_RR16, MOV_RM16, MOV_MR16,                   /* MOVE, 16-BIT */
        MOV_RI16, MOV_MI16,                             /* MOVE, 16-BIT IMMEDIATE */
        MOV_AM8, MOV_AM16, MOV_MA8, MOV_MA16,           /* MOVE, al/ax MEMORY */
        MOV_SR, MOV_SM, MOV_RS, MOV_MS,                 /* MOVE, SEGMENT REGISTERS */
        XCHG_RR8, XCHG_RM8,                             /* EXCHANGE, 8-BIT */
        XCHG_RR16, XCHG_RM16, XCHG_AR16,                /* EXCHANGE, 16-BIT */

        PUSH_R16, PUSH_M16, PUSH_SEG, PUSHF,            /* PUSHES */
        POP_R16, POP_M16, POP_SEG, POPF,                /* POPS */

        ALU_RR8, ALU_RM8, ALU_MR8,                      /* alu OPS, 8-BIT */
        ALU_RI8, ALU_MI8, ALU_MI8_RO,                   /* alu OPS, 8-BIT IMMEDIATE */
        ALU_RR16, ALU_RM16, ALU_MR16,                   /* alu OPS, 16-BIT */
        ALU_RI16, ALU_MI16, ALU_MI16_RO,                /* alu OPS, 16-BIT IMMEDIATE */
        ALU_R16I8, ALU_M16I8, ALU_M16I8_RO,             /* alu OPS, 16-BIT W/8-BIT IMMEDIATE */
        MUL_R8, MUL_R16, MUL_M8, MUL_M16,               /* mul */
        IMUL_R8, IMUL_R16, IMUL_M8, IMUL_M16,           /* imul */
        DIV_R8, DIV_R16, DIV_M8, DIV_M16,               /* div */
        IDIV_R8, IDIV_R16, IDIV_M8, IDIV_M16,           /* idiv */
        INCDEC_R8, INCDEC_R16, INCDEC_M8, INCDEC_M16,   /* inc/dec */
        NEGNOT_R8, NEGNOT_R16, NEGNOT_M8, NEGNOT_M16,   /* neg/not */

        ROT_REG_1, ROT_REG_BASE, ROT_REG_BIT,           /* REG SHIFT/ROTATE */
        ROT_M8_1, ROT_M8_BASE, ROT_M8_BIT,              /* M8 SHIFT/ROTATE */
        ROT_M16_1, ROT_M16_BASE, ROT_M16_BIT,           /* M16 SHIFT/ROTATE */

        CMPS8, REP_CMPS8_BASE, REP_CMPS8_COUNT,         /* cmps 8-BIT */
        CMPS16, REP_CMPS16_BASE, REP_CMPS16_COUNT,      /* cmps 16-BIT */
        SCAS8, REP_SCAS8_BASE, REP_SCAS8_COUNT,         /* scas 8-BIT */
        SCAS16, REP_SCAS16_BASE, REP_SCAS16_COUNT,      /* scas 16-BIT */
        LODS8, REP_LODS8_BASE, REP_LODS8_COUNT,         /* lods 8-BIT */
        LODS16, REP_LODS16_BASE, REP_LODS16_COUNT,      /* lods 16-BIT */
        STOS8, REP_STOS8_BASE, REP_STOS8_COUNT,         /* stos 8-BIT */
        STOS16, REP_STOS16_BASE, REP_STOS16_COUNT,      /* stos 16-BIT */
        MOVS8, REP_MOVS8_BASE, REP_MOVS8_COUNT,         /* movs 8-BIT */
        MOVS16, REP_MOVS16_BASE, REP_MOVS16_COUNT,      /* movs 16-BIT */

        INS8, REP_INS8_BASE, REP_INS8_COUNT,            /* (80186) ins 8-BIT */
        INS16, REP_INS16_BASE, REP_INS16_COUNT,         /* (80186) ins 16-BIT */
        OUTS8, REP_OUTS8_BASE, REP_OUTS8_COUNT,         /* (80186) outs 8-BIT */
        OUTS16, REP_OUTS16_BASE, REP_OUTS16_COUNT,      /* (80186) outs 16-BIT */
        PUSH_IMM, PUSHA, POPA,                          /* (80186) push IMMEDIATE, pusha/popa */
        IMUL_RRI8, IMUL_RMI8,                           /* (80186) imul IMMEDIATE 8-BIT */
        IMUL_RRI16, IMUL_RMI16,                         /* (80186) imul IMMEDIATE 16-BIT */
        ENTER0, ENTER1, ENTER_BASE, ENTER_COUNT, LEAVE, /* (80186) enter/leave */
        BOUND                                           /* (80186) bound */
    };

    enum SREGS { ES=0, CS, SS, DS };
    enum WREGS { AX=0, CX, DX, BX, SP, BP, SI, DI };
    enum BREGS {                                        // NATIVE_ENDIAN_VALUE_LE_BE's little-endian values
        AL = 0x0, AH = 0x1, CL = 0x2, CH = 0x3, DL = 0x4, DH = 0x5, BL = 0x6, BH = 0x7,
        SPL = 0x8, SPH = 0x9, BPL = 0xa, BPH = 0xb, SIL = 0xc, SIH = 0xd, DIL = 0xe, DIH = 0xf
    };
    enum { I8086_READ, I8086_WRITE, I8086_FETCH, I8086_NONE };

    void device_reset();
    void execute_set_input(int inputnum, int state);
    void interrupt(int int_num, int trap = 1);
    bool common_op(uint8_t op);
    uint32_t calc_addr(int seg, uint16_t offset, int size, int op, bool override = true);

    uint8_t fetch_op() { return fetch(); }
    inline uint16_t fetch_word();
    inline uint8_t repx_op();
    inline void CLK(uint8_t op);
    inline void CLKM(uint8_t op_reg, uint8_t op_mem);
    inline uint32_t get_ea(int size, int op);
    inline void PutbackRMByte(uint8_t data);
    inline void PutbackRMWord(uint16_t data);
    inline void RegByte(uint8_t data);
    inline void RegWord(uint16_t data);
    inline uint8_t RegByte();
    inline uint16_t RegWord();
    inline uint16_t GetRMWord();
    inline uint16_t GetnextRMWord();
    inline uint8_t GetRMByte();
    inline void PutMemB(int seg, uint16_t offset, uint8_t data);
    inline void PutMemW(int seg, uint16_t offset, uint16_t data);
    inline uint8_t GetMemB(int seg, uint16_t offset);
    inline uint16_t GetMemW(int seg, uint16_t offset);
    inline void PutImmRMWord();
    inline void PutRMWord(uint16_t val);
    inline void PutRMByte(uint8_t val);
    inline void PutImmRMByte();
    inline void DEF_br8();
    inline void DEF_wr16();
    inline void DEF_r8b();
    inline void DEF_r16w();
    inline void DEF_ald8();
    inline void DEF_axd16();
    inline void set_CFB(uint32_t x);
    inline void set_CFW(uint32_t x);
    inline void set_AF(uint32_t x, uint32_t y, uint32_t z);
    inline void set_SF(uint32_t x);
    inline void set_ZF(uint32_t x);
    inline void set_PF(uint32_t x);
    inline void set_SZPF_Byte(uint32_t x);
    inline void set_SZPF_Word(uint32_t x);
    inline void set_OFW_Add(uint32_t x, uint32_t y, uint32_t z);
    inline void set_OFB_Add(uint32_t x, uint32_t y, uint32_t z);
    inline void set_OFW_Sub(uint32_t x, uint32_t y, uint32_t z);
    inline void set_OFB_Sub(uint32_t x, uint32_t y, uint32_t z);
    inline uint16_t CompressFlags() const;
    inline void ExpandFlags(uint16_t f);
    inline void i_insb();
    inline void i_insw();
    inline void i_outsb();
    inline void i_outsw();
    inline void i_movsb();
    inline void i_movsw();
    inline void i_cmpsb();
    inline void i_cmpsw();
    inline void i_stosb();
    inline void i_stosw();
    inline void i_lodsb();
    inline void i_lodsw();
    inline void i_scasb();
    inline void i_scasw();
    inline void i_popf();
    inline uint32_t ADDB(uint8_t c = 0);
    inline uint32_t ADDX(uint8_t c = 0);
    inline uint32_t SUBB(uint8_t b = 0);
    inline uint32_t SUBX(uint8_t b = 0);
    inline void ORB();
    inline void ORW();
    inline void ANDB();
    inline void ANDX();
    inline void XORB();
    inline void XORW();
    inline void ROL_BYTE();
    inline void ROL_WORD();
    inline void ROR_BYTE();
    inline void ROR_WORD();
    inline void ROLC_BYTE();
    inline void ROLC_WORD();
    inline void RORC_BYTE();
    inline void RORC_WORD();
    inline void SHL_BYTE(uint8_t c);
    inline void SHL_WORD(uint8_t c);
    inline void SHR_BYTE(uint8_t c);
    inline void SHR_WORD(uint8_t c);
    inline void SHRA_BYTE(uint8_t c);
    inline void SHRA_WORD(uint8_t c);
    inline void XchgAXReg(uint8_t reg);
    inline void IncWordReg(uint8_t reg);
    inline void DecWordReg(uint8_t reg);
    inline void PUSH(uint16_t data);
    inline uint16_t POP();
    inline void JMP(bool cond);
    inline void ADJ4(int8_t param1, int8_t param2);
    inline void ADJB(int8_t param1, int8_t param2);

    union
    {
        uint16_t w[8];
        uint8_t b[16];
    } m_regs;

    uint16_t m_sregs[4];
    uint16_t m_ip;
    uint16_t m_prev_ip;
    bool m_io_stall = false;

    int32_t m_SignVal;
    uint32_t m_AuxVal, m_OverVal, m_ZeroVal, m_CarryVal, m_ParityVal;
    uint8_t m_TF, m_IF, m_DF;
    uint8_t m_IOPL, m_NT, m_MF;
    uint32_t m_int_vector;
    uint32_t m_pending_irq;
    uint32_t m_nmi_state;
    uint8_t m_no_interrupt;
    uint8_t m_fire_trap;
    uint8_t m_test_state;

    int m_icount;

    uint32_t m_prefix_seg;
    bool m_seg_prefix;
    bool m_seg_prefix_next;

    uint32_t m_ea;
    uint16_t m_eo;
    int m_easeg;

    uint8_t m_modrm;
    uint32_t m_dst;
    uint32_t m_src;
    uint32_t m_pc;

    uint8_t m_parity_table[256];
    struct {
        struct {
            int w[256];
            int b[256];
        } reg;
        struct {
            int w[256];
            int b[256];
        } RM;
    } m_Mod_RM;

    uint8_t m_timing[200];
    uint8_t m_ea_timing[200];
    bool m_halt;
    bool m_lock;

    // i8086_cpu_device's
    static const uint8_t m_i8086_timing[200];
    static const uint8_t m_i8086_ea_timing[200];
};

typedef i8086_common_cpu_device i8086_cpu_device;

#endif
