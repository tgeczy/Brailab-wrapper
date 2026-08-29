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
import math
import numpy as np

RATE = 10000                 # the chip's internal speech rate (fixed by silicon)
TILT_HZ = 600.0              # glottal source rolloff (tames the bright buzz)
LOWPASS_HZ = 2600.0         # output low-pass

# butter(4, 2600, 'low', fs=10000) as two second-order sections (b0,b1,b2,a1,a2;
# a0=1), hardcoded so no scipy is needed.  Regenerate with
# scipy.signal.butter(4, hz, 'low', fs=10000, output='sos') if LOWPASS_HZ moves.
_LP_SOS = (
    (0.10631234573760745, 0.2126246914752149, 0.10631234573760745,
     0.06533681044002995, 0.04055215548149342),
    (1.0, 2.0, 1.0, 0.09087377369825426, 0.4472530945667702),
)


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


def render(fc, bw, amp, pitch, voiced=None, *, rate=RATE, source_tilt=TILT_HZ,
           lowpass=LOWPASS_HZ, noise_gain=0.5, seed=12345):
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
    FS = RATE
    rng = np.random.default_rng(seed)

    # ---- excitation: band-limited sawtooth (voiced) / noise (unvoiced) ----
    p = np.clip(pitch, 40.0, 400.0)
    phase = np.cumsum(p / FS)
    phase = phase - np.floor(phase)
    edge = FS * 0.5
    KMAX = max(1, int(edge / max(float(p.min()), 1e-6)))
    kk = np.arange(1, KMAX + 1)
    W = np.clip((edge - np.outer(p, kk)) / (edge * 0.16), 0.0, 1.0)
    W = W * W * (3.0 - 2.0 * W)
    Smat = np.sin(2.0 * np.pi * np.outer(phase, kk))
    vsrc = -(2.0 / np.pi) * (Smat * (W / kk)).sum(1)
    if source_tilt:                              # one-pole glottal tilt (voiced only)
        ta = math.exp(-2.0 * math.pi * source_tilt / FS)
        c0 = 1.0 - ta
        vl = vsrc.tolist(); yp = 0.0
        for i in range(N):
            yp = c0 * vl[i] + ta * yp
            vl[i] = yp
        vsrc = np.asarray(vl)
    exc = np.where(voiced, vsrc, rng.uniform(-noise_gain, noise_gain, N)) * amp

    # ---- five-formant cascade (+ fused low-pass), manual per-sample loop ----
    B1 = [(np.exp(-np.pi * bw[i] / FS) * (2.0 * np.cos(2.0 * np.pi * fc[i] / FS))).tolist()
          for i in range(nf)]
    B2 = [(-(np.exp(-np.pi * bw[i] / FS) ** 2)).tolist() for i in range(nf)]
    xl = exc.tolist()
    y1 = [0.0] * nf; y2 = [0.0] * nf
    lp = bool(lowpass)
    if lp:
        (lb0, lb1, lb2, la1, la2) = _LP_SOS[0]
        (mb0, mb1, mb2, ma1, ma2) = _LP_SOS[1]
        lz0 = lz1 = mz0 = mz1 = 0.0
    rng_nf = range(nf)
    for k in range(N):
        v = xl[k]
        for i in rng_nf:
            yn = v + B1[i][k] * y1[i] + B2[i][k] * y2[i]
            y2[i] = y1[i]; y1[i] = yn; v = yn
        if lp:
            o = lb0 * v + lz0
            lz0 = lb1 * v - la1 * o + lz1
            lz1 = lb2 * v - la2 * o
            v = mb0 * o + mz0
            mz0 = mb1 * o - ma1 * v + mz1
            mz1 = mb2 * o - ma2 * v
        xl[k] = v
    sig = np.asarray(xl)
    if lowpass and abs(lowpass - LOWPASS_HZ) >= 1e-6:
        # non-default cutoff: needs scipy (optional); default path above is scipy-free
        from scipy.signal import butter, sosfilt
        sig = sosfilt(butter(4, lowpass, 'low', fs=FS, output='sos'), np.asarray(exc.tolist()))
    if rate != FS:
        sig = _resample(sig, FS, rate)
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
