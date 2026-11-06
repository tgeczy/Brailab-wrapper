# -*- coding: utf-8 -*-
"""Software Philips PCF8200 formant synthesiser -- the render core.

Feed it formant tracks (F1..F5 in Hz), bandwidths, amplitude and pitch over time
and it produces audio the way the chip's five-formant cascade does.  Pure numpy,
no scipy.  This is the same core matched by ear and by measurement to real
PCF8200 silicon in the BraiLab / Ciber projects, decoupled here so you can drive
it with ANY phonetics -- Polish, Klingon, a sine sweep, whatever.

The chip runs a periodic-pulse / noise excitation into five cascaded resonators
(y(n)=x(n)+B*F*y(n-1)-B**2*y(n-2), F=2cos(2*pi*fc/fs), B=exp(-pi*bw/fs)), with a
gentle glottal tilt and an output low-pass.  Internal rate is 10 kHz; ask for any
output rate and it band-limit-resamples.
"""
import numpy as np

from .pcf8200_core import (Core, RATE, TILT_HZ, LOWPASS_HZ, HIGHPASS_HZ, HIGHPASS_POLES,
                           HIGHPASS_MAKEUP, SOFTKNEE, NOISE_GAIN, SEED,
                           soft_knee as _soft_knee)


def _resample(x, src, dst):
    """Band-limited FFT resample (same method as scipy.signal.resample), numpy only."""
    if src == dst or len(x) == 0:
        return x
    n = len(x)
    m = int(round(n * float(dst) / float(src)))
    if m <= 0:
        return x[:0]
    X = np.fft.rfft(x)
    nb = m // 2 + 1
    Y = np.zeros(nb, dtype=complex)
    kc = min(nb, len(X))
    Y[:kc] = X[:kc]
    if m % 2 == 0 and kc == nb and nb > 1:
        Y[-1] = Y[-1].real
    return np.fft.irfft(Y, m) * (float(m) / n)



def _apply_highpass(sig, fc, rate):
    """Three one-pole high-passes and the makeup gain that goes with them.

    See HIGHPASS_HZ for why a device needs this and the bare chip does not.
    """
    if not fc:
        return sig
    import math
    a = math.exp(-2.0 * math.pi * float(fc) / rate)
    for _ in range(HIGHPASS_POLES):
        out = np.empty_like(sig)
        px = py = 0.0
        for n in range(sig.shape[0]):
            x = sig[n]
            py = a * (py + x - px)
            px = x
            out[n] = py
        sig = out
    return _soft_knee(sig * HIGHPASS_MAKEUP, SOFTKNEE)

def render(fc, bw, amp, pitch, voiced=None, *, rate=RATE, source_tilt=TILT_HZ,
           lowpass=LOWPASS_HZ, highpass=HIGHPASS_HZ, noise_gain=NOISE_GAIN,
           seed=SEED):
    """Render formant tracks to a float waveform (roughly -1..1).

    Parameters
    ----------
    fc : array (nf, N) or (N,)      formant centre frequencies in Hz (nf up to 5)
    bw : array (nf, N) or (N,)      formant bandwidths in Hz (same shape as fc)
    amp : array (N,) or scalar      linear amplitude envelope
    pitch : array (N,) or scalar    F0 in Hz
    voiced : array (N,) bool        True = voiced (pulse), False = noise/fricative
    rate : int                      output sample rate (resampled from 10 kHz)
    """
    fc = np.atleast_2d(np.asarray(fc, dtype=float))
    bw = np.atleast_2d(np.asarray(bw, dtype=float))
    nf, N = fc.shape
    if bw.shape != fc.shape:
        bw = np.broadcast_to(bw, fc.shape).copy()
    amp = np.broadcast_to(np.asarray(amp, dtype=float), (N,)).astype(float)
    pitch = np.broadcast_to(np.asarray(pitch, dtype=float), (N,)).astype(float)
    voiced = np.ones(N, bool) if voiced is None else np.asarray(voiced, bool)
    # Only the default cutoff is the fused, scipy-free pair of sections.  Any
    # other cutoff is applied after the cascade instead -- running both would
    # filter twice at two different frequencies.
    lp = bool(lowpass) and abs(lowpass - LOWPASS_HZ) < 1e-6
    # The device's three output high-pass poles ride in the same loop when
    # nothing sits between the cascade and them (no resampling, no scipy
    # low-pass): three one-poles applied one after another per sample perform
    # exactly the operations _apply_highpass performs in three passes, in the
    # same order, so the result is bit-identical.
    hp = bool(highpass) and rate == RATE and (lp or not lowpass)
    core = Core(nf, source_tilt=source_tilt, noise_gain=noise_gain, seed=seed, lowpass=lp,
                highpass=highpass if hp else 0, gain=HIGHPASS_MAKEUP if hp else 1.0,
                knee=SOFTKNEE if hp else 0.0)
    sig = core.run(amp, pitch, voiced, fc, bw)
    if lowpass and not lp:
        # Non-default cutoff: needs scipy (optional); the default path above is
        # scipy-free.  This filters the cascade OUTPUT.  It used to be handed
        # `exc` -- the raw excitation -- which silently discarded every formant
        # and returned a lowpassed buzz for any cutoff but the default.
        from scipy.signal import butter, sosfilt
        sig = sosfilt(butter(4, lowpass, 'low', fs=RATE, output='sos'), sig)
    if rate != RATE:
        sig = _resample(sig, RATE, rate)
    if not hp:
        sig = _apply_highpass(sig, highpass, rate)
    return sig


def write_wav(path, audio, rate=RATE, normalize=True):
    """Write float audio (~ -1..1) to a 16-bit mono WAV.  normalize=True peak-
    normalises to -0.5 dBFS (consistent loudness); else scales by a fixed 16000."""
    import wave
    x = np.asarray(audio, dtype=float)
    if normalize and len(x):
        pk = float(np.max(np.abs(x)))
        if pk > 0:
            x = x * (0.95 / pk)
        pcm = np.clip(x * 32767, -32767, 32767).astype("<i2")
    else:
        pcm = np.clip(x * 16000.0, -32767, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


class Chip:
    """A software PCF8200.  `render(voice)` turns a Voice (or formant tracks) into
    a numpy waveform; `to_wav(path, audio)` writes a 16-bit mono WAV."""

    def __init__(self, rate=RATE, source_tilt=TILT_HZ, lowpass=LOWPASS_HZ):
        self.rate = rate
        self.source_tilt = source_tilt
        self.lowpass = lowpass

    def render(self, voice, **kw):
        """Render a Voice, or (fc, bw, amp, pitch[, voiced]) tuple, to float audio."""
        from .voice import Voice
        if isinstance(voice, Voice):
            fc, bw, amp, pitch, vd = voice.tracks()
        else:
            fc, bw, amp, pitch = voice[:4]
            vd = voice[4] if len(voice) > 4 else None
        return render(fc, bw, amp, pitch, vd, rate=self.rate,
                      source_tilt=self.source_tilt, lowpass=self.lowpass, **kw)

    def to_wav(self, path, audio, normalize=True):
        return write_wav(path, audio, self.rate, normalize)
