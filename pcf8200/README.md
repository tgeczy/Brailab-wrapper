# pcf8200 — a software Philips PCF8200 in Python

A from-scratch, pure-**numpy** software model of the **Philips PCF8200** formant
speech chip — the synthesiser behind the Hungarian **BraiLab** and the Spanish
**Ciber232** talkers for the blind (early 1990s). Matched by ear and by
measurement to real silicon.

It wraps the chip the way this project wraps a vendor DLL: you drive it with the
chip's *own command stream* (5-byte frames + control writes), or phonetically
from formant frequencies. It speaks whatever formants you give it — Hungarian,
Spanish, **Polish**, a sine sweep, anything.

Only dependency: **numpy**. (scipy is used *only* if you ask for a non-default
output low-pass; the default path is scipy-free.)

```
pip install numpy
# then drop the pcf8200/ folder next to your script, or add it to sys.path
import pcf8200
```

---

## 1. Drive the chip's command protocol (authentic)

This is the exact wire format a BraiLab/Ciber board clocks into the PCF8200.

```python
from pcf8200 import PCF8200, nearest_code, tables

chip = PCF8200(voice="male")     # "male" (5 formants) or "female" (4)
chip.pitch_hz(110)               # start pitch (or chip.pitch(byte))

# a steady /a/: pick formant codes from the chip's tables
F1 = nearest_code(700,  tables.MALE_F[0])   # -> code 23 = 727 Hz
F2 = nearest_code(1220, tables.MALE_F[1])
F3 = nearest_code(2600, tables.MALE_F[2])
for _ in range(8):
    chip.frame_codes(F1=F1, F2=F2, F3=F3, F5=1, AM=13, PI=2, FD=2)
chip.stop()
chip.to_wav("a.wav")             # 16-bit mono WAV
```

You can also clock in **raw device bytes** you captured from real hardware:

```python
chip.frame(bytes([0xB7, 0x02, 0x4D, 0x0D, 0x24]))   # one 5-byte frame
```

**Frame fields** (`encode_frame` / `decode_frame`):
`F1..F5` formant codes, `B1..B5` bandwidth codes, `AM` amplitude (0–15),
`PI` pitch increment (16 = unvoiced/noise), `FD` frame-duration multiplier (0–3).
The 40-bit layout and 2-byte control write are the public Philips datasheet;
`tables.py` states the chip's factual code→Hz expansion.

```python
from pcf8200 import decode_frame, encode_frame
f = encode_frame(F1=22, F2=13, F3=4, AM=13, PI=2, FD=2)
decode_frame(f)   # -> {'F1':22,'F2':13,...}
```

## 2. Drive it phonetically (easiest for a new language)

Skip the byte protocol; describe sounds by their **formant frequencies (Hz)**.

```python
from pcf8200 import Chip, Voice, VOWELS

v = Voice(pitch=120)
for ph in "aeiou":
    v.vowel(VOWELS[ph], dur=0.26)   # F1,F2,F3 in Hz; Voice glides between them
    v.silence(0.05)
Chip().to_wav("vowels.wav", Chip().render(v))
```

`Voice` methods (all chainable): `.vowel(formants_hz, dur, amp, pitch)`,
`.fricative(formants, bw, dur, amp)` (noise-excited), `.silence(dur)`.

## 3. Make it speak your language

A language is just a **dict of formant frequencies** you supply. A starter Polish
set ships in `pcf8200.POLISH` (extend/refine against native recordings — Praat's
LPC formant tracker is your friend):

```python
from pcf8200 import Chip, Voice, POLISH, FRICATIVES

v = Voice(pitch=115)
v.vowel(POLISH["o"]).fricative(**FRICATIVES["sz"]).vowel(POLISH["a"])   # "o-sz-a"
Chip().to_wav("polish.wav", Chip().render(v))
```

To go from text to speech you add the two things this library deliberately leaves
to you: a **grapheme→phoneme** step for your language, and formant values for its
sounds. The chip renders whatever you feed it.

## How it works

Periodic-pulse (band-limited sawtooth) or noise excitation → a gentle glottal
tilt → **five cascaded resonators** (`y(n)=x(n)+B·F·y(n-1)−B²·y(n-2)`, with
`F=2cos(2π·fc/fs)`, `B=exp(−π·bw/fs)`) → an output low-pass. Internal rate 10 kHz;
ask for any output rate and it band-limit-resamples.

## Credits & license

The software model, and this library, are released under the MIT license (see
LICENSE). The PCF8200 is Philips silicon; its byte protocol is public
(datasheet). The code→Hz quantization tables in `tables.py` state factual chip
behaviour. Built as part of the BraiLab / Ciber232 preservation work.
