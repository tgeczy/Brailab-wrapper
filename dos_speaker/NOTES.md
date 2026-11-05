# BRAISPK notes: what DOS, TALKHUN and the hardware really do

These are the things that were learned the hard way while getting TALKHUN to
speak on real machines: a Pentium 166 running Windows 98's DOS, and a Dell with
an SB Live! under SBEMU. The [README](README.md) describes the design; this file
describes the surprises. It matches BRAISPK 0.41.

Addresses in TALKHUN are memory offsets in the `.COM` (file offset + 100h), in
the build BRAISPK patches: `TALKHUN.COM`, 64,941 bytes, 20 June 2000. Nothing
here applies unchecked to the 1991 `TALKHUN0.COM`.

TALKHUN itself is not in this repository. `patch_talkhun.py` fetches it from the
[BraiLab PC archive](https://archive.org/details/brailab-pc-archive) or takes your
own copy with `--from`, makes `TALKHUNS.COM`, and refuses any other build.

## How TALKHUN hears the screen

TALKHUN hooks INT 08h, 09h, 10h, 14h and 2Fh. Screen text reaches it through the
INT 10h handler at `1939h`, which watches four calls. The nibble set by `ESC A`
(BRAISET's "biosz10" item, stored at `[AF44h]`) chooses which of them are spoken:

| Bit | Call |
|---|---|
| 0 | AH=09h, write character and attribute |
| 1 | AH=0Ah, write character |
| 2 | AH=0Eh, teletype, which is what DOS uses |
| 3 | AH=13h, write string |

`ESC A F` turns on all four. A wrong value is easy to set from the menu and looks
like a dead synthesizer: with `A2`, DOS output goes silent. Check this first if
the keyboard echo works and `dir` says nothing.

**The mask only decides speech.** Whether or not its bit is set, every character
goes on to `468Eh`, the same routine that takes characters from the virtual COM4
device (INT 14h, at `44AEh`). That routine is the ESC parser. So:

- `TYPE FURCSABE` at the prompt changes the voice just as `COPY FURCSABE COM4`
  does, as long as DOS sends the file through INT 10h (see below).
- Any file full of escape codes can reconfigure the speech by being typed.

### The ESC parser

An ESC moves the state byte `[AF40h]` to FFh. The next character picks a command,
the one after it is the argument, and the state goes back to 0. Every pair needs
its own ESC, which is why `BRAISET.DAT` has one before each. An unknown command
letter is not an error: the state clears and the letter falls through as text.

| Letter | Handler | Argument |
|---|---|---|
| P | `4837h` | raw pitch byte |
| S | `483Bh` | speed, see below |
| F | `488Dh` | `0` or `1`, furcsa; anything else ignored |
| R | `48A1h` | `0` or `1`, spell out detail |
| C | `48B5h` | `0` or `1`, line end |
| E | `48C8h` | `0` or `1`, spaces |
| A | `48DBh` | hex digit, the mask above |
| K | `48EAh` | `0` or `1`, code announcement |
| L | `48FEh` | hex digit, key locks |
| N X T k | `490Dh` | swallowed; this handler only clears the state |

Below 20h, the text path keeps only tab (as a space) and carriage return. All
other control characters are dropped at `47A1h`, and so are NUL bytes.

Speed has a quirk. `S1` to `S4` choose the chip's four hardware speeds. Anything
else lands at `4877h`: the low nibble of the argument, if it is 8 or less, pins
the chip to its fastest setting and stores `nibble - 4` at `[AF47h]` as a software
speed factor. That is how `S5` to `S8` work. But nothing rejects a low nibble
below 5, so a control byte as argument stores a negative factor. The frame
trimmer at `5039h` and `50B1h` subtracts that factor from a frame's length, so
instead of shortening the sound it rewrites the last frame's length to the
3-unit code. The bad value stays until the next `ESC S`.

### Printer definitions as voice commands

`PLAIN.PDF` and `EPSMX80.PDF` in the BraiLab folder aren't Adobe files. They are
printer definitions for MicroStar, the `MS.EXE` editor (magic `PRTDEF`).

`PLAIN.PDF` is empty: no ESC at all, so it can't change the voice in this build.
`EPSMX80.PDF` holds Epson codes stored with length bytes in between, and typing it
walks straight through the parser. `ESC E` and `ESC F` get a length byte as their
argument and ignore it. `ESC S` followed by 00h and later 01h hits the quirk
above, leaving the chip at full speed with a factor of -3. Worked out from the
code; not yet heard.

## Making DOS output reach INT 10h

Windows 98's DOS writes the screen itself. A reader on INT 10h hears only the
tail of each line, so `ver` gives "2]". The fix is one bit in the DOS data
segment, explained in the README section "Making Windows 98's DOS readable".
Neither `DISPLAY.SYS` nor `ANSI.SYS` helps: `ANSI.SYS` tests the same bit.

DOSBox-X can't test any of this, because its console writes bypass the interrupt
table. `TYPE` reaching TALKHUN has to be checked on real hardware.

TALKHUN prints its copyright line before it hooks INT 10h, so the line is never
spoken. To hear it, keep the text in a file and `TYPE` it after loading, then
`SAY /W`, which waits up to a second for speech to start and then for the queue
to drain.

## The timer

- **Windows 98's IO.SYS sits on INT 08h and INT 70h.** Chaining through it at
  10 kHz stopped the BIOS tick and froze anything waiting on it. BRAISPK now
  calls the BIOS entry at `F000:FEA5` directly when something foreign holds the
  vector, after checking that the first byte there looks like a handler.
- **TALKHUN hooks INT 08h above BRAISPK** and saves it as the old vector.
  Re-hooking on top makes the two chain into each other. When the handler above
  chains back, BRAISPK hands that call to the BIOS vector saved at install.
- **Sample clock.** The default is IRQ0 at 1193182/60 = 19886 Hz, two ticks a
  sample, 58 PWM levels. The RTC route (`/8`, 8192 Hz) is the safest, but its
  carrier is audible as a whistle. `/I` is the older 10027 Hz.
- **Windows puts the PIT back.** BRAISPK hooks INT 2Fh: AX=1605h suspends and
  1606h resumes. `pit_check` also latches channel 0 now and then and re-arms it
  if the count is above our divisor, which catches anything else that resets it.
- **Never time anything from PIT channel 0 on these machines.** A resident in any
  mode except `/A` has reprogrammed it. The BIOS tick at `0040:006C` still counts.
- **Reading CMOS register 0Ch races the RTC interrupt.** The handler selects 0Ch
  too, so `cmos_read` and `cmos_write` run with interrupts off. Astra found this.
  Without it, `/S` reported day-long runs and huge lost-tick counts.

## The x87

- **Windows 98's DOS mode leaves CR0.TS set.** Every x87 instruction then traps to
  INT 7, whose handler skips it. Nothing crashes; the doubles are just garbage,
  and the Watcom runtime reports no coprocessor. `CLTS` first thing in `main`.
- **Under a memory manager (V86), `CLTS` isn't allowed**, so it is guarded by
  MSW.PE. BRAISPK checks `sqrt(2)` after this: 8 beeps means the x87 isn't running.
- **Under Jemm and HDPMI, `FSAVE` and `FRSTOR` trap and skip the synth.** Removing
  them isn't enough either: the synth then inherits a dirty x87 stack and computes
  about 6 samples a frame instead of 128, which sounds like ticking every 0.4 s.
  In V86, `fpu_enter` does `FNINIT` and `FLDCW` of the runtime's control word.
- Watcom's inline assembler is 8087: use `fnstsw` with a memory operand, not
  `fnstsw ax`. Each `_asm` with a memory operand needs to sit at the top level of
  its own helper.

## Sound outputs

| Switch | Output | Notes |
|---|---|---|
| none | PC speaker, PWM | a small cone needs drive: default level x8 and a 300 Hz cut |
| `/B` | Sound Blaster direct DAC | best on the 166's Yamaha OPL3-SA; 9943 Hz |
| `/DMA` | Sound Blaster, auto-init 8-bit DMA | 10000 Hz; for SBEMU, a real SB16, or less CPU |
| `/E` | 8-bit DAC on the printer port (Covox type) | verified in DOSBox-X only |
| `/A` | a real PCF8200 on the PC-ROBOT ISA card | handshake works; that card has not yet spoken correctly |

The DSP has to be ready before **every** byte. After command 10h it stays busy for
tens of microseconds, and a byte written while busy is lost, after which the next
command becomes a sample and the sample a command. So `/B` sends the command on
the even tick and the sample on the odd one. A real SB16 goes busy in cycles and
mangles direct-DAC playback; use `/DMA` there.

**SBEMU** (crazii's, for PCI cards under JEMMEX, QPIEMU.DLL and HDPMI32i) works,
with two conditions on a Live!:

- Direct DAC plays at half pitch, because SBEMU estimates the rate from its own
  interrupts. Use `/DMA`, where the time constant sets the rate exactly.
- `/K10000` must be on SBEMU's **first** load. A later change to a resident copy is
  ignored in beta 5, and any other value makes the card play an octave low. Astra
  found this one too.

On that machine: `BRAISPK /DMA /8`.

## Working on a machine with no monitor

Everything can be run by ear. `BRAISPK /L` logs to `BRAISPK.LOG` with raw DOS
calls, and the beeps say how far it got:

| Sound | Meaning |
|---|---|
| chirp, 440 then 660 Hz | installed |
| 1 beep | alive (`/N`) |
| 2 beeps | already resident |
| 3 | INT 61h belongs to something else |
| 4 | log not writable |
| 5 | reboot first (the test ladders) |
| 6 | no card (`/A`) |
| 7 | no DSP |
| 8 | x87 not executing |

`BRAISPK /P` plays a vowel with no TALKHUN involved, and `/K` plays a tone ladder.
`/J`, `/Y` and `/M` on a resident copy retune it live with no reboot. The `/S`
counters are 16-bit and wrap: "samples pushed 4344" over 476 frames was really
about 69,880.

## Build and test traps

- Never cast `MK_FP` to a far function pointer in Watcom: it drops the segment.
  Use a union. This was a hard hang, and it only showed on the branch DOSBox
  never takes.
- `argv[i][1] & 0xDF` to uppercase a switch turns `8` into 18h. `/8` silently
  never matched until 0.31.
- Declare a far pointer to `0040:006C` volatile, or `-os` may hoist the wait loop.
- `_dos_keep` doesn't flush stdio: `fflush(stdout)` first.
- Comparing resident code against your own: the loader relocates the DGROUP word
  in Watcom's interrupt prologue. BRAISPK uses a signature in `isr61` instead.
- DOSBox-X: never pass `-silent`, it mutes the mixer and the capture is zeros.
  Its speaker model turns a DC change into a slow decay, so high-pass at 80 Hz
  before judging envelopes.
- Git Bash rewrites `/V7` into a path: set `MSYS_NO_PATHCONV=1`.
- DOS uppercases redirected log names, so match them case-insensitively.

## Still open

- The `/J` help text says 3600 Hz is the default. The default is 4000 Hz (`/J6`).
- `/Y` and `/M` are still waiting for an ear verdict; defaults are `/Y0` and `/M3`.
- Voiced and noise amplitude may need separate envelopes.
- `/8` synthesises at 8192 Hz, so high formants are clamped. A 10 kHz core with a
  resampler would fix that.
- A real BraiLab PC is the reference these filters have been waiting for, above
  all for the rising edge in the sibilants.
