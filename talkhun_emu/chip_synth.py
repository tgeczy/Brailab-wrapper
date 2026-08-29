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

import pcf8200
from pcf8200 import decode_frame, decode_control, FD_MULT
from brai_synth import frame_params, active_tables  # renamed from 'synth' (too generic -> NVDA addon module clash)

CHIP_RATE = 10000                      # internal speech rate (fixed by silicon)
STD = int(round(0.0128 * CHIP_RATE))   # standard frame = 128 samples
STEP = STD // 8                        # 16 samples = one of the 8 interp steps

# Winning config, ear-matched to TTS.dll on Hungarian material 2026-08-28
# (golyó + reggelt both judged "perfect to tts.dll").  See
# memory/pcf8200-wobble-diagnosis.md for the full derivation.
CHIP_TILT_HZ = 600.0                   # glottal source rolloff (tames the bright "rattle")
CHIP_LOWPASS_HZ = 2600.0               # output low-pass (finishes the rattle removal)

# butter(4, 2600, 'low', fs=10000) as two second-order sections (b0,b1,b2,a1,a2;
# a0=1), hardcoded so the default output low-pass needs no scipy at all.  A
# non-default `lowpass` value falls back to a lazy scipy import.  Regenerate with
# scipy.signal.butter(4, hz, 'low', fs=10000, output='sos') if CHIP_LOWPASS_HZ moves.
_LP2600_SOS = (
    (0.10631234573760745, 0.2126246914752149, 0.10631234573760745,
     0.06533681044002995, 0.04055215548149342),
    (1.0, 2.0, 1.0, 0.09087377369825426, 0.4472530945667702),
)


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
    from scipy.signal import lfilter, resample_poly, butter, sosfilt  # A/B tool, off the bundle path
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


def _render_prep(seq, ampl_compress=1.0, time_scale=1.0, real=None, pitch_byte=46,
                 pitch_mode='cumulative', flat_pitch=False, furcsa_override=None):
    """Shared cheap front half: per-sample parameter trajectories (pass 1) plus the
    wrapped phase.  The expensive per-harmonic excitation is NOT built here -- it is
    streamed per block in _render_blocks, so first-audio stays ~one block even for a
    long paragraph.  Returns (amp, p, phase, noise, fc, bw, nf, N); N == 0 => empty."""
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
        return None, None, None, None, None, None, nf, 0
    amp = np.concatenate(a_amp)
    p = np.concatenate(a_p)
    noise = np.concatenate(a_noise)
    fc = [np.concatenate(a_fc[i]) for i in range(nf)]
    bw = [np.concatenate(a_bw[i]) for i in range(nf)]
    N = len(amp)
    phase = np.cumsum(p / FS)
    phase = phase - np.floor(phase)
    return amp, p, phase, noise, fc, bw, nf, N


def _render_blocks(amp, p, phase, noise, fc, bw, nf, N, source, noise_gain,
                   source_tilt, seed, scale, lp_default, block):
    """Band-limited excitation + one-pole source tilt + the five-formant cascade
    (+ fused default low-pass), computed and YIELDED in ~`block`-sample float
    arrays as it goes (block <= 0 => a single array).  EVERY state -- the tilt
    one-pole, the cascade biquads, the low-pass biquads, and the noise RNG --
    carries across blocks, so concatenating the yields is bit-identical to a single
    pass.  Streaming the *excitation* (the per-harmonic sum, the render's biggest
    cost) as well as the cascade is what keeps first-audio ~one block long even for
    an 18 s paragraph.  Non-default lowpass is added by the caller afterwards, so
    here lp_default False means cascade only.  Pulse source (A/B only) is cheap and
    built whole up front."""
    FS = CHIP_RATE
    rng = np.random.default_rng(seed)
    edge = FS * 0.5
    blsaw = source in ('blsaw', 'saw')
    if source_tilt:
        ta = math.exp(-2.0 * math.pi * source_tilt / FS)
        c0 = 1.0 - ta
    if blsaw:
        KMAX = max(1, int(edge / max(float(p.min()), 1e-6)))
        kk = np.arange(1, KMAX + 1)
    else:  # pulse: build + tilt the whole (cheap) source once
        voiced_all = np.zeros(N)
        pc = np.cumsum(p / FS)
        idx = np.where(np.floor(pc[1:]) > np.floor(pc[:-1]))[0] + 1
        voiced_all[idx] = 1.0
        if source_tilt:
            vl = voiced_all.tolist(); yp = 0.0
            for k in range(N):
                yp = c0 * vl[k] + ta * yp
                vl[k] = yp
            voiced_all = np.asarray(vl)
    typrev = 0.0

    # cascade + low-pass coefficients (whole; cheap)
    B1 = []
    B2 = []
    for i in range(nf):
        Bc = np.exp(-np.pi * bw[i] / FS)
        Fc = 2.0 * np.cos(2.0 * np.pi * fc[i] / FS)
        B1.append((Bc * Fc).tolist())
        B2.append((-(Bc * Bc)).tolist())
    y1 = [0.0] * nf
    y2 = [0.0] * nf
    rng_nf = range(nf)
    if lp_default:
        (lb0, lb1, lb2, la1, la2) = _LP2600_SOS[0]
        (mb0, mb1, mb2, ma1, ma2) = _LP2600_SOS[1]
        lz0 = lz1 = mz0 = mz1 = 0.0

    step = block if (block and block > 0) else N
    if step <= 0:
        step = max(1, N)
    a = 0
    while a < N:
        b = min(a + step, N)
        # ---- excitation for [a:b] ----
        if blsaw:
            W = np.clip((edge - np.outer(p[a:b], kk)) / (edge * 0.16), 0.0, 1.0)
            W = W * W * (3.0 - 2.0 * W)
            Smat = np.sin(2.0 * np.pi * np.outer(phase[a:b], kk))
            voiced = -(2.0 / np.pi) * (Smat * (W / kk)).sum(1)
            if source_tilt:
                vl = voiced.tolist(); yp = typrev
                for k in range(len(vl)):
                    yp = c0 * vl[k] + ta * yp
                    vl[k] = yp
                typrev = yp
                voiced = np.asarray(vl)
        else:
            voiced = voiced_all[a:b]
        exc = np.where(noise[a:b], rng.uniform(-noise_gain, noise_gain, b - a), voiced) * amp[a:b]
        # ---- five-formant cascade (+ fused default low-pass) for [a:b] ----
        xl = exc.tolist()
        outb = [0.0] * (b - a)
        for k in range(b - a):
            j = a + k
            v = xl[k]
            for i in rng_nf:
                yn = v + B1[i][j] * y1[i] + B2[i][j] * y2[i]
                y2[i] = y1[i]
                y1[i] = yn
                v = yn
            if lp_default:
                o = lb0 * v + lz0                   # low-pass section 1
                lz0 = lb1 * v - la1 * o + lz1
                lz1 = lb2 * v - la2 * o
                v = mb0 * o + mz0                    # low-pass section 2
                mz0 = mb1 * o - ma1 * v + mz1
                mz1 = mb2 * o - ma2 * v
            outb[k] = v
        yield np.array(outb) * scale                # low-pass linear -> commutes with scale
        a = b


def render_chip_fast(seq, out_rate=CHIP_RATE, source='blsaw', a0=False,
                     ampl_compress=1.0, time_scale=1.0, real=None, pitch_byte=46,
                     pitch_mode='cumulative', seed=12345, noise_gain=0.5, scale=1.0,
                     source_tilt=CHIP_TILT_HZ, lowpass=CHIP_LOWPASS_HZ,
                     flat_pitch=False, furcsa_override=None, **_ignored):
    """Fast whole-utterance render: per-sample continuous interpolation, no a0,
    band-limited excitation, and the five-formant cascade as ONE manual per-sample
    loop (no scipy.lfilter per-call overhead).  Thin wrapper over _render_prep +
    _render_blocks so it shares exactly one code path with render_chip_stream."""
    FS = CHIP_RATE
    amp, p, phase, noise, fc, bw, nf, N = _render_prep(
        seq, ampl_compress=ampl_compress, time_scale=time_scale, real=real,
        pitch_byte=pitch_byte, pitch_mode=pitch_mode, flat_pitch=flat_pitch,
        furcsa_override=furcsa_override)
    if N == 0:
        return np.zeros(0)
    lp_default = bool(lowpass) and abs(lowpass - CHIP_LOWPASS_HZ) < 1e-6
    sig = np.concatenate(list(_render_blocks(amp, p, phase, noise, fc, bw, nf, N,
                                             source, noise_gain, source_tilt, seed,
                                             scale, lp_default, 0)))
    if lowpass and not lp_default:
        from scipy.signal import butter, sosfilt
        sig = sosfilt(butter(4, lowpass, 'low', fs=FS, output='sos'), sig)
    if out_rate != FS:
        from scipy.signal import resample_poly
        g = math.gcd(int(out_rate), FS)
        sig = resample_poly(sig, int(out_rate) // g, FS // g)
    return sig


def render_chip_stream(seq, out_rate=CHIP_RATE, source='blsaw', a0=False,
                       ampl_compress=1.0, time_scale=1.0, real=None, pitch_byte=46,
                       pitch_mode='cumulative', seed=12345, noise_gain=0.5, scale=1.0,
                       source_tilt=CHIP_TILT_HZ, lowpass=CHIP_LOWPASS_HZ,
                       flat_pitch=False, furcsa_override=None, block=4000, **_ignored):
    """Generator form of render_chip_fast: yields the SAME samples in order, in
    ~`block`-sample float chunks, AS they are produced -- so the NVDA driver can
    start playing ~block/CHIP_RATE seconds in while the rest still renders, with
    ZERO change to the audio (one continuous render, one intonation contour, no
    per-piece fades).  Invariant:
        np.concatenate(list(render_chip_stream(seq))) == render_chip_fast(seq)
    Only the default path streams (out_rate == CHIP_RATE and default/off lowpass);
    any other config yields the whole render in a single chunk."""
    FS = CHIP_RATE
    lp_default = bool(lowpass) and abs(lowpass - CHIP_LOWPASS_HZ) < 1e-6
    if out_rate != FS or (lowpass and not lp_default):
        x = render_chip_fast(
            seq, out_rate=out_rate, source=source, a0=a0, ampl_compress=ampl_compress,
            time_scale=time_scale, real=real, pitch_byte=pitch_byte, pitch_mode=pitch_mode,
            seed=seed, noise_gain=noise_gain, scale=scale, source_tilt=source_tilt,
            lowpass=lowpass, flat_pitch=flat_pitch, furcsa_override=furcsa_override)
        if len(x):
            yield x
        return
    amp, p, phase, noise, fc, bw, nf, N = _render_prep(
        seq, ampl_compress=ampl_compress, time_scale=time_scale, real=real,
        pitch_byte=pitch_byte, pitch_mode=pitch_mode, flat_pitch=flat_pitch,
        furcsa_override=furcsa_override)
    if N == 0:
        return
    yield from _render_blocks(amp, p, phase, noise, fc, bw, nf, N, source,
                              noise_gain, source_tilt, seed, scale, lp_default, block)
