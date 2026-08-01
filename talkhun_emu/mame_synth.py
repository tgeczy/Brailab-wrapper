# -*- coding: utf-8 -*-
"""
MAME's MEA-8000 algorithm, followed exactly, driven by our captured frames.

Why this file exists: MAME's `mea8000.cpp` is a validated emulation of the chip
BraiLab 4 actually contained -- `MEA8000(config, "mea8000", 3'840'000)` in the
homelab driver, credited to the same Lukacs brothers who built the BraiLab PC's
parallel adapter.  The PCF-8200 in the PC is that chip's successor.  So rather
than keep tuning a reconstruction against TTS.dll (a basic 2021 reimplementation),
this renders through MAME's own signal path for comparison.

Structural differences from synth.py, all taken from mea8000.cpp:
  * the filters run AT THE CHIP RATE, and the output is linearly interpolated
    x8 -- not oversampled synthesis.  The timer fires at 8*F0 but
    `compute_sample()` runs "only every 8-th time"; the rest are interpolated.
    That crude upsampling is part of the chip's sound.
  * resonators are UNSCALED (`next = input + b*out - c*last`), no a0 term.
    That is safe here precisely because the filters stay at one fixed rate.
  * four formants, the fourth FIXED at 3500 Hz (`fm4_table[1] = { 3500 }`).
  * excitation is a sawtooth at `pitch` Hz, or noise, scaled by ampl/32.
  * output clips at +/-32767 rather than being normalised.

Kept from our own work because they are established facts about this data:
codes index the tables directly (no +1), and PI is a per-frame offset from the
utterance anchor rather than a cumulative increment.
"""

import math

import numpy as np
from scipy.signal import decimate, lfilter

from pcf8200 import (F1_TAB, F2_TAB, F3_TAB, BW_TAB, FS_TAB, FD_MULT,
                     decode_frame, decode_control)
from synth import (AMPL_TAB, PI_TAB, PI_NOISE, PITCH_HZ_PER_UNIT, CLIP,
                   TARGET_RMS, _SPEECH_FLOOR, SAMPLE_RATE, NOISE_GAIN)

#: MEA-8000's fourth formant is a single fixed value.
FM4_FIXED = 3500.0

#: MAME interpolates its parameters continuously; we hold them over a short
#: block so scipy can do the IIR, which is indistinguishable at this size.
BLOCK = 4

#: MAME's output upsampling: linear interpolation, 8 steps per computed sample.
SUPERSAMPLING = 8

#: High-pass corner modelling the BraiLab's own loudspeaker, in Hz.
#: The chip fed a small driver in a plastic case, which radiates nothing much
#: at the bottom.  Synthesised flat we carry 37% of the energy below 150 Hz
#: against the real engine's 17.6%, starving the 150-600 Hz body where a voice
#: actually sits.  Swept against real output: 150 Hz halves the band-profile
#: error (44.5 -> 22.4) and puts the 450-600 Hz band at 33.6% vs its 33.5%.
#: DISABLED ANYWAY: Tomi picked the un-filtered render, which "gives it more of
#: a chest, 100%".  The spectral match improved but the voice got thinner, so
#: the measurement was optimising away something the ear wants.  Kept as a knob.
CABINET_HZ = None


def _bl_saw(phase, f0, fs, n):
    """Band-limited sawtooth, additive, phase-continuous across blocks.

    MAME generates its sawtooth directly at the chip rate, which is not band
    limited: every harmonic above Nyquist folds back as INHARMONIC content.
    Inharmonic partials shimmer and beat against the real ones -- heard as the
    voice being "swirly" -- and they land high in the spectrum, which also
    reads as "tinny".  Summing only the harmonics that fit below Nyquist gives
    the same waveform without the fold-back.
    """
    t = phase + (f0 / fs) * np.arange(n)
    nh = max(1, int((fs * 0.5) / max(f0, 1.0)))
    x = np.zeros(n)
    for h in range(1, nh + 1):
        x += np.sin(2.0 * np.pi * h * t) / h
    return (-2.0 / np.pi) * x, float((phase + (f0 / fs) * n) % 1.0)


def _bl_pulse(phase, f0, fs, n, width=0.12):
    """Band-limited pulse train -- the datasheet's "programmable pulse generator".

    MAME approximates the voiced source with a sawtooth, whose harmonics fall
    at 1/h.  That puts far too much energy in the fundamental: measured against
    the real engine our 0-150 Hz band held 37% against its 17.6%, while the
    150-600 Hz body where a voice lives was correspondingly starved.  A pulse
    has a flatter harmonic series, and `width` sets how flat -- narrow pulses
    are brighter, wide ones roll off sooner.
    """
    t = phase + (f0 / fs) * np.arange(n)
    nh = max(1, int((fs * 0.5) / max(f0, 1.0)))
    x = np.zeros(n)
    for h in range(1, nh + 1):
        # cosine series, tapered so the pulse has finite width rather than
        # being a raw impulse (which would be maximally bright and harsh)
        x += math.exp(-((h * width) ** 2)) * np.cos(2.0 * np.pi * h * t)
    peak = np.max(np.abs(x)) or 1.0
    return x / peak, float((phase + (f0 / fs) * n) % 1.0)


def _mame_resonator(f, bw, fs):
    """mea8000.cpp's filter_step coefficients, unscaled exactly as MAME has them."""
    r = math.exp(-math.pi * bw / fs)
    return 2.0 * r * math.cos(2.0 * math.pi * f / fs), -(r * r)


def _formants(d, furcsa=False, female_scale=1.0, bw_scale=1.0):
    """PCF frame fields mapped onto MEA-8000's four formants.

    B1/B2 are 3-bit on the PCF-8200 against MAME's 2-bit field, so they are
    reduced by one bit rather than invented.
    """
    out = [
        (float(F1_TAB[min(d['F1'], 31)]), BW_TAB[min(d['B1'] >> 1, 3)] * bw_scale),
        (float(F2_TAB[min(d['F2'], 31)]), BW_TAB[min(d['B2'] >> 1, 3)] * bw_scale),
        (float(F3_TAB[min(d['F3'], 7)]), BW_TAB[d['B3']] * bw_scale),
        (FM4_FIXED, BW_TAB[d['B4']] * bw_scale),
    ]
    if furcsa:
        out = [(f * female_scale, bw) for f, bw in out]
    return out


def render(seq, sample_rate=SAMPLE_RATE, furcsa=None, fs_code=None,
           pitch_byte=46, seed=12345, normalize='fixed', female_scale=1.18,
           bw_scale=1.0, interpolate_out=True, band_limited=True,
           source='saw', pulse_width=0.12, cabinet_hz=CABINET_HZ,
           noise_gain=None, noise_attack=0.4):
    """Render a captured adapter stream through MAME's MEA-8000 signal path."""
    if furcsa is None:
        furcsa = any(decode_control(v)['furcsa'] for k, v in seq if k == 'ctrl'
                     and not decode_control(v)['stop'])
    if fs_code is None:
        starts = [decode_control(v) for k, v in seq if k == 'ctrl'
                  and not decode_control(v)['stop']]
        fs_code = starts[0]['fs'] if starts else 0

    base_ms = FS_TAB[fs_code][1]
    rng = np.random.default_rng(seed)
    zi = [np.zeros(2) for _ in range(4)]
    phase = 0.0
    anchor = pitch_byte * PITCH_HZ_PER_UNIT
    prev = None
    out = []

    for kind, val in seq:
        if kind == 'pitch':
            anchor = val * PITCH_HZ_PER_UNIT
            continue
        if kind != 'frame':
            continue
        d = decode_frame(val)
        cur = {
            'formants': _formants(d, furcsa, female_scale, bw_scale),
            'ampl': AMPL_TAB[d['AM']] / 1000.0,
            'noise': d['PI'] == PI_NOISE,
        }
        if prev is None:
            prev = dict(cur, ampl=0.0)

        n = max(1, int(round(base_ms * FD_MULT[d['FD']] * sample_rate / 1000.0)))
        pitch = min(max(anchor + PI_TAB[d['PI']], 40.0), 400.0)

        pos = 0
        while pos < n:
            m = min(BLOCK, n - pos)
            t0 = (pos + m * 0.5) / n
            amp = prev['ampl'] + (cur['ampl'] - prev['ampl']) * t0

            if cur['noise']:
                # Frication needs its own level.  Broadband noise picks up gain
                # at EVERY resonance of the cascade where a harmonic series
                # mostly sits off-peak, so at equal drive the fricatives come
                # out on top -- heard as the s in "es" being stabby.
                ng = NOISE_GAIN if noise_gain is None else noise_gain
                x = rng.uniform(-ng, ng, m)
                if noise_attack and not (prev.get('noise')):
                    # first block of a fricative: ramp in, so an affricate's
                    # burst does not start as a step discontinuity
                    x = x * np.linspace(noise_attack, 1.0, m)
            elif source == 'pulse':
                x, phase = _bl_pulse(phase, pitch, sample_rate, m, pulse_width)
            elif band_limited:
                x, phase = _bl_saw(phase, pitch, sample_rate, m)
            else:
                step = pitch / sample_rate
                ph = phase + step * np.arange(m)
                x = 2.0 * (ph % 1.0) - 1.0
                phase = (phase + step * m) % 1.0
            x = x * amp

            for i in range(4):
                pf, pbw = prev['formants'][i]
                cf, cbw = cur['formants'][i]
                b1, b2 = _mame_resonator(pf + (cf - pf) * t0,
                                         pbw + (cbw - pbw) * t0, sample_rate)
                x, zi[i] = lfilter([1.0], [1.0, -b1, -b2], x, zi=zi[i])

            out.append(x)
            pos += m

        prev = cur

    if not out:
        return np.zeros(0, dtype=np.int16)
    sig = np.concatenate(out)

    if interpolate_out:
        # MAME computes one sample per chip period and linearly interpolates
        # the 7 between.  Upsampling and then taking every 8th sample is the
        # identity, which is what this used to do -- nothing.  To actually get
        # the character, interpolate up and low-pass on the way back down, so
        # the linear-interpolation response is applied rather than undone.
        up = np.interp(np.arange(len(sig) * SUPERSAMPLING) / SUPERSAMPLING,
                       np.arange(len(sig)), sig)
        sig = decimate(up, SUPERSAMPLING, ftype='fir', zero_phase=True)

    if cabinet_hz:
        # The real BraiLab spoke through a small speaker in a plastic case,
        # which rolls off hard at the bottom.  Without it our output carries
        # 37% of its energy below 150 Hz against the real engine's 17.6%,
        # while the 150-600 Hz body a voice lives in is correspondingly thin --
        # the fundamental is there but the box would never have radiated it.
        from scipy.signal import butter, sosfilt
        sos = butter(2, cabinet_hz / (0.5 * sample_rate), btype='high',
                     output='sos')
        sig = sosfilt(sos, sig)

    if normalize == 'none':
        return sig
    peak = float(np.max(np.abs(sig)))
    if peak <= 0:
        return np.zeros(len(sig), dtype=np.int16)
    speech = sig[np.abs(sig) > peak * _SPEECH_FLOOR]
    level = float(np.sqrt(np.mean(speech ** 2))) if speech.size else peak
    if level > 0:
        sig = sig * (TARGET_RMS / level)
    return np.clip(sig, -CLIP, CLIP).astype(np.int16)
