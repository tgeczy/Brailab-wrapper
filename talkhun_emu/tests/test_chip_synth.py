# -*- coding: utf-8 -*-
"""chip_synth's pitch control, which is what NVDA's capital pitch change rides on.

These need numpy only -- no Unicorn, no TALKHUN, no NVDA -- because the
sequences are built here rather than captured, so they run anywhere.

The bug they exist to prevent: `render_chip_fast(..., pitch_byte=N)` looks like
the pitch knob and is not one.  It only seeds the anchor, and a captured
sequence carries a ('pitch', byte) of its own at every intonation unit which
overwrites it immediately -- rendering one capture at pitch_byte 33, 46 and 65
gives the same 101 Hz.  A driver wired to it would offer a pitch slider, and a
capital pitch change percentage, that did nothing at any value.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chip_synth                                        # noqa: E402


def voiced_frame(F1=22, F2=13, F3=4, AM=13, PI=2, FD=0):
    """One five-byte PCF8200 speech frame, laid out as the chip reads it."""
    b0 = (0 << 5) | (F1 & 0x1F)
    b1 = (0 << 7) | (0 << 5) | (PI & 0x1F)
    b2 = (((FD >> 1) & 1) << 7) | ((F3 & 7) << 4) | (AM & 0x0F)
    b3 = ((FD & 1) << 7) | (0 << 5) | (F2 & 0x1F)
    b4 = 0
    return bytes([b0, b1, b2, b3, b4])


def steady(pitch_byte=46, n=40, PI=0):
    """A steady voiced sequence: one pitch command, then identical frames.

    PI=0 on purpose.  A non-zero PI is a *cumulative* pitch increment in hertz,
    and transposing deliberately leaves those excursions alone so the contour
    keeps its shape while the base moves -- which is right for speech but means
    the average F0 no longer scales exactly with the factor.  To measure the
    transposition itself, the contour has to be flat.
    """
    return [('pitch', pitch_byte)] + [('frame', voiced_frame(PI=PI))] * n


def measure_f0(x, rate=10000):
    """Autocorrelation pitch over the middle of the signal."""
    x = np.asarray(x, dtype=float)
    x = x[len(x) // 4: 3 * len(x) // 4]
    x = x - x.mean()
    ac = np.correlate(x, x, 'full')[len(x) - 1:]
    lo, hi = int(rate / 300), int(rate / 60)
    return rate / float(int(np.argmax(ac[lo:hi])) + lo)


def test_transpose_is_identity_at_one():
    seq = steady()
    assert chip_synth.transpose_seq(seq, 1.0) is seq


def test_transpose_touches_only_pitch_items():
    seq = steady()
    out = chip_synth.transpose_seq(seq, 1.5)
    assert [k for k, _ in out] == [k for k, _ in seq]
    assert out[0] == ('pitch', 69)
    assert [v for k, v in out if k == 'frame'] == [v for k, v in seq if k == 'frame']


@pytest.mark.parametrize("factor", [0.5, 0.75, 1.25, 2.0])
def test_transpose_clamps_into_a_byte(factor):
    for pitch in (1, 46, 200, 255):
        out = chip_synth.transpose_seq([('pitch', pitch)], factor)
        assert 1 <= out[0][1] <= 255


def test_pitch_byte_argument_does_not_override_the_sequence():
    """The trap: pitch_byte cannot be used as a pitch control.

    A captured sequence sets its own pitch, so this argument is overwritten
    before it reaches the audio.  Pinned so nobody wires a slider to it again.
    """
    seq = steady()
    a = chip_synth.render_chip_fast(seq, pitch_byte=33)
    b = chip_synth.render_chip_fast(seq, pitch_byte=65)
    assert np.array_equal(a, b)


@pytest.mark.parametrize("factor", [0.75, 1.25, 1.5])
def test_transposing_scales_f0_and_leaves_duration_alone(factor):
    """Pitch must move without touching rate -- they are separate settings.

    A capital spoken higher must not also be spoken slower, and NVDA's pitch
    slider must not secretly change speed.
    """
    seq = steady()
    base = chip_synth.render_chip_fast(seq)
    moved = chip_synth.render_chip_fast(chip_synth.transpose_seq(seq, factor))

    assert len(moved) == len(base), "transposing must not change the duration"
    ratio = measure_f0(moved) / measure_f0(base)
    assert abs(ratio - factor) < 0.06, \
        "expected F0 x%.2f, measured x%.3f" % (factor, ratio)


def test_capital_pitch_offset_raises_the_voice():
    """NVDA's default capital pitch change of +30 must be clearly audible.

    The driver maps 0-100 to an octave-wide factor, so 50 -> 1.0 and 80 -> ~1.23.
    """
    def factor(pitch, adj=0):
        return 2.0 ** ((min(100, max(0, pitch + adj)) - 50) / 100.0)

    assert factor(50) == 1.0
    assert 1.2 < factor(50, 30) < 1.3
    assert factor(90, 30) == factor(100), "offsets clamp together, not separately"

    seq = steady()
    plain = chip_synth.render_chip_fast(seq)
    capital = chip_synth.render_chip_fast(
        chip_synth.transpose_seq(seq, factor(50, 30)))
    assert measure_f0(capital) > measure_f0(plain) * 1.15


def test_device_output_cannot_reach_the_clipping_ceiling():
    """The output stage must bend, not hit a wall.

    Every emulated build through 3.1.x saturated int16 on loud speech: Tomi's own
    downloads-list string peaked 44% past the driver's ceiling and clipped 46
    samples, a say-all sentence 120.  Single words never did it, which is why
    "harom" alone sounded clean and "harom" inside a version string did not --
    the intonation slide is what reaches the ceiling.

    The knee asymptotes at 1.0, so this is a property of the arithmetic rather
    than of any particular corpus: drive the render far past full scale and the
    output still cannot get there.
    """
    seq = steady()
    quiet = chip_synth.render_chip_fast(seq)
    assert abs(quiet).max() < 1.0

    # 20x overdrive: without a knee this would be far past the ceiling.  tanh
    # saturates to exactly 1.0 in float64, so the bound is inclusive.
    hot = chip_synth.render_chip_fast(seq, scale=20.0)
    assert abs(hot).max() <= 1.0, "knee must bound the output at full scale"

    # ...and the driver's own int16 stage therefore never saturates.
    OUT_SCALE, MAX_GAIN = 20000.0, 1.25
    assert abs(hot).max() * OUT_SCALE * MAX_GAIN < 32767


def test_bare_chip_has_no_output_stage():
    """highpass=0 means the caller asked for silicon, not a device.

    The makeup gain and the knee are both the amplifier, so they must arrive and
    depart together -- otherwise a measurement of the chip itself is quietly
    reshaped by a loudspeaker model.
    """
    seq = steady()
    bare = chip_synth.render_chip_fast(seq, scale=20.0, highpass=0.0)
    assert abs(bare).max() > 1.0, "bare chip must be left unbounded"
