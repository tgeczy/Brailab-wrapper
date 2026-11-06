# -*- coding: utf-8 -*-
"""Hold the C core to the Python reference.

Both run the same seeded random sessions -- random blocks of parameters, under the
defaults and under every option -- and after each block the phase and the noise
state must be equal exactly, the audio within float noise, and the 16-bit PCM
identical.  sin and exp come from different libraries on the two sides, so the
audio can differ in the last bits; nothing else may.

Skipped if the library hasn't been built (python csrc/build_native.py).
"""
import random

import numpy as np
import pytest

from pcf8200 import pcf8200_core as core
from pcf8200 import pcf8200_native as native

pytestmark = pytest.mark.skipif(native.load() is None, reason="native library not built")

AUDIO_TOL = 1e-9
SESSIONS = 40

OPTIONS = [
    {},
    {"gain": core.HIGHPASS_MAKEUP, "knee": core.SOFTKNEE},
    {"gain": 3.0, "knee": core.SOFTKNEE},
    {"highpass": 0},
    {"lowpass": False},
    {"lowpass": False, "highpass": 0},
    {"source_tilt": 0},
    {"noise_gain": 0.1, "seed": 7},
    {"seed": 0},
    {"seed": 2 ** 40 + 99},
]


def _block(r, nf, n):
    """A stretch of speech-like parameters, with pitches past both limits."""
    x = np.arange(n) / max(n, 1)

    def glide(lo, hi):
        a, b = r.uniform(lo, hi), r.uniform(lo, hi)
        return a + (b - a) * x

    fc = np.array([glide(100, 1450), glide(500, 2450), glide(1500, 3450),
                   glide(2550, 4500), glide(3900, 4600)][:nf])
    bw = np.array([glide(10, 3000) for _ in range(nf)])
    pitch = glide(*r.choice([(20, 60), (80, 180), (150, 420)]))
    amp = glide(0, 1) if r.random() < 0.8 else np.zeros(n)
    voiced = np.array([r.random() < 0.7] * n)
    if n > 3 and r.random() < 0.3:
        voiced[n // 2:] = ~voiced[n // 2:]
    return amp, pitch, voiced, fc, bw


@pytest.mark.parametrize("kw", OPTIONS, ids=str)
@pytest.mark.parametrize("nf", [5, 4, 1])
def test_c_matches_the_reference(kw, nf):
    for seed in range(SESSIONS):
        r = random.Random(seed)
        py = core.Core(nf, **kw)
        c = native.NativeCore(nf, **kw)
        for _ in range(r.randint(1, 6)):
            n = r.choice([1, 2, 17, 128, 640, 1500])
            args = _block(r, nf, n)
            a = py.run(*args)
            b = c.run(*args)
            assert c.noise_state == py.noise.x
            assert c.phase == py.phase
            assert np.max(np.abs(a - b)) <= AUDIO_TOL * max(1.0, np.max(np.abs(a)))
            assert np.array_equal(np.round(a * 32767), np.round(b * 32767))


def test_too_many_formants_is_refused():
    with pytest.raises(ValueError):
        native.NativeCore(6)
