# -*- coding: utf-8 -*-
"""The C track builder is the add-on's, exactly: the FS bits ignored, the same
shortest frame, flat pitch and furcsa.  Skipped if the library isn't built."""
import os
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chip_synth                                        # noqa: E402
import pcf8200_native as native                          # noqa: E402

pytestmark = pytest.mark.skipif(native.load() is None, reason="native library not built")


def _seq(r, n):
    out = [("pitch", r.randint(20, 120))]
    for _ in range(n):
        x = r.random()
        if x < 0.06:
            out.append(("pitch", r.randint(1, 255)))
        elif x < 0.12:
            out.append(("ctrl", bytes([0, 0x80 | r.randint(0, 3)])))
        else:
            out.append(("frame", bytes(r.randrange(256) for _ in range(5))))
    return out


@pytest.mark.parametrize("furcsa", [False, True])
@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("time_scale", [1.0, 0.1, 0.73, 1.6])
def test_frames_match_the_addon_exactly(furcsa, flat, time_scale):
    for seed in range(30):
        seq = _seq(random.Random(seed), 60)
        amp, p, noise, fc, bw, nf, n = chip_synth._render_prep(
            seq, time_scale=time_scale, flat_pitch=flat, furcsa_override=furcsa)
        t = native.NativeTracker(female=furcsa, honour_fs=False, flat_pitch=flat,
                                 time_scale=time_scale)
        got = []
        for kind, val in seq:
            if kind == "pitch":
                t.pitch(val)
            elif kind == "frame":
                got.append(t.frame(val))
        assert t.nf == nf
        assert np.array_equal(np.concatenate([g[0] for g in got]), amp)
        assert np.array_equal(np.concatenate([g[1] for g in got]), p)
        assert np.array_equal(np.concatenate([g[2] for g in got]), ~noise)
        for i in range(nf):
            assert np.array_equal(np.concatenate([g[3][i] for g in got]), fc[i])
            assert np.array_equal(np.concatenate([g[4][i] for g in got]), bw[i])
