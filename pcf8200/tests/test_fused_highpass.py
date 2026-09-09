# -*- coding: utf-8 -*-
"""The output high-pass folded into the cascade loop is the three-pass one,
bit for bit -- and rendering a prefix of a track set gives the prefix of the
full render, which is what lets a caller stream a growing stream by
re-rendering it and passing on only the new samples."""
import numpy as np

from pcf8200.chip import render, _apply_highpass, HIGHPASS_HZ, RATE
from pcf8200.voice import Voice


def _tracks():
    v = Voice(pitch=110)
    v.vowel((700, 1200, 2500, 3300, 4000), dur=0.30, amp=0.9)
    v.fricative(dur=0.10)
    v.vowel((300, 2200, 2900, 3400, 4100), dur=0.25, amp=0.8, pitch=140)
    v.silence(0.05)
    v.vowel((500, 900, 2400, 3200, 3900), dur=0.20, amp=0.95, pitch=90)
    return v.tracks()


def test_fused_highpass_is_bit_identical_to_three_passes():
    fc, bw, amp, p, voiced = _tracks()
    fused = render(fc, bw, amp, p, voiced)                 # default path: fused
    bare = render(fc, bw, amp, p, voiced, highpass=0)      # cascade + low-pass only
    three = _apply_highpass(bare, HIGHPASS_HZ, RATE)        # the old three passes
    assert fused.shape == three.shape
    assert np.array_equal(fused, three)


def test_prefix_render_is_prefix_of_full_render():
    fc, bw, amp, p, voiced = _tracks()
    fc, bw = np.asarray(fc), np.asarray(bw)        # Voice gives lists of tracks
    full = render(fc, bw, amp, p, voiced)
    n = len(amp)
    for cut in (n // 7, n // 3, n // 2, n - 1):
        part = render(fc[:, :cut], bw[:, :cut], amp[:cut], p[:cut], voiced[:cut])
        assert len(part) == cut
        # bit for bit: every stage is causal and the harmonic sum is
        # accumulated in a fixed order, so the prefix's narrower harmonic
        # count (its lowest pitch may be higher) changes nothing
        assert np.array_equal(part, full[:cut])
