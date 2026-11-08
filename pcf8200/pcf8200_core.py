# -*- coding: utf-8 -*-
"""The PCF8200 audio core: per-sample parameters in, audio out, in any block size.

This is the one reference for the chip's sound.  The library's render() and the
BraiLab add-on's chip_synth both run through Core, and the C port is held to it.
The file stands alone, importing only numpy, so an add-on can carry it as a single
module without the rest of the package.

The chip runs a periodic-pulse / noise excitation into five cascaded resonators
(y(n)=x(n)+B*F*y(n-1)-B**2*y(n-2), F=2cos(2*pi*fc/fs), B=exp(-pi*bw/fs)), with a
gentle glottal tilt and an output low-pass.

Every uncertain constant is here, marked with where it came from:

    [chip]    fixed by the silicon, from the datasheet
    [ear]     matched by ear to TTS.dll; the real BraiLab PC may overrule it
    [device]  the amplifier after the chip, not the chip itself
    [model]   a modelling choice
"""
import math
import os

import numpy as np

RATE = 10000                 # [chip] internal speech rate
TILT_HZ = 600.0              # [ear] glottal source rolloff (tames the bright buzz)
LOWPASS_HZ = 4200.0          # [ear] output low-pass (was 2600 to 2.0.0; see LP_SOS)
NOISE_GAIN = 0.5             # [ear] level of the noise source
SEED = 12345                 # [model] where the noise source starts
PITCH_MIN_HZ = 40.0          # [model] floor of the pitch the source will follow
PITCH_MAX_HZ = 400.0         # [model] ceiling of the same
HARMONIC_FADE = 0.16         # [model] top harmonics fade over this fraction of the band

#: [device] Output high-pass, in hertz, and how many one-pole stages of it.
#:
#: A PCF8200 device drives an AC-coupled amplifier, which rolls off the bottom
#: of the band -- but only the bottom.  An earlier version cut at 600 Hz, tuned
#: against a recording of real hardware; that recording is a small speaker in a
#: room, passing almost nothing below 250 Hz, so matching it removed the low end
#: altogether.  Measured instead against the vendor's own TTS.dll, which reaches
#: a sound card rather than a small cone, the target is 23.6% of the energy
#: below 250 Hz; an unfiltered render puts 36.5% there.  The fault was never
#: that the low end existed, only that there was half again too much of it,
#: taking headroom the rest of the voice needed.
#:
#: This models a *device*.  Pass highpass=0 for the chip's own output.
HIGHPASS_HZ = 90.0
HIGHPASS_POLES = 3

#: [device] What fits back under the peaks once the deepest rumble is gone.
#: Cutting higher would free more headroom, at the price of the bass.
HIGHPASS_MAKEUP = 0.9315

#: [device] Soft knee on the output stage, as a fraction of full scale.
#:
#: A real device's amplifier runs out of swing gradually; a fixed-point buffer
#: stops dead, which is audible as static on the loudest points of speech.  Above
#: this threshold the response bends, asymptotically approaching 1.0, so a device
#: render can never reach full scale however it is later scaled.
#:
#: At 0.75 it engages on 0.04% of samples (0.49% THD) and buys +1.2 dB.  Lower is
#: louder and dirtier: 0.62 gives +2.25 dB at 1.42% THD.  Memoryless, so it
#: commutes with the block split.
SOFTKNEE = 0.75

# butter(4, 4200, 'low', fs=10000) as two second-order sections (b0,b1,b2,a1,a2;
# a0=1), hardcoded so no scipy is needed.  Regenerate with
# scipy.signal.butter(4, hz, 'low', fs=10000, output='sos') if LOWPASS_HZ moves.
#
# 2600 Hz was tuned against TTS.dll, where it hid an F5 buzz.  But the chip's own
# frames put F4 near 3.25 kHz and F5 at 3.9 or 4.6 kHz, and Arato places his
# vowels' microintonation in F4/F5 movement; 2600 cut all of it, which is the
# muffled, "low sample rate" sound listeners heard.  4200 keeps F4 and F5 and
# still rolls off before 5 kHz.  Chosen by ear in an A/B against 2600, 3400 and
# TTS.dll's bandwidths; the source tilt stays at 600, since lowering it brings
# back the buzz.
LP_SOS = (
    (0.5142468489962791, 1.0284936979925583, 0.5142468489962791,
     1.2128120926202175, 0.38400416228655304),
    (1.0, 2.0, 1.0, 1.4797988943972162, 0.6886769530538613),
)


def soft_knee(sig, knee):
    """Bend the top of the swing so a device render cannot reach full scale."""
    if not knee or knee >= 1.0:
        return sig
    a = np.abs(sig)
    if not (a > knee).any():
        return sig
    room = 1.0 - knee
    return np.where(a > knee,
                    np.sign(sig) * (knee + room * np.tanh((a - knee) / room)),
                    sig)


def make_core(nf, **kw):
    """A Core: in C if the native library is here, otherwise this module's.  The
    PCF8200_BACKEND environment variable forces one: python, or native."""
    backend = os.environ.get('PCF8200_BACKEND', 'auto')
    if backend != 'python':
        try:
            from . import pcf8200_native as native
        except ImportError:
            try:
                import pcf8200_native as native
            except ImportError:
                native = None
        if native is not None and native.load() is not None and nf <= native.MAX_FORMANTS:
            return native.NativeCore(nf, **kw)
        if backend == 'native':
            raise OSError('PCF8200_BACKEND=native, but the C core is not available')
    return Core(nf, **kw)


class Noise:
    """The noise source: xorshift32, one value per sample, voiced or not.

    Written out so that C repeats it exactly.  The state starts as

        x = (seed * 2654435761 + 1) mod 2**32, or 1 if that is 0

    and each sample does, in 32-bit unsigned arithmetic,

        x ^= x << 13;  x ^= x >> 17;  x ^= x << 5;
        value = x * (2 * gain / 2**32) - gain;

    which is uniform on [-gain, gain).  The chip's own noise generator is not
    documented, so this models only its effect.  [model]
    """

    def __init__(self, seed=SEED):
        self.x = ((seed * 2654435761 + 1) & 0xFFFFFFFF) or 1

    def block(self, n, gain):
        scale = 2.0 * gain / 4294967296.0
        x = self.x
        out = [0.0] * n
        for i in range(n):
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= x >> 17
            x ^= (x << 5) & 0xFFFFFFFF
            out[i] = x * scale - gain
        self.x = x
        return np.asarray(out)


class Core:
    """One running chip.  run() takes the next block of per-sample parameters and
    returns its audio; every filter, the phase and the noise carry across calls,
    so any split of the same samples gives the same output, bit for bit.

    lowpass     True runs the LP_SOS sections in the loop
    highpass    hertz of the output high-pass in the loop; 0 for none
    gain, knee  applied last: the makeup gain and the soft knee
    """

    def __init__(self, nf, source_tilt=TILT_HZ, noise_gain=NOISE_GAIN, seed=SEED,
                 lowpass=True, highpass=HIGHPASS_HZ, gain=1.0, knee=0.0):
        self.nf = nf
        self.noise_gain = noise_gain
        self.noise = Noise(seed)
        self.tilt = math.exp(-2.0 * math.pi * source_tilt / RATE) if source_tilt else None
        self.lowpass = bool(lowpass)
        self.ha = math.exp(-2.0 * math.pi * float(highpass) / RATE) if highpass else None
        self.gain = gain
        self.knee = knee
        self.phase = 0.0                     # unwrapped: the running sum of p / RATE
        self.ty = 0.0                        # tilt
        self.y1 = [0.0] * nf                 # cascade
        self.y2 = [0.0] * nf
        self.lz = [0.0, 0.0, 0.0, 0.0]       # low-pass
        self.hx = [0.0] * HIGHPASS_POLES     # high-pass
        self.hy = [0.0] * HIGHPASS_POLES

    def _voiced(self, p):
        """The band-limited sawtooth for pitch track `p`, tilted.

        One harmonic at a time, accumulated in order.  The same sum as a
        (samples x harmonics) matrix reduced along the harmonics -- but that
        reduction is pairwise, so its rounding depends on how many harmonics the
        matrix has, which depends on the lowest pitch in *this* block.  Summing
        sequentially, a harmonic beyond a sample's own cutoff adds an exact zero
        and the result no longer depends on the block, which is what lets a
        caller stream an utterance.  It also never materialises the matrix.
        """
        phase = np.cumsum(np.concatenate(([self.phase], p / RATE)))[1:]
        self.phase = float(phase[-1])
        phase = phase - np.floor(phase)
        edge = RATE * 0.5
        kmax = max(1, int(edge / max(float(p.min()), 1e-6)))
        vsrc = np.zeros(len(p))
        for k in range(1, kmax + 1):
            w = np.clip((edge - p * k) / (edge * HARMONIC_FADE), 0.0, 1.0)
            w = w * w * (3.0 - 2.0 * w)
            vsrc += np.sin(2.0 * np.pi * phase * k) * (w / k)
        vsrc *= -(2.0 / np.pi)
        if self.tilt is not None:                # one-pole glottal tilt
            ta = self.tilt
            c0 = 1.0 - ta
            vl = vsrc.tolist()
            yp = self.ty
            for i in range(len(vl)):
                yp = c0 * vl[i] + ta * yp
                vl[i] = yp
            self.ty = yp
            vsrc = np.asarray(vl)
        return vsrc

    def run(self, amp, pitch, voiced, fc, bw):
        """Audio for the next block.  amp, pitch (Hz) and voiced (bool) are arrays
        of one length; fc and bw hold one such array per formant, in hertz.

        Both sources run on every sample, whichever one is heard: the phase and
        the tilt advance through noise, and the noise through voicing."""
        n = len(amp)
        if n == 0:
            return np.zeros(0)
        nf = self.nf
        p = np.clip(pitch, PITCH_MIN_HZ, PITCH_MAX_HZ)
        vsrc = self._voiced(p)
        noise = self.noise.block(n, self.noise_gain)
        xl = (np.where(voiced, vsrc, noise) * amp).tolist()

        # ---- five-formant cascade (+ low-pass, high-pass), per-sample loop ----
        B1 = []
        B2 = []
        for i in range(nf):
            Bc = np.exp(-np.pi * bw[i] / RATE)
            Fc = 2.0 * np.cos(2.0 * np.pi * fc[i] / RATE)
            B1.append((Bc * Fc).tolist())
            B2.append((-(Bc * Bc)).tolist())
        y1 = self.y1
        y2 = self.y2
        rng_nf = range(nf)
        lp = self.lowpass
        (lb0, lb1, lb2, la1, la2) = LP_SOS[0]
        (mb0, mb1, mb2, ma1, ma2) = LP_SOS[1]
        lz0, lz1, mz0, mz1 = self.lz
        ha = self.ha
        hx1, hx2, hx3 = self.hx
        hy1, hy2, hy3 = self.hy
        for k in range(n):
            v = xl[k]
            for i in rng_nf:
                yn = v + B1[i][k] * y1[i] + B2[i][k] * y2[i]
                y2[i] = y1[i]
                y1[i] = yn
                v = yn
            if lp:
                o = lb0 * v + lz0
                lz0 = lb1 * v - la1 * o + lz1
                lz1 = lb2 * v - la2 * o
                v = mb0 * o + mz0
                mz0 = mb1 * o - ma1 * v + mz1
                mz1 = mb2 * o - ma2 * v
            if ha is not None:
                hy1 = ha * (hy1 + v - hx1)
                hx1 = v
                hy2 = ha * (hy2 + hy1 - hx2)
                hx2 = hy1
                hy3 = ha * (hy3 + hy2 - hx3)
                hx3 = hy2
                v = hy3
            xl[k] = v
        self.lz = [lz0, lz1, mz0, mz1]
        self.hx = [hx1, hx2, hx3]
        self.hy = [hy1, hy2, hy3]
        return soft_knee(np.asarray(xl) * self.gain, self.knee)
