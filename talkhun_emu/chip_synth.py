# -*- coding: utf-8 -*-
"""PCF8200 core at the chip's real internal rate.

Per the Philips report (EDP/8807): the excitation source and the five-formant
cascade run at the chip's **10 kHz** internal sampling rate; the 8x up-sampler
to 80 kHz is an *output* low-pass stage (modelled here as plain resampling when a
higher WAV rate is asked for).  The resonator is the chip's own three-multiplier
section

    y(n) = x(n) + B*F*y(n-1) - B**2*y(n-2)      F = 2 cos(2 pi fc/fs),  B = e^(-pi b/fs)

with **no input-normalisation term** (the released synth.py invented a0 = 1-b1-b2
to compensate for running the cascade at 80x; that is the emulator error this
module removes).  Parameters interpolate as an 8-step staircase per standard
frame; the voiced source is a periodic pulse (impulse) train, integer-period at
10 kHz (which reproduces the chip's 100 us pitch quantisation for free).

This is a *parallel* path to synth.render() -- the released one is untouched.
Everything the theory disputes is switchable for A/B: `source` (pulse|saw),
`a0` (chip vs normalised), `ampl_compress` (chip ~3 dB/code vs TTS.dll ~0.75).
"""
import math
import numpy as np
from scipy.signal import lfilter, resample_poly, butter, sosfilt

import pcf8200
from pcf8200 import decode_frame, decode_control, FD_MULT
from synth import frame_params, active_tables

CHIP_RATE = 10000                      # internal speech rate (fixed by silicon)
STD = int(round(0.0128 * CHIP_RATE))   # standard frame = 128 samples
STEP = STD // 8                        # 16 samples = one of the 8 interp steps

# Winning config, ear-matched to TTS.dll on Hungarian material 2026-08-28
# (golyó + reggelt both judged "perfect to tts.dll").  See
# memory/pcf8200-wobble-diagnosis.md for the full derivation.
CHIP_TILT_HZ = 600.0                   # glottal source rolloff (tames the bright "rattle")
CHIP_LOWPASS_HZ = 2600.0               # output low-pass (finishes the rattle removal)


def _interp_formants(prev, cur, frac, nf):
    out = []
    for i in range(nf):
        pf, pbw = prev['formants'][i] if i < len(prev['formants']) else cur['formants'][i]
        cf, cbw = cur['formants'][i]
        out.append((pf + (cf - pf) * frac, pbw + (cbw - pbw) * frac))
    return out


def render_chip(seq, out_rate=CHIP_RATE, source='blsaw', a0=False,
                ampl_compress=1.0, time_scale=1.0, real=None, pitch_byte=46,
                pitch_mode='cumulative', seed=12345, noise_gain=0.5, scale=1.0,
                staircase=False, source_tilt=CHIP_TILT_HZ, lowpass=CHIP_LOWPASS_HZ,
                flat_pitch=False, smooth_block=8):
    FS = CHIP_RATE
    real = pcf8200.REAL_TABLES if real is None else real
    tables = active_tables(real)
    ptables, hz_per_unit = tables[:6], tables[6]

    furcsa = any(decode_control(v)['furcsa'] for k, v in seq
                 if k == 'ctrl' and not decode_control(v)['stop'])
    nf = 4 if furcsa else 5
    rng = np.random.default_rng(seed)

    zi = [np.zeros(2) for _ in range(nf)]
    # One-pole spectral tilt on the voiced source: a bare band-limited sawtooth
    # is -6 dB/oct, too bright, and over-excites F5 (heard as a rattly "cone"
    # buzz on the top).  A real glottal pulse rolls off steeper; this pole
    # starves the high formants toward TTS.dll's spectral envelope.
    tilt_a = math.exp(-2.0 * math.pi * source_tilt / FS) if source_tilt else None
    tilt_zi = np.zeros(1)
    phase = 0.0
    anchor = pitch_byte * hz_per_unit
    pitch = anchor
    prev = None
    out = []

    for kind, val in seq:
        if kind == 'pitch':
            anchor = val * hz_per_unit
            pitch = anchor
            continue
        if kind != 'frame':
            continue
        d = decode_frame(val)
        cur = frame_params(d, ptables, furcsa, ampl_compress=ampl_compress)
        if prev is None:
            prev = dict(cur)

        n = max(STEP, int(round(STD * FD_MULT[d['FD']] * time_scale)))
        if flat_pitch:
            pt = anchor                                    # intonation off: pin F0
        elif pitch_mode == 'cumulative':
            pt = min(max(pitch + cur['pi'] * FD_MULT[d['FD']], 40.0), 400.0)
        else:
            pt = min(max(anchor + cur['pi'], 40.0), 400.0)

        block = STEP if staircase else max(1, smooth_block)  # continuous-interp granularity
        pos = 0
        sub = 0
        while pos < n:
            m = min(block, n - pos)
            if staircase:
                frac = (min(7, sub) + 1) / 8.0             # 8-step staircase, then hold
            else:
                frac = (pos + m * 0.5) / n                 # continuous, smooth coefficients
            amp = prev['ampl'] + (cur['ampl'] - prev['ampl']) * frac
            p = pitch + (pt - pitch) * frac

            if cur['noise']:
                x = rng.uniform(-noise_gain, noise_gain, m) * amp
            elif source == 'pulse':
                x = np.zeros(m)
                stepph = p / FS
                for i in range(m):
                    phase += stepph
                    if phase >= 1.0:
                        phase -= 1.0
                        x[i] = 1.0
                x *= amp
            elif source == 'blsaw':
                # Band-limited sawtooth at the NATIVE 10 kHz rate: sum harmonics
                # only up to the 5 kHz band edge, so none fold back as the
                # inharmonic "swirl"/hash a naive ramp aliases at this rate.  Top
                # harmonics are raised-cosine faded so one entering/leaving as the
                # pitch drifts does so smoothly (no tick).
                stepph = p / FS
                ph = phase + stepph * np.arange(m)
                phase = float((phase + stepph * m) % 1.0)
                edge = FS * 0.5                            # 5 kHz
                kmax = max(1, int(edge / max(p, 1e-6)))
                kk = np.arange(1, kmax + 1)
                w = np.clip((edge - kk * p) / (edge * 0.16), 0.0, 1.0)
                w = w * w * (3.0 - 2.0 * w)
                x = -(2.0 / np.pi) * (
                    np.sin(2.0 * np.pi * np.outer(ph % 1.0, kk)) * (w / kk)).sum(1)
                if tilt_a is not None:
                    x, tilt_zi = lfilter([1.0 - tilt_a], [1.0, -tilt_a], x, zi=tilt_zi)
                x *= amp
            else:                                          # naive sawtooth, A/B only
                stepph = p / FS
                ph = (phase + stepph * np.arange(1, m + 1)) % 1.0
                phase = float(ph[-1])
                x = (2.0 * ph - 1.0)
                if tilt_a is not None:
                    x, tilt_zi = lfilter([1.0 - tilt_a], [1.0, -tilt_a], x, zi=tilt_zi)
                x = x * amp

            fmnts = _interp_formants(prev, cur, frac, nf)
            for i in range(nf):
                fc, bw = fmnts[i]
                F = 2.0 * math.cos(2.0 * math.pi * fc / FS)
                B = math.exp(-math.pi * bw / FS)
                b1 = B * F
                b2 = -(B * B)
                b = [1.0 - b1 - b2] if a0 else [1.0]       # a0=True = old normalised form
                x, zi[i] = lfilter(b, [1.0, -b1, -b2], x, zi=zi[i])

            out.append(x * scale)
            pos += m
            sub += 1
        pitch = pt
        prev = cur

    if not out:
        return np.zeros(0)
    sig = np.concatenate(out)
    if lowpass:
        # Output low-pass: with the source tilt this is what finally matched
        # TTS.dll by ear -- it removes the bright top-end "rattle" our 5 kHz-wide
        # cascade carries where TTS.dll is already dark.
        sig = sosfilt(butter(4, lowpass, 'low', fs=FS, output='sos'), sig)
    if out_rate != FS:
        g = math.gcd(int(out_rate), FS)
        sig = resample_poly(sig, int(out_rate) // g, FS // g)
    return sig


def render_chip_fast(seq, out_rate=CHIP_RATE, source='blsaw', a0=False,
                     ampl_compress=1.0, time_scale=1.0, real=None, pitch_byte=46,
                     pitch_mode='cumulative', seed=12345, noise_gain=0.5, scale=1.0,
                     source_tilt=CHIP_TILT_HZ, lowpass=CHIP_LOWPASS_HZ,
                     flat_pitch=False, furcsa_override=None, **_ignored):
    """Same synthesis as render_chip (per-sample continuous interpolation, no a0)
    but built for speed: parameter trajectories and the band-limited excitation
    are vectorised, and the five-formant cascade runs as ONE manual per-sample
    Python loop instead of ~6 scipy.lfilter() calls per 2-sample block.  Kills
    the lfilter per-call overhead that made the block version ~20x too slow for
    real-time NVDA use, while keeping interpolation per-sample (so no swirl)."""
    FS = CHIP_RATE
    r = pcf8200.REAL_TABLES if real is None else real
    tables = active_tables(r)
    ptables, hz_per_unit = tables[:6], tables[6]
    if furcsa_override is not None:
        furcsa = bool(furcsa_override)
    else:
        furcsa = any(decode_control(v)['furcsa'] for k, v in seq
                     if k == 'ctrl' and not decode_control(v)['stop'])
    nf = 4 if furcsa else 5
    rng = np.random.default_rng(seed)

    # ---- pass 1: per-sample parameter trajectories (Python loop over ~frames) ----
    a_amp, a_p, a_noise = [], [], []
    a_fc = [[] for _ in range(nf)]
    a_bw = [[] for _ in range(nf)]
    anchor = pitch_byte * hz_per_unit
    pitch = anchor
    prev = None
    for kind, val in seq:
        if kind == 'pitch':
            anchor = val * hz_per_unit
            pitch = anchor
            continue
        if kind != 'frame':
            continue
        d = decode_frame(val)
        cur = frame_params(d, ptables, furcsa, ampl_compress=ampl_compress)
        if prev is None:
            prev = dict(cur)
        n = max(STEP, int(round(STD * FD_MULT[d['FD']] * time_scale)))
        if flat_pitch:
            pt = anchor
        elif pitch_mode == 'cumulative':
            pt = min(max(pitch + cur['pi'] * FD_MULT[d['FD']], 40.0), 400.0)
        else:
            pt = min(max(anchor + cur['pi'], 40.0), 400.0)
        frac = (np.arange(n) + 0.5) / n
        a_amp.append(prev['ampl'] + (cur['ampl'] - prev['ampl']) * frac)
        a_p.append(pitch + (pt - pitch) * frac)
        a_noise.append(np.full(n, bool(cur['noise'])))
        for i in range(nf):
            pf, pbw = prev['formants'][i] if i < len(prev['formants']) else cur['formants'][i]
            cf, cbw = cur['formants'][i]
            a_fc[i].append(pf + (cf - pf) * frac)
            a_bw[i].append(pbw + (cbw - pbw) * frac)
        pitch = pt
        prev = cur
    if not a_amp:
        return np.zeros(0)
    amp = np.concatenate(a_amp)
    p = np.concatenate(a_p)
    noise = np.concatenate(a_noise)
    fc = [np.concatenate(a_fc[i]) for i in range(nf)]
    bw = [np.concatenate(a_bw[i]) for i in range(nf)]
    N = len(amp)

    # ---- excitation (vectorised) ----
    phase = np.cumsum(p / FS)
    phase = phase - np.floor(phase)
    edge = FS * 0.5
    if source in ('blsaw', 'saw'):
        KMAX = max(1, int(edge / max(float(p.min()), 1e-6)))
        kk = np.arange(1, KMAX + 1)
        W = np.clip((edge - np.outer(p, kk)) / (edge * 0.16), 0.0, 1.0)
        W = W * W * (3.0 - 2.0 * W)
        Smat = np.sin(2.0 * np.pi * np.outer(phase, kk))
        voiced = -(2.0 / np.pi) * (Smat * (W / kk)).sum(1)
    else:  # pulse
        voiced = np.zeros(N)
        pc = np.cumsum(p / FS)
        idx = np.where(np.floor(pc[1:]) > np.floor(pc[:-1]))[0] + 1
        voiced[idx] = 1.0
    if source_tilt:
        ta = math.exp(-2.0 * math.pi * source_tilt / FS)
        voiced = lfilter([1.0 - ta], [1.0, -ta], voiced)
    exc = np.where(noise, rng.uniform(-noise_gain, noise_gain, N), voiced) * amp

    # ---- five-formant cascade: one manual per-sample loop, no scipy ----
    B1 = []
    B2 = []
    for i in range(nf):
        Bc = np.exp(-np.pi * bw[i] / FS)
        Fc = 2.0 * np.cos(2.0 * np.pi * fc[i] / FS)
        B1.append((Bc * Fc).tolist())
        B2.append((-(Bc * Bc)).tolist())
    xl = exc.tolist()
    y1 = [0.0] * nf
    y2 = [0.0] * nf
    rng_nf = range(nf)
    for k in range(N):
        v = xl[k]
        for i in rng_nf:
            yn = v + B1[i][k] * y1[i] + B2[i][k] * y2[i]
            y2[i] = y1[i]
            y1[i] = yn
            v = yn
        xl[k] = v
    sig = np.array(xl) * scale

    if lowpass:
        sig = sosfilt(butter(4, lowpass, 'low', fs=FS, output='sos'), sig)
    if out_rate != FS:
        g = math.gcd(int(out_rate), FS)
        sig = resample_poly(sig, int(out_rate) // g, FS // g)
    return sig
