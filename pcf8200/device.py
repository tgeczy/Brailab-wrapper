# -*- coding: utf-8 -*-
"""PCF8200 -- a software stand-in for the chip, driven by its own command stream.

Talk to it the way a BraiLab or Ciber board does: set a start pitch, clock in
5-byte speech frames (and control writes), STOP, then render() the accumulated
stream to audio.

    from pcf8200 import PCF8200
    chip = PCF8200(voice="male")
    chip.pitch_hz(110)
    chip.frame_codes(F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)   # steady /a/
    chip.frame_codes(F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)
    chip.stop()
    chip.to_wav("a.wav")
"""
import numpy as np
from . import protocol as P
from . import tables as T
from .chip import render, RATE, TILT_HZ, LOWPASS_HZ

STD = int(round(0.0128 * RATE))          # standard frame = 128 samples at 10 kHz


class PCF8200:
    def __init__(self, voice="male", rate=RATE, source_tilt=TILT_HZ, lowpass=LOWPASS_HZ):
        self.female = str(voice).lower().startswith("f")
        self.rate = rate
        self.source_tilt = source_tilt
        self.lowpass = lowpass
        self._pitch_byte = 46            # default start pitch
        self._fs = 0                     # FS1/FS0: standard frame = 12.8 ms
        self._seq = []                   # ('pitch',b) / ('frame',bytes5) / ('ctrl',bytes2)

    def _std_samples(self, fs):
        """Samples in one standard frame at speed code `fs` (FS_TAB, ms)."""
        return max(1, int(round(P.FS_TAB[fs & 3][1] * 0.001 * self.rate)))

    # ---- the chip's commands ----
    def pitch(self, byte):
        """Start-pitch command (raw byte); Hz = byte * PITCH_HZ_PER_UNIT."""
        self._pitch_byte = int(byte) & 0xFF
        self._seq.append(('pitch', self._pitch_byte)); return self

    def pitch_hz(self, hz):
        return self.pitch(int(round(hz / T.PITCH_HZ_PER_UNIT)))

    def frame(self, f):
        """Clock in one raw 5-byte speech frame."""
        f = bytes(f)
        if len(f) != 5:
            raise ValueError("a PCF8200 frame is 5 bytes")
        self._seq.append(('frame', f)); return self

    def frame_codes(self, **codes):
        """Clock in a frame built from field codes (F1..F5, B1..B5, AM, PI, FD)."""
        return self.frame(P.encode_frame(**codes))

    def control(self, stop=False, female=None, fs=0):
        """Control write: STOP flag, M/F (female table), FS speed 0..3."""
        if female is not None:
            self.female = bool(female)
        if not stop:
            self._fs = fs & 3
        self._seq.append(('ctrl', bytes([0x00, P.control_byte(stop, self.female, fs)])))
        return self

    def stop(self):
        return self.control(stop=True)

    def reset(self):
        self._seq = []; return self

    # ---- render the accumulated command stream ----
    def tracks(self):
        """Decode the command stream to per-sample (fc, bw, amp, pitch, voiced)."""
        nf = 4 if self.female else 5
        a_amp, a_p, a_noise = [], [], []
        a_fc = [[] for _ in range(nf)]
        a_bw = [[] for _ in range(nf)]
        anchor = self._pitch_byte * T.PITCH_HZ_PER_UNIT
        pitch = anchor
        prev = None
        # FS1/FS0 in the control write set the standard frame duration, and a
        # stream may change it part-way through, so track it as we walk.
        std = self._std_samples(self._fs)
        for kind, val in self._seq:
            if kind == 'pitch':
                anchor = val * T.PITCH_HZ_PER_UNIT; pitch = anchor; continue
            if kind == 'ctrl':
                d = P.decode_control(val)
                if d['stop']:
                    break
                std = self._std_samples(d['fs'])
                continue
            if kind != 'frame':
                continue
            d = P.decode_frame(val)
            cur = P.frame_params(d, female=self.female)
            if prev is None:
                prev = dict(cur)
            n = max(1, int(round(std * P.FD_MULT[d['FD']])))
            pt = min(max(pitch + cur['pi'] * P.FD_MULT[d['FD']], 40.0), 400.0)
            frac = (np.arange(n) + 0.5) / n
            a_amp.append(prev['ampl'] + (cur['ampl'] - prev['ampl']) * frac)
            a_p.append(pitch + (pt - pitch) * frac)
            a_noise.append(np.full(n, bool(cur['noise'])))
            for i in range(nf):
                pf, pbw = prev['formants'][i] if i < len(prev['formants']) else cur['formants'][i]
                cf, cbw = cur['formants'][i]
                a_fc[i].append(pf + (cf - pf) * frac)
                a_bw[i].append(pbw + (cbw - pbw) * frac)
            pitch = pt; prev = cur
        if not a_amp:
            return None, None, None, None, None
        amp = np.concatenate(a_amp); p = np.concatenate(a_p)
        noise = np.concatenate(a_noise)
        fc = [np.concatenate(a_fc[i]) for i in range(nf)]
        bw = [np.concatenate(a_bw[i]) for i in range(nf)]
        return fc, bw, amp, p, ~noise

    def render(self):
        """Synthesise the accumulated command stream to a float waveform."""
        fc, bw, amp, p, voiced = self.tracks()
        if fc is None:
            return np.zeros(0)
        return render(fc, bw, amp, p, voiced, rate=self.rate,
                      source_tilt=self.source_tilt, lowpass=self.lowpass)

    def to_wav(self, path, audio=None, normalize=True):
        from .chip import write_wav
        return write_wav(path, self.render() if audio is None else audio,
                         self.rate, normalize)
