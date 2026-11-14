# -*- coding: utf-8 -*-
"""The audio core is the same however its samples are split into blocks: that is
what the add-on streams on, and what the C port will be held to."""
import os

import numpy as np
import pytest

from pcf8200 import pcf8200_core as core
from pcf8200.voice import Voice


def _tracks():
    v = Voice(pitch=110)
    v.vowel((700, 1200, 2500, 3300, 4000), dur=0.20, amp=0.9)
    v.fricative(dur=0.10)
    v.vowel((300, 2200, 2900, 3400, 4100), dur=0.20, amp=0.8, pitch=300)
    v.silence(0.03)
    v.vowel((500, 900, 2400, 3200, 3900), dur=0.15, amp=0.95, pitch=60)
    fc, bw, amp, p, voiced = v.tracks()
    return np.asarray(fc), np.asarray(bw), amp, p, voiced


def _run(block, **kw):
    fc, bw, amp, p, voiced = _tracks()
    c = core.Core(len(fc), **kw)
    out = []
    for a in range(0, len(amp), block):
        s = slice(a, a + block)
        out.append(c.run(amp[s], p[s], voiced[s], fc[:, s], bw[:, s]))
    return np.concatenate(out)


@pytest.mark.parametrize("kw", [
    {},
    {"highpass": 0, "lowpass": False},
    {"source_tilt": 0, "gain": 0.9315, "knee": 0.75},
    {"seed": 7, "noise_gain": 0.25},
    {"lowpass": True},
    {"noise_lowpass": ()},
    {"noise_lowpass": (150.0, 1100.0, 1400.0), "noise_gain": 5.5},
])
@pytest.mark.parametrize("block", [1, 7, 128, 1000])
def test_any_block_split_is_bit_identical(block, kw):
    whole = _run(10 ** 9, **kw)
    assert np.array_equal(_run(block, **kw), whole)


def test_noise_is_the_written_out_generator():
    """Pinned: C has to produce exactly these, and a render depends on them."""
    n = core.Noise(12345)
    states = []
    for _ in range(4):
        n.block(1, 0.5)
        states.append(n.x)
    assert states == [3438011225, 2694051897, 755124627, 3795020523]
    v = core.Noise(12345).block(1, 0.5)[0]
    assert v == 3438011225 * (2.0 * 0.5 / 4294967296.0) - 0.5


def test_noise_is_uniform_at_the_asked_level():
    v = core.Noise().block(200000, 0.5)
    assert v.min() >= -0.5 and v.max() < 0.5
    assert abs(v.mean()) < 0.005
    assert abs(v.std() - 0.5 / 3 ** 0.5) < 0.002


def test_noise_runs_through_its_one_pole_lowpasses():
    """Written out here as the recurrence C repeats: y = (1 - a) x + a y, per corner."""
    import math
    corners = (900.0, 300.0)
    c = core.Core(1, noise_lowpass=corners, noise_gain=0.5)
    got = np.concatenate([c._noise(5), c._noise(120)])
    want = core.Noise().block(125, 0.5).tolist()
    for hz in corners:
        a = math.exp(-2.0 * math.pi * hz / core.RATE)
        y = 0.0
        for k in range(len(want)):
            y = (1.0 - a) * want[k] + a * y
            want[k] = y
    assert got.tolist() == want


def test_the_noise_source_is_low_passed_by_default():
    """The measured chip: far more noise under 500 Hz than at 4 kHz."""
    x = core.Core(1)._noise(1 << 16)
    spec = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / core.RATE)
    low = spec[(f > 100) & (f < 500)].mean()
    high = spec[(f > 3800) & (f < 4200)].mean()
    assert 28.0 < 10 * np.log10(low / high) < 34.0
    white = core.Core(1, noise_lowpass=())._noise(1000)
    assert np.array_equal(white, core.Noise().block(1000, core.NOISE_GAIN))


def test_more_noise_corners_than_the_c_core_holds_are_refused():
    with pytest.raises(ValueError):
        core.Core(1, noise_lowpass=(900.0,) * (core.NOISE_POLES + 1))


def test_pitch_outside_the_range_is_held_to_it():
    n = 2000
    fc = [np.full(n, 700.0)]
    bw = [np.full(n, 90.0)]
    amp = np.full(n, 0.5)
    voiced = np.ones(n, bool)
    wild = core.Core(1).run(amp, np.full(n, 900.0), voiced, fc, bw)
    top = core.Core(1).run(amp, np.full(n, core.PITCH_MAX_HZ), voiced, fc, bw)
    assert np.array_equal(wild, top)


def test_an_empty_block_changes_nothing():
    fc, bw, amp, p, voiced = _tracks()
    a = core.Core(len(fc))
    b = core.Core(len(fc))
    e = np.zeros(0)
    assert len(a.run(e, e, e.astype(bool), [e] * len(fc), [e] * len(fc))) == 0
    assert np.array_equal(a.run(amp, p, voiced, fc, bw), b.run(amp, p, voiced, fc, bw))


def test_output_rate_does_not_change_the_length_in_seconds():
    from pcf8200 import PCF8200
    secs = []
    for rate in (10000, 22050):
        chip = PCF8200(rate=rate)
        chip.pitch_hz(110)
        for _ in range(40):
            chip.frame_codes(F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)
        chip.stop()
        secs.append(len(chip.render()) / rate)
    assert abs(secs[0] - secs[1]) < 0.001


def test_the_two_version_numbers_agree():
    # They drifted apart once: 1.0.0 in the package, 1.1.3 in pyproject.toml.
    import pcf8200
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml")
    with open(path, encoding="utf-8") as f:
        assert 'version = "%s"' % pcf8200.__version__ in f.read()
