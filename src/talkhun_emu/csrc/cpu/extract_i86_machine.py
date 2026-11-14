"""Generate i86_mame_machine.cpp from MAME's i86.cpp and i86inline.h: the 8086's machine code this library needs, copied
from exact upstream line ranges, with the framework calls replaced by named substitutions (each listed below and marked
'CHANGED' in the output).  It refuses to run if a source is not the pinned revision or an anchor line has moved.

    python src/csrc/cpu/extract_i86_machine.py <folder holding i86.cpp and i86inline.h, or a MAME checkout>

The pinned sources: MAME c0d3677674339a489efbad881047012ce8c2cc96, src/devices/cpu/i86/ (sha256 below, of the files as
upstream stores them, LF line ends: a Windows checkout's CRLF is normalised first; mame_i86/PINNED.txt).  They are
BSD-3-Clause (copyright-holders: Carl); the generated file keeps that notice.  What is left out: the MAME device framework
(constructors, address spaces, the state table and save states, the disassembler), the memory and port accessors (ours,
in i86_mame.hpp: the cpu_bus callbacks) and execute_run -- replaced by our own step driver in i86_mame.cpp, see
CONTRACT.md; execute_run's own opcodes (POP CS, the shifts by CL, ESC) are kept, as execute_op().  The 80186 and 80286
(i186.cpp, i286.cpp) are not taken: the Accent-mini's driver needs only the 8086 (README.md).  The class it compiles
against is i86_mame.hpp.

The clock counts the substitutions correct come from Intel's manual (Astra, Replies 104 and 106; CONTRACT.md 4): each
is its own named substitution, so i86_controls.py can put one back alone and see exactly its tests fail.  After
Reply 106 every row is the 8086's (one CPU, no 8088 rows), and WAIT is Intel's 3 + 5n.  Reply 110 adds three rows
(LOOPNE taken, TEST reg,imm and mem,imm) and one defined-flag correction: IMUL's CF and OF, byte and word.
"""
import hashlib
import os
import sys

REVISION = "c0d3677674339a489efbad881047012ce8c2cc96"
SHA256 = {
    "i86.cpp": "22138681b88981a49721944952f1eba4f060d0e0c924c194994847a46e062a7a",
    "i86inline.h": "8c060f5f465811da6c9a8640c2ca9181d30fc386060f3521859245bb476187ec",
    "i86.h": "274ebbde7817417c3add1534dce94d1ecaea8ddbc1c5f09a7c091828fb26c81a",   # restated in i86_mame.hpp
}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i86_mame_machine.cpp")

# (file, first line, last line, the text that must open the range, what it is); line numbers as sed and grep count them
RANGES = [
    ("i86inline.h", 5, 968, "#define CF", "the flag macros and every inline helper (fetch_word, get_ea, the ALU, "
                                            "the string ops, PUSH/POP)"),
    ("i86.cpp", 32, 111, "#define I8086_NMI_INT_VECTOR 2", "the NMI vector, the cycle tables"),
    ("i86.cpp", 407, 433, "static const BREGS reg_name[8]", "the constructor's tables (parity, ModRM)"),
    ("i86.cpp", 560, 596, "void i8086_common_cpu_device::device_reset()", "reset"),
    ("i86.cpp", 599, 616, "void i8086_common_cpu_device::interrupt(int int_num, int trap)", "an interrupt's entry"),
    ("i86.cpp", 619, 639, "void i8086_common_cpu_device::execute_set_input( int inptnum, int state )", "the input lines"),
    ("i86.cpp", 699, 711, "uint32_t i8086_common_cpu_device::calc_addr(", "segment:offset to an address"),
    ("i86.cpp", 283, 369, "switch(op)", "execute_run's own opcodes: POP CS, the shifts by CL, ESC"),
    ("i86.cpp", 713, 2620, "bool i8086_common_cpu_device::common_op(uint8_t op)", "every other instruction"),
]

# our lines around a range
BEFORE = {
    ("i86.cpp", 407): ["void i8086_common_cpu_device::init_tables()   // CHANGED: the constructor's body; its initialiser "
                       "list is our constructor's", "{"],
    ("i86.cpp", 283): ["// CHANGED (ours): execute_run's own opcodes, as a function the step driver (i86_mame.cpp) calls with",
                       "// the fetched opcode.  The lines are execute_run's switch; the loop, the interrupt dispatch and the",
                       "// trap around it are the step driver's.",
                       "void i8086_common_cpu_device::execute_op(uint8_t op)", "{"],
}
AFTER = {
    ("i86.cpp", 407): ["}"],
    ("i86.cpp", 283): ["}"],
}

# (upstream text, replacement, why, how many times it must match) -- applied to the copied text only
SUBS = [
    ("void i8086_common_cpu_device::interrupt(int int_num, int trap)\n{\n",
     "void i8086_common_cpu_device::interrupt(int int_num, int trap)\n{\n"
     "\t// CHANGED: the host's seam (CONTRACT.md 4, cpu_bus.intercept): an INT n, INT 3, INTO or divide error raised by\n"
     "\t// the instruction may be serviced by the host instead -- nothing pushed, the instruction ends here\n"
     "\tif (drv_intercept(int_num, trap))\n\t\treturn;\n",
     "the INT seam", 1),
    ("\t\t\t//logerror(\"%s: %06x: HALT\\n\", tag(), m_pc);\n\t\t\tm_icount = 0;\n\t\t\tm_halt = true;",
     "\t\t\t//logerror(\"%s: %06x: HALT\\n\", tag(), m_pc);\n"
     "\t\t\tCLK(HLT);   // CHANGED: HLT's own 2 T-states (the table's HLT); upstream ends the slice (m_icount = 0)\n"
     "\t\t\tm_halt = true;",
     "HLT's T-states", 1),
    # WAIT (Astra, Reply 106): Intel's 3 + 5n (Table 2-21, printed 2-67/PDF 90) -- 3 on entering the instruction,
    # then 5 for each recheck of TEST (five-clock intervals: printed 2-18/PDF 41), one per step; TEST found active
    # ends it.  An interrupt is accepted between rechecks (printed 2-24/PDF 47) with IP on the WAIT, so the handler
    # returns to it and it is entered again: 3 (i86_mame.hpp's wait_clk and wait_hold)
    ("\t\t\tif (m_test_state == 0)\n\t\t\t{\n\t\t\t\tm_icount = 0;\n\t\t\t\tm_ip--;\n\t\t\t}\n\t\t\telse\n"
     "\t\t\t\tCLK(WAIT);",
     "\t\t\twait_clk();   // CHANGED: 3 T on entry, 5 for each recheck (Intel's 3 + 5n; upstream charged 3, or ended "
     "the slice)\n"
     "\t\t\tif (m_test_state == 0)\n"
     "\t\t\t\twait_hold();   // CHANGED: TEST inactive: IP back on the WAIT, the next step rechecks (upstream ended "
     "the slice)",
     "WAIT: 3 on entry, 5 a recheck", 1),
] + [
    # ---- clock counts from Intel's manual (Astra, Reply 104): The 8086 Family User's Manual, Oct 1979 (9800722-03),
    # Table 2-21, cited as printed page / PDF page.  Each is its own substitution, so a control can undo one alone.
    ("\t51,32,          /* exception, IRET */",
     "\t51,24,          /* exception, IRET */   // CHANGED: IRET 24 (Table 2-21, printed 2-56/PDF 79), its POPF "
     "included (see 'IRET charges no POPF'); upstream 32 + POPF 12 = 44.  EXCEPTION 51 (unused "
     "upstream) is the divide error's entry: a model, see 'the divide error's entry'",
     "IRET 24", 1),
    ("\t\t\ti_popf();\n\t\t\tCLK(IRET);",
     "\t\t\ti_popf();\n"
     "\t\t\tm_icount += m_timing[POPF];   // CHANGED: IRET's 24 includes restoring FLAGS; upstream also charges POPF's 12\n"
     "\t\t\tCLK(IRET);",
     "IRET charges no POPF", 1),
    ("\t\t2, 0, 4, 2, /* INTs */",
     "\t\t52,51, 4,53, /* INTs */   // CHANGED: INT 3 52, INT n 51, INTO 4 not taken / 53 taken (Table 2-21, printed "
     "2-56/PDF 79); upstream 2, 0, 4, 2.  An intercepted one costs the same (CONTRACT.md 4)",
     "the software interrupts' T-states", 1),
    ("\t\t2,24, 2, 2, 3,11,   /* misc */",
     "\t\t2,24, 2, 3, 3,11,   /* misc */   // CHANGED: NOP 3 (Table 2-21, printed 2-62/PDF 85); upstream 2",
     "NOP 3", 1),
    ("\t\t\tm_no_interrupt = 1;\n\t\t\tCLK(NOP);",
     "\t\t\tm_no_interrupt = 1;\n"
     "\t\t\tCLK(OVERRIDE);   // CHANGED: LOCK is a 2-T prefix (Table 2-21, printed 2-60/PDF 83), the segment "
     "override's 2; upstream charged NOP's entry",
     "LOCK 2", 1),
    ("\t\t\t\t\tm_esc_data_handler(0);\n\t\t\t\tCLK(NOP);",
     "\t\t\t\t\tm_esc_data_handler(0);\n"
     "\t\t\t\tm_icount -= (m_modrm < 0xc0) ? 8 : 2;   // CHANGED: ESC 8 + EA with a memory operand, 2 with a "
     "register (Table 2-21, printed 2-54/PDF 77); upstream charged NOP's entry (+ EA)",
     "ESC's T-states", 1),
    # the REP string forms: Intel's 9 + n per repetition (MOVS 17, printed 2-61/PDF 84; CMPS 22, 2-53/PDF 76; SCAS
    # 15, 2-65/PDF 88; LODS 13, 2-60/PDF 83; STOS 10, 2-66/PDF 89).  Upstream's table has these rows but never uses
    # them (it charges the REP as an override, 2, and each pass as the plain instruction); three of its counts differ
    ("\t22, 9,21,       /* CMPS 8-bit */\n\t22, 9,21,       /* CMPS 16-bit */",
     "\t22, 9,22,       /* CMPS 8-bit */\n\t22, 9,22,       /* CMPS 16-bit */   // CHANGED: REP CMPS 9 + 22/rep "
     "(printed 2-53/PDF 76); upstream 21",
     "REP CMPS 22 a repetition", 1),
    ("\t15, 9,14,       /* SCAS 8-bit */\n\t15, 9,14,       /* SCAS 16-bit */",
     "\t15, 9,15,       /* SCAS 8-bit */\n\t15, 9,15,       /* SCAS 16-bit */   // CHANGED: REP SCAS 9 + 15/rep "
     "(printed 2-65/PDF 88); upstream 14",
     "REP SCAS 15 a repetition", 1),
    ("\t12, 9,11,       /* LODS 8-bit */\n\t12, 9,11,       /* LODS 16-bit */",
     "\t12, 9,13,       /* LODS 8-bit */\n\t12, 9,13,       /* LODS 16-bit */   // CHANGED: REP LODS 9 + 13/rep "
     "(printed 2-60/PDF 83); upstream 11",
     "REP LODS 13 a repetition", 1),
    ("\t\t\t\t\t// Decrement IP so the normal instruction will be executed next\n\t\t\t\t\tm_ip--;\n",
     "\t\t\t\t\t// Decrement IP so the normal instruction will be executed next\n\t\t\t\t\tm_ip--;\n"
     "\t\t\t\t\tCLK(OVERRIDE);   // CHANGED: the REP prefix's own 2 T (Table 2-21, REP, printed 2-63/PDF 86): "
     "upstream charged none, a 0-T step\n",
     "a REP before a non-string instruction 2 T", 2),
    # ---- the 8086's own rows (Astra, Reply 106: one CPU, the virtual 8086; no 8088 rows).  Upstream's stack,
    # word-port, return, LDS/LES and word MUL/DIV rows are the 8088's: Intel's 8086 figure + 4 for every word
    # transfer, the footnote's 8088 rule ("For the 8088, add four clocks for each 16-bit word transfer"), and its
    # returns match neither CPU.  The 8086 adds its 4 only for a word transfer at an odd address, which read_word /
    # write_word / the word port accessors already do (i86_mame.hpp's odd_word), once per actual transfer.
    ("\t15,24,14,14,    /* pushes */",
     "\t11,16,10,10,    /* pushes */   // CHANGED: PUSH r16 11, PUSH mem 16 + EA, PUSH sreg 10 (printed 2-63/PDF "
     "86), PUSHF 10 (2-63/PDF 86); upstream 15, 24, 14, 14 (the 8088's)",
     "the pushes: the 8086's", 1),
    ("\t12,25,12,12,    /* pops */",
     "\t 8,17, 8, 8,    /* pops */   // CHANGED: POP r16 8, POP mem 17 + EA, POP sreg 8 (printed 2-62/PDF 85), "
     "POPF 8 (2-63/PDF 86); upstream 12, 25, 12, 12 (the 8088's)",
     "the pops: the 8086's", 1),
    ("\t10,14, 8,12,    /* port reads */",
     "\t10,10, 8, 8,    /* port reads */   // CHANGED: IN AX,imm8 10 and IN AX,DX 8, as the byte forms (printed "
     "2-55/PDF 78); upstream 14, 12 (the 8088's)",
     "the word port reads: the 8086's", 1),
    ("\t10,14, 8,12,    /* port writes */",
     "\t10,10, 8, 8,    /* port writes */   // CHANGED: OUT imm8,AX 10 and OUT DX,AX 8, as the byte forms (printed "
     "2-62/PDF 85); upstream 14, 12 (the 8088's)",
     "the word port writes: the 8086's", 1),
    ("\t20,32,24,31,    /* returns */",
     "\t 8,18,12,17,    /* returns */   // CHANGED: RET 8, RETF 18, RET n 12, RETF n 17 (intra/inter-segment, no pop/"
     "pop; printed 2-64/PDF 87); upstream 20, 32, 24, 31",
     "the returns: the 8086's", 1),
    ("\t\t2,24, 2, 3, 3,11,   /* misc */",
     "\t\t2,16, 2, 3, 3,11,   /* misc */   // CHANGED: LDS/LES 16 + EA (printed 2-59/PDF 82); upstream 24 (the "
     "8088's)",
     "LDS/LES 16", 1),
    ("\t70,118,76,128,  /* MUL */",
     "\t70,118,76,124,  /* MUL */   // CHANGED: MUL m16 124 + EA, the low end of Intel's (124-139) + EA (printed "
     "2-61/PDF 84); upstream 128 (the 8088's)",
     "MUL m16 124", 1),
    ("\t80,128,86,138,  /* IMUL */",
     "\t80,128,86,134,  /* IMUL */   // CHANGED: IMUL m16 134 + EA, the low end of (134-160) + EA (printed 2-55/"
     "PDF 78); upstream 138 (the 8088's)",
     "IMUL m16 134", 1),
    ("\t80,144,86,154,  /* DIV */",
     "\t80,144,86,150,  /* DIV */   // CHANGED: DIV m16 150 + EA, the low end of (150-168) + EA (printed 2-54/PDF "
     "77); upstream 154 (the 8088's)",
     "DIV m16 150", 1),
    ("\t101,165,107,175,/* IDIV */",
     "\t101,165,107,171,/* IDIV */   // CHANGED: IDIV m16 171 + EA, the low end of (171-190) + EA (printed 2-55/"
     "PDF 78); upstream 175 (the 8088's)",
     "IDIV m16 171", 1),
    # ---- three more of the 8086's rows (Astra, Reply 110): where upstream charges a row shared with another form,
    # the substitution is in the one instruction's handler, so the rows it shares (LOOP's 17, the ALU's reg,imm 4 --
    # TEST AL/AX,imm (A8/A9) and the 80h-83h group -- and CMP's mem,imm 10) stay as they are
    ("\t\t\t\tif (!ZF && m_regs.w[CX])\n\t\t\t\t{\n\t\t\t\t\tm_ip = m_ip + disp;\n\t\t\t\t\tCLK(LOOP_T);",
     "\t\t\t\tif (!ZF && m_regs.w[CX])\n\t\t\t\t{\n\t\t\t\t\tm_ip = m_ip + disp;\n"
     "\t\t\t\t\tm_icount -= 19;   // CHANGED: LOOPNE taken 19 (\"19 or 5\", printed 2-60/PDF 83); upstream LOOP's "
     "17.  Not taken: LOOP's 5, as upstream",
     "LOOPNE taken 19", 1),
] + [
    # TEST r/m,imm (F6/F7 /0): Intel's register,immediate 5 and memory,immediate 11 + EA (printed 2-67/PDF 90);
    # upstream charged the ALU's reg,imm 4 and CMP's mem,imm 10.  Two rows, two substitutions (each width): the first
    # splits upstream's CLKM into its register and memory arms and sets the register's, the second the memory's
    ("\t\t\t\t\tset_SZPF_%s(tmp);\n\t\t\t\t\tCLKM(ALU_RI%s,ALU_MI%s_RO);" % (name, w, w),
     "\t\t\t\t\tset_SZPF_%s(tmp);\n\t\t\t\t\tif (m_modrm >= 0xc0)\n"
     "\t\t\t\t\t\tm_icount -= 5;   // CHANGED: TEST r%s,imm 5 (printed 2-67/PDF 90); upstream the ALU's reg,imm 4 "
     "(TEST AL/AX,imm keeps its own 4)\n\t\t\t\t\telse\n\t\t\t\t\t\tCLK(ALU_MI%s_RO);" % (name, w, w),
     "TEST r%s,imm 5" % w, 1)
    for name, w in (("Byte", "8"), ("Word", "16"))
] + [
    ("\t\t\t\t\telse\n\t\t\t\t\t\tCLK(ALU_MI%s_RO);" % w,
     "\t\t\t\t\telse\n\t\t\t\t\t\tm_icount -= 11;   // CHANGED: TEST m%s,imm 11 + EA (printed 2-67/PDF 90); upstream "
     "CMP's mem,imm 10 + EA" % w,
     "TEST m%s,imm 11 + EA" % w, 1)
    for w in ("8", "16")
] + [
    # IMUL's CF and OF (Astra, Reply 110): Intel's IMUL "If the upper half of the result (AH for a byte source, DX for
    # a word source) is not the sign extension of the lower half of the result, CF and OF are set; otherwise they are
    # cleared" (printed 2-37/PDF 60) -- set exactly when the signed product does not fit the source's width.  Upstream
    # tests AH != 0 / DX != 0, which is MUL's rule: it sets them for every small negative product (-1 x 1) and misses
    # a positive overflow whose upper half is zero (127 x 2).  The product itself was right; AF, PF, SF and ZF stay
    # upstream's (Intel: undefined after IMUL)
    ("\t\t\t\t\tm_regs.w[AX] = (uint16_t)result;\n\t\t\t\t\tm_CarryVal = m_OverVal = (m_regs.b[AH]!=0) ? 1 : 0;",
     "\t\t\t\t\tm_regs.w[AX] = (uint16_t)result;\n"
     "\t\t\t\t\tm_CarryVal = m_OverVal = (result < -128 || result > 127) ? 1 : 0;   // CHANGED: IMUL r/m8: set when "
     "the product does not fit a signed byte, AH not AL's sign extension (printed 2-37/PDF 60); upstream AH != 0",
     "IMUL r/m8's CF and OF", 1),
    ("\t\t\t\t\tm_regs.w[DX] = result >> 16;\n\t\t\t\t\tm_CarryVal = m_OverVal = (m_regs.w[DX] != 0) ? 1 : 0;",
     "\t\t\t\t\tm_regs.w[DX] = result >> 16;\n"
     "\t\t\t\t\tm_CarryVal = m_OverVal = (result < -32768 || result > 32767) ? 1 : 0;   // CHANGED: IMUL r/m16: set "
     "when the product does not fit a signed word, DX not AX's sign extension (printed 2-37/PDF 60); upstream DX != 0",
     "IMUL r/m16's CF and OF", 1),
    # the divide error (DIV, IDIV, AAM 0): its entry, charged when the instruction raises it, before the host's seam
    ("\tif (drv_intercept(int_num, trap))\n\t\treturn;\n",
     "\tif (m_in_instruction && trap)   // CHANGED: a divide error's entry, 51 -- a MODEL: Intel gives no figure. "
     "Like INT n\n"
     "\t\tCLK(EXCEPTION);                 // it runs no INTA cycles (printed 2-25/PDF 48), and INT n's entry is 51 "
     "(2-56/PDF 79). Upstream: 0\n"
     "\tif (drv_intercept(int_num, trap))\n\t\treturn;\n",
     "the divide error's entry", 1),
] + [
    # each REP pass: the 9 on the first pass only, then the repetition count in place of the plain instruction's
    ("CLK(OVERRIDE); if (c) do { i_%s(); c--; }" % op,
     "rep_first(REP_%s_BASE); /* CHANGED */ if (c) do { i_%s(); rep_count(%s, REP_%s_COUNT); c--; }"
     % (row, op, row, row),
     "REP %s: 9 + n a repetition (CHANGED)" % op, 2)
    for op, row in (("movsb", "MOVS8"), ("movsw", "MOVS16"), ("cmpsb", "CMPS8"), ("cmpsw", "CMPS16"),
                    ("stosb", "STOS8"), ("stosw", "STOS16"), ("lodsb", "LODS8"), ("lodsw", "LODS16"),
                    ("scasb", "SCAS8"), ("scasw", "SCAS16"))
]


def source_path(arg, name):
    for p in (os.path.join(arg, name), os.path.join(arg, "src", "devices", "cpu", "i86", name)):
        if os.path.isfile(p):
            return p
    sys.exit("no %s in %s" % (name, arg))


def load(arg, name):
    raw = open(source_path(arg, name), "rb").read().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != SHA256[name]:
        sys.exit("%s is not the pinned revision %s (sha256 differs)" % (name, REVISION))
    return raw.decode("utf-8").split("\n")


def main():
    src = {name: load(sys.argv[1], name) for name in SHA256}
    cpp = src["i86.cpp"]
    assert cpp[0] == "// license:BSD-3-Clause" and cpp[1] == "// copyright-holders:Carl", cpp[:2]
    assert src["i86inline.h"][0:2] == cpp[0:2], "i86inline.h's notice differs"
    head_end = cpp.index('#include "emu.h"')
    out = cpp[0:2] + [
        "//",
        "// i86_mame_machine.cpp -- GENERATED by extract_i86_machine.py from MAME's src/devices/cpu/i86/i86.cpp and",
        "// i86inline.h at %s (mame_i86/PINNED.txt).  The 8086's machine code," % REVISION,
        "// copied from exact line ranges; framework calls replaced as marked 'CHANGED'.  Do not edit: change the script",
        "// and regenerate.  The class it compiles against: i86_mame.hpp.  Our step driver and the cpu.h API:",
        "// i86_mame.cpp, which includes this file (build that one, never this one alone).",
        "//",
        "// Upstream's header comment, kept:",
    ] + cpp[2:head_end] + [
        '#include "i86_mame.hpp"',
    ]
    for name, a, b, opener, what in RANGES:
        seg = src[name][a - 1:b]
        assert seg[0].strip().startswith(opener.strip()), "%s line %d moved: %r" % (name, a, seg[0])
        out.append("")
        out.append("// ---- upstream %s lines %d-%d: %s " % (name, a, b, what) + "-" * max(0, 50 - len(what)))
        out.extend(BEFORE.get((name, a), []))
        out.extend(seg)
        out.extend(AFTER.get((name, a), []))
    text = "\n".join(out) + "\n"
    for old, new, why, n in SUBS:
        assert text.count(old) == n, "substitution anchor not found %d time(s): %s" % (n, why)
        text = text.replace(old, new)
    open(OUT, "w", encoding="utf-8", newline="\n").write(text)
    print("wrote %s (%d lines from %d upstream ranges)" % (os.path.basename(OUT), text.count("\n"), len(RANGES)))


if __name__ == "__main__":
    main()
