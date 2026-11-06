# -*- coding: utf-8 -*-
"""The audio core is the same however its samples are split into blocks: that is
what the add-on streams on, and what the C port will be held to."""
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
