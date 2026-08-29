# -*- coding: utf-8 -*-
"""Voice -- build formant tracks phonetically, without touching the byte protocol.

This is the friendly layer on top of the chip: describe a sound as a sequence of
segments (vowels by their formant frequencies, fricatives as noise, silences) and
Voice assembles smoothly-interpolated formant / amplitude / pitch tracks that a
Chip renders.  It is language-agnostic -- feed it Polish formants and you get
Polish vowels.

    from pcf8200 import Chip, Voice, VOWELS
    v = Voice(pitch=115)
    v.vowel(VOWELS["a"]).vowel(VOWELS["i"]).fricative().vowel(VOWELS["o"])
    Chip().to_wav("demo.wav", Chip().render(v))
"""
import numpy as np
from .chip import RATE

# high formants F4/F5 are fairly fixed for a male tract; used to pad short specs
_HI = [3300.0, 3750.0]
_DEFAULT_BW = [60.0, 90.0, 120.0, 150.0, 200.0]


class Voice:
    def __init__(self, pitch=120.0, nf=5, default_bw=None):
        self.pitch0 = float(pitch)
        self.nf = nf
        self.default_bw = list(default_bw) if default_bw else list(_DEFAULT_BW)
        self._segs = []

    def _pad(self, vals, fill):
        vals = list(vals)[:self.nf]
        i = 0
        while len(vals) < self.nf:
            vals.append(fill[i] if i < len(fill) else fill[-1]); i += 1
        return vals[:self.nf]

    def _seg(self, formants, dur, amp, voiced, bw=None, pitch=None):
        fc = self._pad(list(formants), _HI)
        bw = self._pad(bw, self.default_bw) if bw else list(self.default_bw)[:self.nf]
        self._segs.append(dict(fc=[float(x) for x in fc], bw=[float(x) for x in bw],
                               amp=float(amp), dur=float(dur), voiced=bool(voiced),
                               pitch=float(pitch) if pitch else self.pitch0))
        return self

    # ---- segment builders (chainable) ----
    def vowel(self, formants, dur=0.22, amp=0.85, pitch=None, bw=None):
        """A voiced vowel with the given formant frequencies (Hz)."""
        return self._seg(formants, dur, amp, True, bw=bw, pitch=pitch)

    def fricative(self, dur=0.12, amp=0.45, formants=(4200, 5200, 6000), bw=(700, 700, 700)):
        """An unvoiced (noise-excited) consonant -- hiss shaped by broad formants."""
        return self._seg(formants, dur, amp, False, bw=bw)

    def silence(self, dur=0.08):
        return self._seg([300, 900, 2400], dur, 0.0, True)

    def hold(self, formants, dur, amp=0.85, pitch=None, bw=None):
        """Alias for vowel() -- a steady held sound."""
        return self.vowel(formants, dur, amp, pitch, bw)

    # ---- assemble per-sample tracks ----
    def tracks(self):
        nf = self.nf
        a_fc = [[] for _ in range(nf)]
        a_bw = [[] for _ in range(nf)]
        a_amp, a_p, a_v = [], [], []
        prev = None
        for s in self._segs:
            N = max(1, int(round(s['dur'] * RATE)))
            frac = (np.arange(N) + 0.5) / N
            p0 = prev if prev else s          # glide from previous segment's targets
            for i in range(nf):
                a_fc[i].append(p0['fc'][i] + (s['fc'][i] - p0['fc'][i]) * frac)
                a_bw[i].append(p0['bw'][i] + (s['bw'][i] - p0['bw'][i]) * frac)
            a_amp.append(p0['amp'] + (s['amp'] - p0['amp']) * frac)
            a_p.append(p0['pitch'] + (s['pitch'] - p0['pitch']) * frac)
            a_v.append(np.full(N, s['voiced']))
            prev = s
        if not a_amp:
            return None, None, None, None, None
        fc = [np.concatenate(a_fc[i]) for i in range(nf)]
        bw = [np.concatenate(a_bw[i]) for i in range(nf)]
        return fc, bw, np.concatenate(a_amp), np.concatenate(a_p), np.concatenate(a_v)
