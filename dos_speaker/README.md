# BRAISPK — a BraiLab on the PC speaker

A 16-bit DOS TSR that stands in for the BraiLab PC speech adapter. TALKHUN, the
1991–2003 BraiLab screen reader, thinks it is clocking frames into a PCF8200 on
the printer port; in fact it is talking to a few kilobytes of resident code that
synthesises the chip and plays the result through the PC's own cone speaker.
No adapter, no sound card, no memory manager. A Pentium 166 has cycles to spare.

The synth is the same model as the NVDA add-on's `chip_synth.py`: the PCF8200's
five-formant cascade at its 10 kHz internal rate, the chip's own quantisation
ROM, the ear-matched source tilt, low-pass, high-pass and soft knee. The one
deliberate difference is the voiced source: a PolyBLEP sawtooth instead of the
per-harmonic sum, because the sum does not fit a 166 in real time.

## Files

| file | what |
|---|---|
| `braispk.c` | the TSR: INT 61h adapter API, wire decoder, synth, 10 kHz PWM timer |
| `patch_talkhun.py` | makes `TALKHUNS.COM`: fetches `TALKHUN.COM` from archive.org, or `--from FILE` for your own copy |
| `say.c` | `SAY.EXE`: feeds text and configuration to TALKHUN over INT 14h |
| `pwmtest.c` | plays two tones through the speaker; proves the output stage alone |
| `build.sh` | builds everything with Open Watcom (portable snapshot in `C:\WATCOM`) |
| `dosbox_run.py` | runs the whole chain headless under DOSBox-X and captures WAVs |
| `NOTES.md` | what real machines taught us: TALKHUN's INT 10h path, timers, the x87, sound cards |

## How TALKHUN is redirected

Tracing a spoken sentence under the Unicorn DOS host showed that every printer
port access in the 64 KB of v4 goes through two places: the 2-wire primitive at
`0x537f` and the ready poll at `0x5308`. The patcher rewrites 11 bytes:

    537f  and ah,3 / mov al,ah / mov dx,[base] / out ...   ->  int 61h / ret
    5314  mov dx,[base] / inc dx / in al,dx                 ->  mov ah,0FFh / nop / nop / int 61h
    532a  jb 5319                                           ->  jb 5318

It takes only the exact 64,941-byte file of 20 June 2000, checked by SHA-256,
so a different TALKHUN build is never silently corrupted. The original is not
modified. Run it on a modern PC, then copy `TALKHUNS.COM` to the DOS machine.

## The adapter, as the TSR models it

- **Wire**: I2C-style framing on data bits 0 (SDA) and 1 (SCL): START when data
  falls while the clock is high, STOP when it rises; bits sampled on the rising
  edge, eight MSB-first plus an ack. Five bytes are a speech frame, two a
  control write, one a start-sequence single (settings nibble, then pitch).
- **Status**: `30h` busy, `20h` ready. Bit 5 must always be set; TALKHUN reads it
  clear as a broken adapter and goes mute.
- **Busy**: while more than ~100 ms of audio is queued (TALKHUN's poll gives up
  after four BIOS ticks); at rest until the first transaction of an utterance
  (that is what lets the start sequence carrying the pitch go out at all);
  back at rest after a STOP control. This is the pacing the JATEKOK games relied
  on: text does not advance until the utterance has been heard.
- **Output**: by default IRQ0 at 1193182/60 = 19886 Hz, two ticks a sample; each
  tick writes a PIT channel-2 mode-0 count, 58 levels. The carrier sits above
  hearing, and when IO.SYS holds INT 08 the BIOS entry is called directly. `/8`
  selects the RTC's periodic interrupt (IRQ8) at 8192 Hz instead, 144 levels:
  nothing else in the machine is touched, but the carrier is an audible whistle,
  and the synth, the low-pass and the frame lengths are designed for that rate
  with a 4 kHz ceiling. `/I` is the older IRQ0 route at 1193182/119 = 10027 Hz.
  There are no DOS calls in resident code. `/B`, `/DMA`, `/E` and `/A` send the
  samples elsewhere: see [NOTES.md](NOTES.md).
- **Speaker ownership**: channel 2 and the gate are taken only while there is
  audio to play. The line is eased from the off level to the idle level over
  12 ms at the first sample, and given back (eased out, channel 2 returned to
  square-wave mode, gate off) as soon as an utterance's STOP has drained, or
  50 ms into a mid-utterance gap. Between utterances the games' own beeps find
  the timer as they left it, and a real cone sits silent rather than carrying a
  10 kHz tone.

## Use

    BRAISPK              install (BRAISPK /C for chip frame timing, see below)
    TALKHUNS 1           the patched screen reader, on "LPT1"
    SAY /C               the configuration HUN.BAT used to send with COPY ... COM4
    SAY Jó napot.        speak
    SAY /F FILE.TXT      speak a file, line by line
    SAY /T               self-test: beep, a sentence, then a beep 110 ms after it
    BRAISPK /P           self-test: a vowel through the synth, no TALKHUN needed
    BRAISPK /L           install with breadcrumbs in BRAISPK.LOG, for a machine with no monitor
    BRAISPK /I           clock the samples from IRQ0 at 10027 Hz instead of the RTC
    BRAISPK /S           counters: frames, controls, pitches, queued samples, underruns, overruns
    BRAISPK /D           what the resident check sees (vector, handler bytes, identify)
    BRAISPK /U           unload (refused while TALKHUNS is loaded: reboot instead)

What you should hear on a machine with no monitor: BRAISPK plays a two-tone
chirp (440 then 660 Hz) the moment it goes resident; two short beeps mean it
already was, three mean something else owns INT 61h and it did not install.
Then TALKHUNS loads, SAY /C's "configured" is spoken, and `SAY Kesz.` says
Kész. No chirp: BRAISPK. Chirp but no speech: TALKHUNS or SAY. Speech but
wrong: the synth.

`/C` honours the chip's FS bits: TALKHUN's default speed (ESC S6) sets FS=1,
which on real silicon means 8.8 ms frames rather than 12.8. The emulator the
NVDA voice was tuned on ignores FS, so the default here does too; the switch is
for the ear to decide.

## Making Windows 98's DOS readable (0.26)

DOS 7.1 writes the screen directly. Its console routine in IO.SYS tests bit 4
of a byte at offset 86h in the DOS data segment (the segment INT 21h AH=52h
returns) and, if set, stores the character at B800h itself; only control
characters and the last character of each write take INT 10h AH=0Eh. A screen
reader hooking INT 10h hears the tail of every line and nothing else. The
write routine arms bit 4 at the start of each write unless bit 3 is set, and
nothing in IO.SYS ever sets bit 3. BRAISPK sets it at install and restores it
at unload; DOS then goes through the BIOS for every character, the DOS 6 way,
and TALKHUN reads `ver`, `dir` and the games' prompts. ANSI.SYS consults the
same bit. `/T` leaves DOS alone. All of this was read out of the machine's own
IO.SYS and ANSI.SYS with capstone.

## Through a Sound Blaster DAC instead (`/B`, 0.24)

`BRAISPK /B` sends the same samples to a Sound Blaster-compatible DAC at 220h
(`/B240` for another address; without one the `BLASTER` variable's `A` part
is used). Direct-DAC mode, DSP command 10h with one byte per sample, paced by
the same IRQ0 tick as the speaker path: no DMA, no sound-card IRQ, nothing else
in the machine touched. The DSP's write buffer has to be free before *every*
byte, command and sample alike, and after a direct-DAC command it stays busy for
tens of microseconds (the mode's documented 23 kHz ceiling); a byte written
while it is busy is lost, after which the next command byte becomes the sample
and the sample a command. So on the 19.9 kHz clock the command goes out on the
even tick and the sample on the odd one: 9943 samples a second, the synth's own
rate, no spinning. Defaults in `/B` mode: full range, level x2; the mixer's
master and voice are raised to full and the SB Pro output filter bypassed, and
put back at unload. The Yamaha OPL3-SA on the target machine is Sound Blaster
Pro class, and its DSP answered every port scan so far (all after a restart
from Windows into DOS mode; a straight boot is untested). A real SB16's
DSP goes busy in cycles and mangles direct-DAC playback (DOSBox-X's `sb16`
model shows it); DMA mode would be the answer there.

Under DOSBox-X: `python dosbox_run.py "Jó napot kívánok."` runs the chain and
leaves a WAV per sentence in the output directory; `--sb` does the same on an
emulated SB Pro (`--nospk` turns the emulated speaker off, so the capture can
only be the DAC). Never pass `-silent` to DOSBox-X; it mutes the mixer and the
capture is zeros.

On the real machine: copy `BRAISPK.EXE`, `TALKHUNS.COM`, `SAY.EXE` next to the
JATEKOK programs, boot to real DOS, run the three lines above. The games'
PC-speaker jingles run off CPU-timed loops and are unaffected; `CPUCACHE.COM`
from the same archive slows the machine to 486 pace for those. Test BRAISPK
alone first and add CPUCACHE afterwards: with the cache off a 166 is a much
slower machine, and the underrun counter in `/S` says whether the synth still
kept up.

## Verified

- DOSBox-X renders the one-shot PWM: 440/880 Hz test tones land within 1%.
- The full chain speaks two sentences headless, counters matching the Unicorn
  model (one pitch start per intonation unit, STOP after each), and unloads.
- `SAY /T` under DOSBox-X: a plain mode-3 beep, the sentence, and a beep 110 ms
  after the text come out as two clean 1 kHz tones around the speech, the tail
  is silent, and no underruns are counted.
- On a real Pentium 166: speech through the cone speaker and, as the daily
  setup, through the Yamaha DAC with `/B`. DOS output reads aloud.
- On a real Dell with an SB Live! under SBEMU: clear speech with `/DMA /8`.
- Not yet: a full game session.
