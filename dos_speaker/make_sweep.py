# -*- coding: utf-8 -*-
"""Build the chip sweep: BRAIPLAY files that make a real PCF8200 show what every code does.

    python make_sweep.py OUTDIR [NOTESDIR]

writes CHIP1.EXE, CHIP2.EXE and CHIP3.EXE to OUTDIR and, to NOTESDIR (OUTDIR if not given), for
each of them a manifest (every hold: what was sent, and when, in the chip's own nominal time)
and a rendering of the same frames by the emulation as it stands, made before the recording.

No speech engine is involved, apart from the spoken section names (TALKHUN, as in
make_braiplay.py).  The frames are written here, a field at a time:

  CHIP1  levels and sources: the amplitude codes, voiced and noise; the fifteen DAC factors;
         both sources through a tract with every formant damped; the start-pitch byte; every
         pitch-increment code, at each frame duration and speed; pitch run past both ends.
  CHIP2  the resonators, one at a time with the other four damped: every frequency code and
         every bandwidth code, on noise and on a low voice, with the male table and the female.
  CHIP3  time: the frame durations at the four speeds; one field alternating between two values
         at each duration, to show how the chip gets from one frame to the next; voiced against
         noise; starting and stopping at full level.

Every unit starts with a mark (three loud frames between silences) to find it by, and holds
are a whole number of frames, so a recording is cut from the manifest, not by ear.

What is sent stays inside what the chip's documents allow: no DAC byte F0h, and no DAC factor
above the 3.5 that TALKHUN uses all the time.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'talkhun_emu'))
import make_braiplay as mb                                   # noqa: E402

FS_MS = (12.8, 8.8, 10.4, 17.6)         # command bits FS1 FS0 -> a standard frame, in ms
FD_MULT = (1, 2, 3, 5)                  # frame-duration code -> standard frames
MALE, FEMALE = 0x80, 0x90
#: DAC-control bytes in rising order of their factor: 0, 0.25, 0.5, ... 3.25, 3.5.
DAC = (0x00, 0x80, 0x40, 0xC0, 0x20, 0xA0, 0x60, 0xE0, 0x10, 0x90, 0x50, 0xD0, 0x30, 0xB0, 0x70)
DAC_FACTOR = (0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.2, 2.5, 2.75, 3.0, 3.25, 3.5)
#: The reference vowel, near TALKHUN's a (F1 612, F2 974 Hz in the male table).
REF_F, REF_B = (21, 13, 4, 3, 0), (3, 3, 2, 2, 2)
#: Every formant at bandwidth code 0 (3000 Hz): as near to no filter as the chip gets.
OFF_F, OFF_B = (19, 21, 4, 4, 1), (0, 0, 0, 0, 0)
NOISE = 16                              # the pitch-increment code that selects the noise source
WIDTH = ((8, 8, 4, 4, 4), (32, 32, 8, 8, 2))        # codes per bandwidth field, per frequency field


def frame(F, B, pi=0, am=0, fd=0):
    """The five bytes of one frame."""
    f1, f2, f3, f4, f5 = F
    b1, b2, b3, b4, b5 = B
    assert 0 <= f1 < 32 and 0 <= f2 < 32 and 0 <= f3 < 8 and 0 <= f4 < 8 and 0 <= f5 < 2
    assert 0 <= b1 < 8 and 0 <= b2 < 8 and 0 <= b3 < 4 and 0 <= b4 < 4 and 0 <= b5 < 4
    assert 0 <= pi < 32 and 0 <= am < 16 and 0 <= fd < 4
    return bytes([b1 << 5 | f1, f5 << 7 | b5 << 5 | pi, (fd >> 1) << 7 | f3 << 4 | am,
                  (fd & 1) << 7 | b3 << 5 | f2, b4 << 6 | f4 << 3 | b2])


class Unit:
    """One utterance for the chip: start bytes, frames, STOP.  Keeps the time of everything in it."""

    def __init__(self, name, pitch=46, cmd=MALE, vol=0x70, mark=True):
        self.name, self.pitch, self.cmd, self.vol = name, pitch, cmd, vol
        self.frames, self.events, self.std = [], [], 0
        if mark:
            self.add(REF_F, REF_B, am=0, n=2)
            self.add(REF_F, REF_B, am=12, n=3, event='mark')
            self.add(REF_F, REF_B, am=0, n=8)

    def add(self, F, B, pi=0, am=0, fd=0, n=1, event=None, **notes):
        t0 = self.std
        self.frames += [frame(F, B, pi, am, fd)] * n
        self.std += FD_MULT[fd] * n
        if event:
            self.events.append(dict(notes, event=event, std0=t0, std1=self.std,
                                    F=list(F), B=list(B), pi=pi, am=am, fd=fd))

    def hold(self, event, seconds, F, B, pi=0, am=11, **notes):
        """One frame of a single standard frame, to get there quickly, then long ones."""
        t0 = self.std
        n = max(1, int(round((seconds * 1000.0 / FS_MS[self.cmd & 3] - 1) / 5.0)))
        self.add(F, B, pi, am, fd=0)
        self.add(F, B, pi, am, fd=3, n=n)
        self.events.append(dict(notes, event=event, std0=t0, std1=self.std, F=list(F), B=list(B), pi=pi, am=am))

    def quiet(self, n=4):
        self.add(REF_F, REF_B, am=0, n=n)

    def seconds(self):
        return self.std * FS_MS[self.cmd & 3] / 1000.0

    def record(self):
        self.quiet(3)
        if len(self.frames) > mb.MAX_FRAMES:
            raise SystemExit('unit %s has %d frames' % (self.name, len(self.frames)))
        return ('U', self.vol, self.pitch, self.cmd, True, list(self.frames))


def solo(i, fcode, bcode):
    """Formant i alone: the other four at bandwidth code 0."""
    F, B = list(OFF_F), [0, 0, 0, 0, 0]
    F[i], B[i] = fcode, bcode
    return tuple(F), tuple(B)


# ------------------------------------------------------------------------------------ CHIP1
def chip1():
    out = ['Csip egy.']
    u = Unit('reference')
    u.hold('ref', 1.0, REF_F, REF_B)
    out += [u, 'Hangerő.']
    for name, pi in (('am-voiced', 0), ('am-noise', NOISE)):
        u = Unit(name)
        for am in range(1, 16):
            u.hold('am', 0.45, REF_F, REF_B, pi=pi, am=am)
        out.append(u)
    out.append('Erősítés.')
    for byte, factor in zip(DAC, DAC_FACTOR):
        u = Unit('dac-%02X' % byte, vol=byte)
        u.hold('dac', 0.4, REF_F, REF_B, am=15, factor=factor)
        u.hold('dac', 0.4, REF_F, REF_B, am=11, factor=factor)
        u.hold('dac', 0.4, REF_F, REF_B, pi=NOISE, am=13, factor=factor)
        out.append(u)
    out.append('Források.')
    u = Unit('flat-noise')
    u.hold('flat', 2.0, OFF_F, OFF_B, pi=NOISE, am=13)
    u.hold('flat', 1.0, (0, 0, 0, 0, 0), OFF_B, pi=NOISE, am=13, what='all F codes lowest')
    u.hold('flat', 1.0, (31, 31, 7, 7, 1), OFF_B, pi=NOISE, am=13, what='all F codes highest')
    u.hold('flat', 0.6, OFF_F, OFF_B, pi=NOISE, am=13)
    out.append(u)
    u = Unit('flat-noise-female', cmd=FEMALE)
    u.hold('flat', 2.0, OFF_F, OFF_B, pi=NOISE, am=13)
    out.append(u)
    for byte in (16, 24, 33, 46, 62, 82, 110, 150, 200, 255):
        u = Unit('pitch-%d' % byte, pitch=byte)
        u.hold('flat', 0.8, OFF_F, OFF_B, am=13, hz=byte / 0.4096)
        u.hold('ref', 0.5, REF_F, REF_B, hz=byte / 0.4096)
        out.append(u)
    u = Unit('flat-voiced-female', cmd=FEMALE)
    u.hold('flat', 0.8, OFF_F, OFF_B, am=13)
    u.hold('ref', 0.5, REF_F, REF_B)
    out += [u, 'Dallam.']
    from pcf8200_tables import PI as PI_HZ
    for first in (1, 6, 11):
        u = Unit('pi-%d-%d' % (first, first + 4), pitch=82)
        u.hold('level', 0.25, REF_F, REF_B)
        for code in range(first, first + 5):
            n = min(40, int(140 / PI_HZ[code]))
            u.add(REF_F, REF_B, pi=code, am=11, n=n, event='ramp', code=code, frames=n)
            u.hold('level', 0.2, REF_F, REF_B)
            u.add(REF_F, REF_B, pi=32 - code, am=11, n=n, event='ramp', code=32 - code, frames=n)
            u.hold('level', 0.2, REF_F, REF_B)
        out.append(u)
    for fs in range(4):                 # the same step at each frame duration, at each speed
        u = Unit('pi-fd-fs%d' % fs, pitch=82, cmd=MALE | fs)
        u.hold('level', 0.25, REF_F, REF_B)
        for fd in range(4):
            u.add(REF_F, REF_B, pi=5, am=11, fd=fd, n=8, event='ramp', code=5, frames=8)
            u.hold('level', 0.2, REF_F, REF_B)
            u.add(REF_F, REF_B, pi=27, am=11, fd=fd, n=8, event='ramp', code=27, frames=8)
            u.hold('level', 0.2, REF_F, REF_B)
        out.append(u)
    out.append('Határok.')
    u = Unit('limit-fast', pitch=82)
    u.hold('level', 0.3, REF_F, REF_B)
    u.add(REF_F, REF_B, pi=15, am=11, n=40, event='ramp', code=15, frames=40)
    u.hold('level', 0.3, REF_F, REF_B)
    u.add(REF_F, REF_B, pi=17, am=11, n=80, event='ramp', code=17, frames=80)
    u.hold('level', 0.3, REF_F, REF_B)
    out.append(u)
    u = Unit('limit-slow', pitch=82)
    u.add(REF_F, REF_B, pi=5, am=11, n=160, event='ramp', code=5, frames=160)
    u.hold('level', 0.3, REF_F, REF_B)
    u.add(REF_F, REF_B, pi=27, am=11, n=320, event='ramp', code=27, frames=320)
    u.hold('level', 0.3, REF_F, REF_B)
    out.append(u)
    u = Unit('pitch-through-noise', pitch=82)
    u.hold('level', 0.4, REF_F, REF_B)
    u.add(REF_F, REF_B, pi=9, am=11, n=10, event='ramp', code=9, frames=10)
    u.hold('level', 0.3, REF_F, REF_B)
    u.hold('noise', 0.4, REF_F, REF_B, pi=NOISE, am=11)
    u.hold('level', 0.4, REF_F, REF_B)
    out.append(u)
    out.append('Mély hangok.')          # last: nobody knows what the chip does with these
    for byte in (12, 8, 4, 2, 1, 0):
        u = Unit('pitch-%d' % byte, pitch=byte)
        u.hold('ref', 0.6, REF_F, REF_B, hz=byte / 0.4096)
        out.append(u)
    u = Unit('reference-end')
    u.hold('ref', 1.0, REF_F, REF_B)
    out += [u, 'Vége.']
    return out


# ------------------------------------------------------------------------------------ CHIP2
MID_B = (3, 3, 2, 2, 2)
B_AT_F = ((10, 22), (8, 24), (2, 5), (2, 5), (0, 1))


def am_for(i, bcode):
    """Quieter for the narrow bandwidths, whose resonance is high."""
    last = WIDTH[0][i] - 1
    return 12 if bcode * 2 <= last else (10 if bcode < last - 1 or last == 3 and bcode == 2 else 8)


def chip2():
    out = ['Csip kettő.']
    for table, cmd, nf, word in (('male', MALE, 5, 'Férfi.'), ('female', FEMALE, 4, 'Női.')):
        out.append(word)
        for i in range(nf):
            u = Unit('%s-F%d-ladder' % (table, i + 1), pitch=33, cmd=cmd)
            for code in range(WIDTH[1][i]):
                F, B = solo(i, code, MID_B[i])
                u.hold('solo', 0.5, F, B, pi=NOISE, am=12, formant=i + 1, fcode=code, bcode=MID_B[i], source='noise')
            for code in range(WIDTH[1][i]):
                F, B = solo(i, code, MID_B[i])
                u.hold('solo', 0.3, F, B, am=11, formant=i + 1, fcode=code, bcode=MID_B[i], source='voiced')
            out.append(u)
        for i in range(nf):
            u = Unit('%s-B%d-ladder' % (table, i + 1), pitch=33, cmd=cmd)
            for fcode in B_AT_F[i]:
                for bcode in range(WIDTH[0][i]):
                    F, B = solo(i, fcode, bcode)
                    am = am_for(i, bcode)
                    u.hold('solo', 0.6, F, B, pi=NOISE, am=am, formant=i + 1, fcode=fcode, bcode=bcode, source='noise')
                    u.hold('solo', 0.3, F, B, am=am - 1, formant=i + 1, fcode=fcode, bcode=bcode, source='voiced')
            out.append(u)
    # the female table has no fifth formant: do its two fields do anything there?
    u = Unit('female-F5-fields', pitch=33, cmd=FEMALE)
    for f5, b5 in ((0, 0), (1, 0), (0, 3), (1, 3)):
        F, B = (19, 21, 4, 4, f5), (0, 0, 0, 0, b5)
        u.hold('f5', 0.6, F, B, pi=NOISE, am=12, source='noise')
        u.hold('f5', 0.3, F, B, am=11, source='voiced')
    out += [u, 'Vége.']
    return out


# ------------------------------------------------------------------------------------ CHIP3
def alternate(u, a, b, what, reps=3, each=3):
    """a a a b b b ..., at every frame duration; a and b are keyword sets for Unit.add."""
    for fd in range(4):
        for _ in range(reps):
            for side, kw in (('a', a), ('b', b)):
                u.add(fd=fd, n=each, event='alt', what=what, side=side, **kw)
        u.add(REF_F, REF_B, am=0, n=6)


def chip3():
    out = ['Csip három.', 'Időzítés.']
    for fs in range(4):
        u = Unit('clicks-fs%d' % fs, cmd=MALE | fs)
        for fd in range(4):
            for _ in range(8):
                u.add(REF_F, REF_B, am=13, fd=fd, event='click')
                u.add(REF_F, REF_B, am=0, fd=fd)
            u.quiet(4)
        out.append(u)
    out.append('Átmenetek.')
    ref = dict(F=REF_F, B=REF_B)
    patterns = [
        ('am-13-7', dict(ref, am=13), dict(ref, am=7)),
        ('am-13-0', dict(ref, am=13), dict(ref, am=0)),
        ('f1-8-26', dict(F=(8, 13, 4, 3, 0), B=(4, 3, 2, 2, 2), am=11), dict(F=(26, 13, 4, 3, 0), B=(4, 3, 2, 2, 2), am=11)),
        ('f2-4-28', dict(F=(12, 4, 4, 3, 0), B=REF_B, am=11), dict(F=(12, 28, 4, 3, 0), B=REF_B, am=11)),
        ('f3-0-7', dict(F=(21, 13, 0, 3, 0), B=REF_B, am=11), dict(F=(21, 13, 7, 3, 0), B=REF_B, am=11)),
        ('f5-0-1', dict(F=(21, 13, 4, 3, 0), B=(3, 3, 2, 2, 3), am=11), dict(F=(21, 13, 4, 3, 1), B=(3, 3, 2, 2, 3), am=11)),
        ('b1-1-6', dict(F=REF_F, B=(1, 3, 2, 2, 2), am=10), dict(F=REF_F, B=(6, 3, 2, 2, 2), am=10)),
        ('voiced-noise', dict(ref, am=11), dict(ref, am=11, pi=NOISE)),
        ('vowel-s', dict(ref, am=12), dict(F=(12, 24, 6, 6, 1), B=(1, 2, 2, 2, 2), am=10, pi=NOISE)),
    ]
    for name, a, b in patterns:
        u = Unit('alt-' + name)
        alternate(u, a, b, name)
        out.append(u)
    for name, a, b in (patterns[0], patterns[7]):       # and at the slowest speed
        u = Unit('alt-%s-fs3' % name, cmd=MALE | 3)
        alternate(u, a, b, name)
        out.append(u)
    out.append('Indulás és megállás.')
    for name, kw, n, fd in (('start-stop-voiced', dict(ref, am=13), 20, 0), ('start-stop-noise', dict(ref, am=13, pi=NOISE), 20, 0),
                            ('one-long-frame', dict(ref, am=13), 1, 3), ('one-short-frame', dict(ref, am=13), 1, 0)):
        u = Unit(name, mark=False)
        u.add(fd=fd, n=n, event='burst', **kw)
        u.record = (lambda u=u: ('U', u.vol, u.pitch, u.cmd, True, list(u.frames)))     # no quiet tail: STOP at full level
        out.append(u)
    out.append('Vége.')
    return out


# ------------------------------------------------------------------------------------ files
def render(records, path, rate=44100):
    """The emulation's version of the same records, for comparing with the recording later."""
    import hashlib
    import wave
    import numpy as np
    import chip_synth
    parts = []
    for r in records:
        if r[0] == 'P':
            parts.append(np.zeros(int(rate * r[1] / 1000.0)))
            continue
        _, vol, pitch, cmd, stopped, frames = r
        seq = [('pitch', pitch), ('ctrl', [0, cmd])] + [('frame', list(f)) for f in frames]
        parts.append(chip_synth.render_chip_fast(seq, out_rate=rate, time_scale=FS_MS[cmd & 3] / 12.8))
    y = np.concatenate(parts)
    pcm = np.clip(y / (np.abs(y).max() + 1e-9) * 0.8 * 32767, -32767, 32767).astype('<i2')
    w = wave.open(path, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes()); w.close()
    return hashlib.sha256(pcm.tobytes()).hexdigest()


def build(name, items, labels, outdir, notesdir):
    records, manifest, t = [], [], 0.3
    records.append(('P', 300))
    for it in items:
        if isinstance(it, str):
            spoken = labels[it]
            start = t
            for r in spoken:
                t += sum(FS_MS[r[3] & 3] * FD_MULT[((f[2] >> 7) << 1) | (f[3] >> 7)] for f in r[5]) / 1000.0
            records += spoken + [('P', 350)]
            manifest.append({'label': it, 'start_s': round(start, 3)})
            t += 0.35
        else:
            ms = FS_MS[it.cmd & 3]
            rec = it.record()
            manifest.append({'unit': it.name, 'start_s': round(t, 3), 'pitch': it.pitch, 'cmd': '%02X' % it.cmd,
                             'dac': '%02X' % it.vol, 'frame_ms': ms, 'frames': len(rec[5]),
                             'events': [dict(e, t0=round(e['std0'] * ms / 1000.0, 4), t1=round(e['std1'] * ms / 1000.0, 4))
                                        for e in it.events]})
            records += [rec, ('P', 200)]
            t += it.seconds() + 0.2
    mb.build(records, os.path.join(outdir, name + '.EXE'))
    digest = render(records, os.path.join(notesdir, name.lower() + '-emulation.wav'))
    with open(os.path.join(notesdir, name.lower() + '-manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'file': name + '.EXE', 'nominal_seconds': round(t, 1), 'emulation_sha256': digest,
                   'note': 'times are nominal chip time from the start of the file; unit starts drift by a few ms each, '
                           'event times inside a unit (t0, t1, from its first frame) do not',
                   'items': manifest}, f, ensure_ascii=False, indent=1)
    holds = sum(len(m.get('events', ())) for m in manifest)
    print('%s: about %d min %02d s, %d units, %d holds and ramps' % (
        name, t // 60, t % 60, sum(1 for m in manifest if 'unit' in m), holds))


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    outdir = os.path.abspath(sys.argv[1])
    notesdir = os.path.abspath(sys.argv[-1])
    os.makedirs(notesdir, exist_ok=True)
    files = (('CHIP1', chip1()), ('CHIP2', chip2()), ('CHIP3', chip3()))
    words = sorted({it for _, items in files for it in items if isinstance(it, str)})
    program = [('set', b'\x1bP*\x1bS4\x1bF0\x1bR0\x1bC0\x1bE1\x1bK1')]
    for w in words:
        program += [('say', w), ('pause', 1)]
    work = os.path.join(HERE, '_braiplay_work')
    os.makedirs(work, exist_ok=True)
    labels, cur, i = {}, [], 0
    for r in mb.capture(program, work):
        if r[0] == 'P':
            labels[words[i]] = cur
            cur, i = [], i + 1
        else:
            cur.append(r)
    for name, items in files:
        build(name, items, labels, outdir, notesdir)


if __name__ == '__main__':
    main()
