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
| `patch_talkhun.py` | makes `TALKHUNS.COM` from the archive's `TALKHUN.COM` |
| `say.c` | `SAY.EXE`: feeds text and configuration to TALKHUN over INT 14h |
| `pwmtest.c` | plays two tones through the speaker; proves the output stage alone |
| `build.sh` | builds everything with Open Watcom (portable snapshot in `C:\WATCOM`) |
| `dosbox_run.py` | runs the whole chain headless under DOSBox-X and captures WAVs |

## How TALKHUN is redirected

Tracing a spoken sentence under the Unicorn DOS host showed that every printer
port access in the 64 KB of v4 goes through two places: the 2-wire primitive at
`0x537f` and the ready poll at `0x5308`. The patcher rewrites 11 bytes:

    537f  and ah,3 / mov al,ah / mov dx,[base] / out ...   ->  int 61h / ret
    5314  mov dx,[base] / inc dx / in al,dx                 ->  mov ah,0FFh / nop / nop / int 61h
    532a  jb 5319                                           ->  jb 5318

It refuses any file whose bytes at those addresses differ, so a different
TALKHUN build is never silently corrupted. The archive copy is not modified.

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
- **Output**: the RTC's periodic interrupt (IRQ8) at 8192 Hz; each tick writes
  one sample as a PIT channel-2 mode-0 count, 144 levels. Nothing else in the
  machine is touched: not PIT channel 0, not the BIOS tick, not IO.SYS's or
  TALKHUN's INT 08 hooks. The synth, the low-pass and the frame lengths are
  designed for the rate in use, so the chip model is unchanged apart from the
  4 kHz ceiling. `/I` selects the older route instead: IRQ0 at 1193182/119 =
  10027 Hz with the old INT 08 chained every 551st tick, the re-hook done inside
  the timer handler within one tick of anyone hooking above us, and no DOS calls
  in resident code. That route worked under DOSBox-X and stopped the BIOS clock
  on a real Pentium 166 running Windows 98's DOS, where IO.SYS sits on INT 08;
  the RTC route exists because of that log.
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

Under DOSBox-X: `python dosbox_run.py "Jó napot kívánok."` runs the chain and
leaves a WAV per sentence in the output directory. Never pass `-silent` to
DOSBox-X; it mutes the mixer and the capture is zeros.

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
- Not yet: the Pentium 166's real cone speaker, and a game session.
