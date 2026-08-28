# -*- coding: utf-8 -*-
"""
A software PCF-8200: turn captured frames into audio.

Ported from MAME's `mea8000.cpp` (Antoine Miné), which emulates the MEA-8000 --
the same formant architecture and, as our capture confirms, the same frequency
tables.  What the PCF-8200 adds is a fifth formant for male speech and a wider
bandwidth field.

Signal path, per the datasheet and MAME:
    excitation (sawtooth at F0, or noise when PI==16)
      -> scaled by the frame amplitude
      -> cascade of second-order resonators, one per formant
All parameters interpolate linearly across a frame, which is what stops the
output sounding stepped.

Pitch is NOT carried in the frames.  The frame's PI field is an increment; the
absolute value arrives as a separate one-byte write at utterance start (the
second transaction of 0x1d2c), exactly like MEA-8000's pitch register.  MAME
uses 2 Hz per unit at its 8 kHz sample rate; BraiLab's chip runs at 10 kHz, so
the scale here is 2.5 Hz per unit -- which puts the default 42+4=46 at ~115 Hz
settling toward the 107.3 Hz measured from real BraiLab audio.

Reconstructed tables are marked RECONSTRUCTED: the Hz values for the PCF-8200's
wider bandwidth field and for F4/F5 are not in the public MAME tables, so they
are geometric fits anchored on the four bandwidths MAME confirms.  When a local
set of measured tables is available the emulator uses those instead (see
pcf8200.load_real_tables).
"""

import math

import numpy as np
from scipy.signal import decimate, lfilter

import pcf8200
from pcf8200 import (F1_TAB, F2_TAB, F3_TAB, BW_TAB, FS_TAB, FD_MULT,
                     decode_frame, decode_control)

#: BraiLab's PCF-8200 output rate, measured from captured hardware audio.
SAMPLE_RATE = 10000

#: Synthesis runs this many times faster than SAMPLE_RATE, then decimates.
#: A sawtooth generated directly at 10 kHz is not band limited: every harmonic
#: above 5 kHz folds back into the speech band as inharmonic hash, which is
#: audible as the render sounding brighter and harsher than BraiLab does.
#: Generating at 8x and decimating through an anti-alias filter removes it --
#: and 80 kHz is not an arbitrary choice, it is the rate the datasheet says the
#: chip upsamples its own output to.
OVERSAMPLE = 8
SYNTH_RATE = SAMPLE_RATE * OVERSAMPLE

#: MEA-8000 takes 2 Hz per pitch unit at 8 kHz; scale with the sample rate.
PITCH_HZ_PER_UNIT = 2.0 * SAMPLE_RATE / 8000.0

#: Amplitude, x1000 (MAME `ampl_table`).
AMPL_TAB = [0, 8, 11, 16, 22, 31, 44, 62,
            88, 125, 177, 250, 354, 500, 707, 1000]

#: Pitch increment in Hz per frame (MAME `pi_table`).  Index 16 means the frame
#: is unvoiced and the excitation switches to noise.
PI_TAB = [0, 1, 2, 3, 4, 5, 6, 7,
          8, 9, 10, 11, 12, 13, 14, 15,
          0, -15, -14, -13, -12, -11, -10, -9,
          -8, -7, -6, -5, -4, -3, -2, -1]
PI_NOISE = 16

#: RECONSTRUCTED.  B1/B2 are 3-bit on the PCF-8200 where MAME's are 2-bit, so
#: this interleaves geometric means between the four known values; the even
#: entries reproduce BW_TAB exactly.
BW8_TAB = [726, 474, 309, 197, 125, 79, 50, 32]

#: RECONSTRUCTED.  F4 measured 3300-3390 Hz across every Hungarian vowel in the
#: LPC work, so this is a narrow spread around that; F5 sits above it.
F4_TAB = [3000, 3150, 3300, 3400, 3500, 3650, 3800, 4000]
F5_TAB = [4200, 4700]

#: RECONSTRUCTED, and the single most uncertain number here -- calibrate by ear.
#: M/F=1 selects the chip's female quantization table, whose Hz values are not
#: in the public MAME tables.  The physics, though: a female vocal tract
#: is roughly 15-20% shorter, so the same codes must map to proportionally
#: higher formants.  Applying that scale to F1-F4 while keeping the male F0 --
#: pitch is a separate register the M/F bit does not touch -- gives female
#: formants under a male voice, which is exactly the mismatch that would earn
#: the name "furcsa" (odd) rather than "female".
FEMALE_SCALE = 1.18

#: Peak clip, matching MAME's saturation rather than letting the cascade blow up.
CLIP = 32767

#: Target RMS of the speech (not the silence) in a rendered utterance.
#: A cascade of resonators has an overall gain that depends on where the
#: formants sit -- /u/, whose F1 and F2 are both low, loses far more energy
#: through the upper resonators than /i/ does -- so raw output level swings
#: ~30 dB between utterances.  For a screen reader that is the thing to fix:
#: matching loudness means matching RMS, not peak.  Chosen to leave room for
#: the ~7x peak-to-RMS ratio of this material, and set to the level TTS.dll
#: itself renders at -- measured 4588 RMS against our 4000 on the same
#: sentence, which Tomi heard as the emulator sitting slightly quiet.
TARGET_RMS = 4600.0

#: Fraction of peak below which a sample counts as silence for that measurement.
_SPEECH_FLOOR = 0.05

#: One-pole lowpass on the voiced excitation, in Hz; None disables it.
#: A raw sawtooth's harmonics fall at -6 dB/octave, but a real glottal source
#: falls at about -12, and the chip's output stage filters further.  Without
#: this the upper formants come out far too strong -- measured against real
#: TTS.dll output the emulator carried 23x its energy above 2 kHz, which is
#: what Tomi heard as a "squished headsize", a head too small for the voice.
#: RECALIBRATED at CODEC_OFFSET=0: the deep 800 Hz value was largely
#: compensating for the +1 offset bug (it was heard as "8K phone quality" once
#: that was fixed).  With the offset gone the sweep is nearly flat and gentle
#: wins: none 10.04 dB LSD, 3000 Hz 10.03, 800 Hz 10.36.  Tomi then picked the
#: no-tilt render by ear, so it is off entirely.
SOURCE_TILT_HZ = None

#: Exponent applied to the frame amplitude, compressing its dynamic range.
#: MAME's ampl_table spans ~42 dB across the 4-bit AM field, which makes the
#: loudness swing noticeably through an utterance.  TTS.dll's own amplitude
#: table steps at 0.75 dB, suggesting the real engine works on a gentler scale.
#: 1.0 = MAME verbatim; lower values compress (0.5 halves the range in dB).
AMPL_COMPRESS = 1.0

#: Divide out the formant cascade's own gain so loudness follows the frame's
#: AM field instead of drifting with formant position.
LEVEL_TRACK = True

#: Aspiration noise mixed into the VOICED source, relative to the sawtooth.
ASPIRATION = 0.0

#: How the frame's PI field moves the pitch.
#:   'offset'     -- PI is a per-frame deviation from the utterance's anchor
#:                   pitch, recomputed each frame.  THIS IS THE CHIP'S BEHAVIOUR.
#:   'cumulative' -- MAME's MEA-8000 model, pitch += PI every frame.
#: MAME accumulates, and copying that gave a 37-42% monotonic pitch sag -- heard
#: by Tomi as "a broken cassette", a tape slowing down.  That verdict was real
#: but the experiment was not: it was measured on "mama.", a SINGLE intonation
#: unit, where there is no second pitch mark to reload the register and the
#: increments can only pile up.  On multi-clause text each pitch mark reloads
#: the anchor, every clause gets its own contour, and nothing accumulates
#: across the utterance.  Measured against TTS.dll on the same sentences,
#: cumulative reproduces its shape including the clause-final fall (ours 71 Hz
#: against its 70), where offset renders a dead-flat plateau spanning 4 Hz
#: against TTS.dll's 157.  The PI field is almost entirely 0 and +/-1, so as
#: offsets it can only ever move +/-4 Hz -- it is an increment, which is what
#: the MEA-8000 pitch register does: load the anchor, add PI each frame.
#: Measuring the real engine settled it: its F0 is essentially FLAT (mama.
#: 119/116/115/111/116/119/116/115/115, mean 116, 7% spread) and sits right on
#: the anchor of 46 units x 2.5 Hz = 115 Hz.  With PI as an offset the dominant
#: codes 30 and 31 map to -2 and -1 Hz, i.e. 113-114 Hz -- flat, and matching.
PITCH_MODE = 'cumulative'

#: Multiplier on every formant bandwidth.  BW8_TAB is reconstructed, and if the
#: real values are wider than assumed the cascade turns into a row of sharp
#: isolated peaks with deep valleys between them -- which is what "thin" sounds
#: like.  Measured against real TTS.dll output the emulator was 11x less
#: spectrally flat (0.0006 vs 0.0067) with deeper contrast, and short of energy
#: at BOTH ends of the band: the signature of bandwidths that are too narrow.
#:
#: That reasoning was WRONG, and Tomi's ear caught it: widening the bandwidths
#: smears neighbouring formants into each other, which he heard immediately as
#: "formant squishyness" -- the same artefact TGSpeechBox produces at formant
#: sharpness zero.  His account of the real machine is decisive: **BraiLab did
#: no bandwidth narrowing or squishing at all in normal mode, and only slight
#: narrowing in furcsa.**  So the table values stand unscaled.
BW_SCALE = 1.0

#: Bandwidth multiplier applied only in furcsa mode.  Per Tomi, furcsa is where
#: BraiLab did narrow its formants slightly -- narrower bandwidth sharpens each
#: resonance, which is part of what makes the voice sound pinched.
FURCSA_BW_SCALE = 0.85

#: Level of the noise (fricative) excitation relative to the voiced sawtooth.
#: The source tilt only touches the voiced path -- frication really is
#: broadband -- but that means the tilt drains vowel power while fricatives
#: keep all of theirs, and they end up peaking over the vowels.  Deeper than
#: that: broadband noise picks up gain at EVERY resonance peak of the cascade,
#: where a harmonic series mostly sits off-peak -- so at equal excitation the
#: fricatives come out on top.  In the real engine they are far QUIETER than
#: the vowels (in 'sas.' they fall below an 8%-of-peak measurement threshold
#: entirely, while ours were the loudest frames in the utterance).  Matching
#: that exactly (~0.07) would make them nearly inaudible, and TTS.dll may
#: itself under-render frication -- 0.2 puts them clearly below the vowels
#: (ratio 0.78) while keeping them present; the rest is Tomi's ear.
#: 2026-07-31, measured properly on the MAME path: the real engine's
#: fricative/vowel RMS ratio is 0.40 and ours was 0.81 -- exactly twice as hot,
#: which Tomi heard as the s in "es" coming out stabby.  0.35 lands near 0.46,
#: about as close as this crude ratio resolves.
NOISE_GAIN = 0.10

#: Codec-to-table index offset: the PCF-8200's codes index the MEA-8000 tables
#: DIRECTLY.  The +1 used earlier came from matching thesis codec values
#: (/a/ F1=21, F2=13 -- TALKHUN0's diad data) against TTS.dll audio (625/988 Hz
#: -- BINADATA's diad data); once those were proven different authorings the
#: inference collapsed, and the A/B settled it: one table step is ~6%, the +1
#: render was heard as "slightly furcsa, like 1.05", and the offset-0 renders
#: were picked as closest to the original hardware.
CODEC_OFFSET = 0

#: How many formants the male voice uses.  The datasheet says five ("Five
#: formants are needed for male speech and four for female speech") and the
#: frame does carry an F5 bit, which is decoded -- but F5_TAB below is invented,
#: there being no published Hz values, and measured against real TTS.dll output
#: A log-spectral-distance comparison once favoured 4 (8.49 dB vs 11.99), and
#: that was a mistake: LSD measures average spectral SHAPE, not peakiness, and
#: peakiness is what "thin" actually is.  On spectral flatness -- energy between
#: the formants rather than only at them -- five formants score 4x closer to the
#: real engine (0.00145 vs 0.00035), and Tomi picked a five-formant render by
#: ear.  Optimise against the metric that matches the complaint.
MALE_FORMANTS = 5

#: Formant coefficients are recomputed and the parameters re-interpolated every
#: BLOCK samples.  The datasheet interpolates parameters 8x per 12.8 ms frame,
#: i.e. every 1.6 ms -- but holding the resonator COEFFICIENTS constant for
#: 1.6 ms at the 80 kHz synthesis rate (128 samples) and then stepping them
#: makes each IIR section transient at every boundary, heard as a "swirl" over
#: fast formant transitions (/r/, consonant clusters).  Updating 8x finer, every
#: 0.2 ms, smooths the coefficient trajectory and removes it (confirmed by ear);
#: the parameter TARGETS still move on the datasheet's 8-steps-per-frame grid.
#: Costs ~5x realtime vs ~18x, still well above real time for a screen reader.
BLOCK = int(round(0.0002 * SYNTH_RATE))

#: Band-limit the voiced excitation to the 5 kHz speech band.  A naive sawtooth
#: sampled even at 80 kHz still carries harmonics above the 40 kHz synthesis
#: Nyquist that fold back into 0-5 kHz as inharmonic partials -- heard as a
#: "swirl" over the voice, worst at steady pitch (the folded partials are fixed
#: frequencies that beat against the steady harmonics).  Summing only the
#: harmonics up to the band edge removes it at the source: measured inharmonic
#: energy in 2-5 kHz drops from ~12% to ~0.2%, cheaper than raising oversampling.
BANDLIMIT = True


def _resonator(f, bw, fs):
    """Klatt second-order resonator, normalised to unity gain at DC.

        y[n] = a0 x[n] + b1 y[n-1] + b2 y[n-2]
        b1 = 2r cos(2*pi*f/fs),  b2 = -r^2,  a0 = 1 - b1 - b2

    The a0 term matters more than it looks.  MAME omits it, which is fine at
    one fixed sample rate but not across rates: without it a stage's gain is
    ~1/(1-r)^2 at low frequencies, and r rises towards 1 as fs rises, so
    oversampling silently rebalances the cascade towards the low formants.
    That is not theoretical -- at 8x it buried F3 (2842 Hz) completely, and
    the /a/ lost its third formant.  Normalising at DC makes each stage
    rate-independent; the resonance peak still rises with Q, as it should.

    (Normalising at the resonance peak instead is worse than either: the
    scalar then jumps between interpolation blocks, desynchronising the
    filter's retained state and audibly smearing the formants.)
    """
    r = math.exp(-math.pi * bw / fs)
    b1 = 2.0 * r * math.cos(2.0 * math.pi * f / fs)
    b2 = -(r * r)
    return 1.0 - b1 - b2, b1, b2


def _cascade_gain(formants, f0, fs, nharm=None, source_tilt=None,
                  band_hz=SAMPLE_RATE / 2.0):
    """RMS gain the formant cascade applies to the voiced source at `f0`.

    With DC-normalised resonators the cascade's overall gain depends on where
    the formants happen to sit, so loudness drifts as the vowels change rather
    than following the frame's AM field -- heard as the volume fluctuating
    through an utterance.  Dividing this out puts AM back in charge.

    `source_tilt` must be the same one-pole cutoff the excitation is actually
    filtered with.  Model the source as a bare sawtooth while rendering a
    tilted one and this correction stops matching: it then over-corrects
    low-F1/high-F2 vowels by several dB, which is heard as one syllable of a
    word jumping in volume.
    """
    if f0 <= 0:
        return 1.0
    # Integrate over the band that survives to the output, not over the
    # oversampled one, and far enough up to actually include F3 and F4.  A
    # fixed 24 harmonics reaches only ~2.8 kHz at this pitch, so the correction
    # never saw the upper formants: vowels with a high F2 came out several dB
    # louder than their AM field asks for, heard as one syllable of a word
    # jumping in volume.
    limit = min(band_hz, fs * 0.5)
    if nharm is None:
        nharm = max(8, int(limit / f0))
    tot = 0.0
    for h in range(1, nharm + 1):
        f = h * f0
        if f >= limit:
            break
        g = 1.0 / h                       # sawtooth harmonic falls as 1/h
        if source_tilt:
            g /= math.hypot(1.0, f / source_tilt)
        for ff, bw in formants:
            r = math.exp(-math.pi * bw / fs)
            b1 = 2.0 * r * math.cos(2.0 * math.pi * ff / fs)
            b2 = -(r * r)
            w = 2.0 * math.pi * f / fs
            re = 1.0 - b1 * math.cos(w) - b2 * math.cos(2.0 * w)
            im = b1 * math.sin(w) + b2 * math.sin(2.0 * w)
            g *= (1.0 - b1 - b2) / (math.hypot(re, im) + 1e-12)
        tot += g * g
    return math.sqrt(tot) + 1e-12


#: Fallback ladders, one list per formant, matching the pre-ground-truth code:
#: B1/B2 shared the reconstructed 3-bit table, B3-B5 the 2-bit MAME table.
_FB_MALE_F = [F1_TAB, F2_TAB, F3_TAB, F4_TAB, F5_TAB]
_FB_MALE_B = [BW8_TAB, BW8_TAB, BW_TAB, BW_TAB, BW_TAB]
_FB_AMPL = [a / 1000.0 for a in AMPL_TAB]


def active_tables(real):
    """The (male_F, male_B, female_F, female_B, ampl, pi, hz_per_unit) bundle.

    In real mode the values come from the chip's own quantization ROM (loaded
    by pcf8200 from the external measured tables); female_F/female_B then carry
    the real four-formant female table.  In fallback mode female_F
    is None and furcsa is done by the FEMALE_SCALE shift, exactly as before.
    """
    if real and pcf8200.REAL is not None:
        R = pcf8200.REAL
        return (R['male_F'], R['male_B'], R['female_F'], R['female_B'],
                R['ampl'], R['pi'], R['pitch_hz_per_unit'])
    return (_FB_MALE_F, _FB_MALE_B, None, None,
            _FB_AMPL, PI_TAB, PITCH_HZ_PER_UNIT)


def frame_params(d, tables, furcsa=False, female_scale=FEMALE_SCALE,
                 codec_offset=CODEC_OFFSET, bw_scale=None,
                 ampl_compress=None):
    """Target parameters for one decoded frame, using the given table bundle."""
    male_F, male_B, female_F, female_B, ampl, pi = tables
    off = codec_offset
    bs = BW_SCALE if bw_scale is None else bw_scale
    ampl_compress = (AMPL_COMPRESS if ampl_compress is None else ampl_compress)
    if furcsa and female_F is not None:
        # Real furcsa: M/F=1 selects the chip's four-formant FEMALE quantization
        # table, the codes re-read through a shorter vocal tract.
        # The diads were authored for the five-formant male model, so reading
        # them female is the whole trick -- and with the real table there is no
        # scalar shift or bandwidth hack, the chip's own values stand.
        formants = [
            (female_F[0][min(d['F1'], 31)], female_B[0][d['B1']] * bs),
            (female_F[1][min(d['F2'], 31)], female_B[1][d['B2']] * bs),
            (female_F[2][min(d['F3'], 7)],  female_B[2][d['B3']] * bs),
            (female_F[3][min(d['F4'], 7)],  female_B[3][d['B4']] * bs),
        ]
    else:
        formants = [
            (male_F[0][min(d['F1'] + off, 31)], male_B[0][d['B1']] * bs),
            (male_F[1][min(d['F2'] + off, 31)], male_B[1][d['B2']] * bs),
            (male_F[2][min(d['F3'] + off, 7)],  male_B[2][d['B3']] * bs),
            (male_F[3][min(d['F4'], 7)],        male_B[3][d['B4']] * bs),
            (male_F[4][d['F5']],                male_B[4][d['B5']] * bs),
        ]
        if furcsa:
            # Fallback furcsa (no real female table): shift the male formants up
            # and narrow them -- the reconstruction we calibrated by ear.
            formants = [(f * female_scale, bw * FURCSA_BW_SCALE)
                        for f, bw in formants[:4]]
    return {
        'formants': formants,
        'ampl': (ampl[d['AM']]) ** ampl_compress,
        'pi': pi[d['PI']],
        'noise': d['PI'] == PI_NOISE,
    }


def render(seq, sample_rate=SAMPLE_RATE, furcsa=None, fs_code=None,
           pitch_byte=46, seed=12345, normalize='fixed',
           oversample=OVERSAMPLE, female_scale=FEMALE_SCALE,
           nformants_override=None, source_tilt=SOURCE_TILT_HZ,
           codec_offset=CODEC_OFFSET, flat_pitch=False,
           noise_gain=None, bw_scale=None, aspiration=None,
           pitch_mode=None, level_track=True, ampl_compress=None,
           real=None, bandlimited=None, soft_start=True):
    """Render a captured adapter stream to int16 PCM at `sample_rate`.

    `seq` is what Talkhun.capture() returns: ('pitch', b), ('ctrl', bytes) and
    ('frame', bytes) in the order the engine sent them.  A start control write
    supplies furcsa and the speed code, and each intonation unit re-sends its
    own pitch, so all of that is followed as the stream goes by.

    Synthesis happens at `oversample` times `sample_rate` and is decimated
    through an anti-alias filter, so the sawtooth's harmonics above the chip's
    5 kHz band do not fold back in.
    """
    synth_rate = sample_rate * oversample
    # Settle the filter shape up front: furcsa changes the formant count, and
    # rebuilding the cascade mid-utterance would drop its state.
    if furcsa is None:
        furcsa = any(decode_control(v)['furcsa']
                     for k, v in seq if k == 'ctrl'
                     and not decode_control(v)['stop'])
    if fs_code is None:
        starts = [decode_control(v) for k, v in seq if k == 'ctrl'
                  and not decode_control(v)['stop']]
        fs_code = starts[0]['fs'] if starts else 0

    # Real tables when present (the chip's own ROM); fallback otherwise.  In
    # real mode the codes index the chip ROM directly, so the offset is 0.
    real = pcf8200.REAL_TABLES if real is None else real
    tables = active_tables(real)
    ptables, hz_per_unit = tables[:6], tables[6]
    eff_offset = 0 if real else codec_offset
    bl = BANDLIMIT if bandlimited is None else bandlimited

    base_ms = FS_TAB[fs_code][1]
    nformants = nformants_override or (4 if furcsa else MALE_FORMANTS)
    rng = np.random.default_rng(seed)

    # Filter state, one biquad per formant.
    zi = [np.zeros(2) for _ in range(nformants)]
    # Source tilt is one pole, carried across blocks like the formants are.
    tilt_a = (math.exp(-2.0 * math.pi * source_tilt / synth_rate)
              if source_tilt else None)
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
        f = val
        d = decode_frame(f)
        cur = frame_params(d, ptables, furcsa, female_scale, eff_offset,
                           bw_scale, ampl_compress)
        if prev is None:
            # First frame: optionally ramp amplitude up from zero.  The chip's
            # own reset does soften the onset, but a full 12.8 ms ramp on top of
            # the (unavoidable) filter warm-up is an audible fade-in at the head
            # of every utterance.  soft_start=False plays the first frame at its
            # real level, leaving only the short filter warm-up.
            prev = dict(cur, ampl=0.0) if soft_start else dict(cur)
        if level_track:
            cur['gain'] = _cascade_gain(cur['formants'][:nformants],
                                        anchor, synth_rate,
                                        source_tilt=source_tilt)
            prev.setdefault('gain', cur['gain'])
        else:
            cur['gain'] = prev['gain'] = 1.0

        n = max(1, int(round(base_ms * FD_MULT[d['FD']] * synth_rate / 1000.0)))
        # The frame's PI is a pitch increment applied across the frame.
        # flat_pitch pins F0 at the utterance's absolute pitch instead --
        # TTS.dll behaves that way (its pitch is an inert stub), so this
        # isolates the intonation contour when A/B-ing against it.
        if flat_pitch:
            pitch_target = anchor
        elif (PITCH_MODE if pitch_mode is None else pitch_mode) == 'cumulative':
            pitch_target = pitch + cur['pi'] * FD_MULT[d['FD']]
            pitch_target = min(max(pitch_target, 40.0), 400.0)
        else:
            # PI deviates from the anchor; it does not accumulate.
            pitch_target = min(max(anchor + cur['pi'], 40.0), 400.0)

        pos = 0
        while pos < n:
            m = min(BLOCK, n - pos)
            t0 = (pos + m * 0.5) / n              # block midpoint
            amp = prev['ampl'] + (cur['ampl'] - prev['ampl']) * t0
            # divide out the cascade's own gain so level follows AM
            amp /= prev['gain'] + (cur['gain'] - prev['gain']) * t0
            p = pitch + (pitch_target - pitch) * t0

            if cur['noise']:
                ng = NOISE_GAIN if noise_gain is None else noise_gain
                x = rng.uniform(-ng, ng, m)
            else:
                # Sawtooth at p Hz with phase carried across blocks, so there
                # is no discontinuity at a block or frame boundary.
                step = p / synth_rate
                ph = phase + step * np.arange(m)
                phase = (phase + step * m) % 1.0
                if bl:
                    # Band-limited sawtooth: sum harmonics only to the 5 kHz band
                    # edge, so none fold back as inharmonic swirl.  Same 1/k
                    # rolloff as the ramp, so the cascade-gain correction holds.
                    # The top harmonics are raised-cosine faded toward the edge,
                    # so one entering/leaving as the pitch drifts does so smoothly
                    # instead of snapping on at a block boundary (an audible tick).
                    edge = sample_rate * 0.5
                    kmax = max(1, int(edge / max(p, 1e-6)) + 1)
                    kk = np.arange(1, kmax + 1)
                    w = np.clip((edge - kk * p) / (edge * 0.16), 0.0, 1.0)
                    w = w * w * (3.0 - 2.0 * w)
                    x = -(2.0 / np.pi) * (
                        np.sin(2.0 * np.pi * np.outer(ph, kk)) * (w / kk)).sum(1)
                else:
                    x = 2.0 * (ph % 1.0) - 1.0
                asp = ASPIRATION if aspiration is None else aspiration
                if asp:
                    # A perfectly periodic source leaves near-silence between
                    # harmonics, which measures as extreme spectral peakiness
                    # and is heard as thin and buzzy.  Real voicing carries
                    # aspiration, and the chip's 11-bit DAC adds a noise floor
                    # of its own; a little breath fills the gaps.
                    x = x + rng.uniform(-asp, asp, m)
                if tilt_a is not None:
                    # Only the voiced source is tilted; frication really is
                    # broadband, and rolling it off would dull the sibilants.
                    x, tilt_zi = lfilter([1.0 - tilt_a], [1.0, -tilt_a], x,
                                         zi=tilt_zi)
            x = x * amp

            for i in range(nformants):
                pf, pbw = prev['formants'][i] if i < len(prev['formants']) \
                    else cur['formants'][i]
                cf, cbw = cur['formants'][i]
                fq = pf + (cf - pf) * t0
                bw = pbw + (cbw - pbw) * t0
                a0, b1, b2 = _resonator(fq, bw, synth_rate)
                x, zi[i] = lfilter([a0], [1.0, -b1, -b2], x, zi=zi[i])

            out.append(x)
            pos += m

        pitch = pitch_target
        prev = cur

    if not out:
        return np.zeros(0, dtype=np.int16) if normalize != 'none' \
            else np.zeros(0)
    sig = np.concatenate(out)

    # Down to the chip's own rate.  decimate()'s anti-alias filter is what
    # actually removes the folded harmonics, and its cutoff lands at the
    # PCF-8200's 5 kHz band edge for free.
    if oversample > 1:
        sig = decimate(sig, oversample, ftype='fir', zero_phase=True)

    if normalize == 'none':
        return sig                                # raw float, for calibration
    peak = float(np.max(np.abs(sig)))
    if peak <= 0:
        return np.zeros(len(sig), dtype=np.int16)

    if normalize == 'peak':
        # Equal peak per utterance. Fine for a one-off render, but a quiet word
        # gets pushed to the same height as a loud phrase.
        sig = sig / peak * 0.89 * CLIP
    else:
        # Equal loudness per utterance: scale the speech (ignoring the silence
        # around it) to a common RMS, then clip whatever peaks survive.
        speech = sig[np.abs(sig) > peak * _SPEECH_FLOOR]
        level = float(np.sqrt(np.mean(speech ** 2))) if speech.size else peak
        if level > 0:
            sig = sig * (TARGET_RMS / level)
    return np.clip(sig, -CLIP, CLIP).astype(np.int16)


#: Format to hand to the outside world.  The chip really does run at 10 kHz in
#: mono and render() stays there, but a WAV in that format was reported as dead
#: air even though its contents verified clean through three independent
#: readers.  Demo files are therefore written in the same format as the
#: Windows system sounds -- 44100 Hz, stereo -- which is the most widely
#: accepted shape and costs nothing, since the chip band-limits to 5 kHz.
#: The sbaitso addon resamples for the same class of reason ("8475 Hz, which
#: not every output path accepts").
OUT_RATE = 44100
OUT_CHANNELS = 2


def compress(pcm, ratio=0.55, attack_ms=8.0, release_ms=60.0,
             sample_rate=SAMPLE_RATE, floor_db=-45.0):
    """Even out the loudness swing through an utterance.

    This is deliberately NOT a chip model.  The PCF-8200 applies the frame's
    AM field and whatever gain the formant cascade happens to have, and the
    result genuinely swings about 19 dB across a sentence.  TTS.dll measures
    14.6 dB on the same material, and no chip-level explanation accounted for
    the difference -- not the amplitude table, not the source tilt, not the
    cascade gain correction.  The likely reason is prosaic: it is a modern
    reimplementation for screen-reader use, and a gentle limiter is an obvious
    thing for one to carry.

    `ratio` is the exponent applied to the envelope, so 1.0 is a no-op and
    smaller values flatten harder.
    """
    import numpy as np
    x = pcm.astype(np.float64)
    if not len(x) or ratio >= 1.0:
        return pcm
    peak = np.abs(x).max()
    if peak <= 0:
        return pcm
    # one-pole envelope follower with separate attack and release
    a_at = math.exp(-1.0 / (sample_rate * attack_ms / 1000.0))
    a_re = math.exp(-1.0 / (sample_rate * release_ms / 1000.0))
    env = np.empty_like(x)
    e = 0.0
    for i, v in enumerate(np.abs(x)):
        a = a_at if v > e else a_re
        e = a * e + (1.0 - a) * v
        env[i] = e
    floor = peak * (10.0 ** (floor_db / 20.0))
    env = np.maximum(env, floor)
    y = x * (env / peak) ** (ratio - 1.0)
    m = np.abs(y).max()
    return (y * (peak / m)).astype(np.int16) if m > 0 else pcm


def resample(pcm, src_rate=SAMPLE_RATE, dst_rate=OUT_RATE):
    """Rate-convert int16 mono, preserving level."""
    if src_rate == dst_rate or len(pcm) == 0:
        return pcm
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(int(src_rate), int(dst_rate))
    y = resample_poly(pcm.astype(np.float64), dst_rate // g, src_rate // g)
    return np.clip(y, -CLIP, CLIP).astype(np.int16)


def write_wav(path, pcm, sample_rate=SAMPLE_RATE, out_rate=OUT_RATE,
              channels=OUT_CHANNELS):
    """Write a WAV in the most widely playable shape (44.1 kHz stereo)."""
    import wave
    if out_rate and out_rate != sample_rate:
        pcm = resample(pcm, sample_rate, out_rate)
        sample_rate = out_rate
    if channels == 2:
        pcm = np.repeat(pcm[:, None], 2, axis=1).ravel()
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path
