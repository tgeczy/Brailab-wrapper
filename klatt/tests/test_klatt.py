# -*- coding: utf-8 -*-
"""What the two papers predict, measured on the built library.

K80 = Klatt (1980), "Software for a cascade/parallel formant synthesizer".
K90 = Klatt and Klatt (1990), the KLGLOTT88 source and the KLSYN88 parameters.

Every check is a relation the papers state: a resonator's response, a source
parameter's meaning, a branch's routing.  Nothing here compares against a stored
rendering, so the tests say why a number is what it is.

Skipped if the library hasn't been built (python klatt/csrc/build_native.py).
"""
import math
import random

import numpy as np
import pytest

from klatt import klatt_native as kn

pytestmark = pytest.mark.skipif(kn.load() is None, reason="native library not built")

SR = 10000.0
SETTLE = 3000            # samples left out at the start of a steady sound
VOWEL = dict(f0=100.0, av=60.0)
NOISE_ONLY = dict(f0=0.0, av=0.0)


def render(n, config=None, **frame):
    s = kn.Synth(**(config or {}))
    s.frame(**frame)
    return s.run(n)


def db(x):
    return 10.0 * math.log10(float(np.mean(np.asarray(x) ** 2)) + 1e-300)


def harmonic_db(x, f0, fmax=4500.0):
    """Levels of the harmonics of a sound whose period is a whole number of samples:
    the window holds whole periods, so each harmonic falls on one bin."""
    period = int(round(SR / f0))
    assert abs(period - SR / f0) < 1e-9
    n = (len(x) // period) * period
    X = np.abs(np.fft.rfft(x[:n])) / n
    k = np.arange(1, int(fmax / f0) + 1)
    return k * f0, 20.0 * np.log10(X[k * (n // period)] + 1e-300)


def resonator_db(f, F, BW):
    """K80's resonator, |A / (1 - B z^-1 - C z^-2)| in dB at f."""
    T = 1.0 / SR
    C = -math.exp(-2.0 * math.pi * BW * T)
    B = 2.0 * math.exp(-math.pi * BW * T) * math.cos(2.0 * math.pi * F * T)
    A = 1.0 - B - C
    z = np.exp(-2j * np.pi * np.asarray(f, float) * T)
    return 20.0 * np.log10(np.abs(A / (1.0 - B * z - C * z * z)))


def fundamental_hz(x, near):
    """The fundamental's frequency from a zero-padded spectrum, to a small fraction of a hertz."""
    n = len(x)
    pad = 1 << int(math.ceil(math.log2(n)) + 3)
    X = np.abs(np.fft.rfft(x * np.hanning(n), pad))
    f = np.fft.rfftfreq(pad, 1.0 / SR)
    m = (f > near * 0.9) & (f < near * 1.1)
    i = int(np.flatnonzero(m)[0] + np.argmax(X[m]))
    a, b, c = X[i - 1], X[i], X[i + 1]
    return f[i] + 0.5 * (a - c) / (a - 2.0 * b + c) * (f[1] - f[0])


# ---------------------------------------------------------------- the pieces

@pytest.mark.parametrize("F,BW", [(500.0, 60.0), (1500.0, 90.0), (4900.0, 1000.0), (0.0, 100.0), (280.0, 90.0)])
def test_resonator_coefficients_are_k80s(F, BW):
    T = 1.0 / SR
    C = -math.exp(-2.0 * math.pi * BW * T)
    B = 2.0 * math.exp(-math.pi * BW * T) * math.cos(2.0 * math.pi * F * T)
    A = 1.0 - B - C
    got = kn.resonator(F, BW, SR)
    assert got == pytest.approx((A, B, C), abs=1e-12)


def test_defaults_are_the_papers():
    c = kn.default_config()
    assert [getattr(c, n) for n in kn.CONFIG_FIELDS] == [10000.0, 50.0, 5.0, 2.0, 0.0, 0.0, 8.0, 47.0]
    f = kn.default_frame()
    assert (f.f0, f.av, f.avs, f.ah, f.af, f.oq, f.tl, f.fl) == (100.0, 60.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0)
    assert list(f.f) == [500.0, 1500.0, 2500.0, 3250.0, 3700.0, 4900.0]
    assert list(f.b) == [60.0, 90.0, 150.0, 200.0, 200.0, 1000.0]
    assert (f.fnp, f.bnp, f.fnz, f.bnz) == (280.0, 90.0, 280.0, 90.0)
    assert list(f.a) == [0.0] * 6 and (f.an, f.ab) == (0.0, 0.0)
    assert list(f.bp) == [0.0] * 6


@pytest.mark.parametrize("config", [{"n_cascade": 0}, {"n_cascade": 7}, {"source": 0}, {"source": 3},
                                    {"sample_rate": 0}, {"samples_per_frame": 0}, {"tap": 9}])
def test_a_bad_config_is_refused(config):
    with pytest.raises(ValueError):
        kn.Synth(**config)


# ---------------------------------------------------------------- the contract

@pytest.mark.parametrize("tap", [0, 1, 2, 3])
@pytest.mark.parametrize("source", [1, 2])
def test_no_amplitude_no_sound(tap, source):
    x = render(3000, {"tap": tap, "source": source}, av=0, avs=0, ah=0, af=0)
    assert not x.any()


def _session(seed):
    """A stretch of speech-like frames at uneven distances."""
    r = random.Random(seed)
    events, at = [], 0
    for _ in range(14):
        events.append((at, dict(
            f0=r.choice([0.0, 97.0, 123.4, 220.0]), av=r.choice([0.0, 48.0, 60.0]),
            avs=r.choice([0.0, 0.0, 47.0]), ah=r.choice([0.0, 40.0, 55.0]), af=r.choice([0.0, 0.0, 60.0]),
            oq=r.uniform(30, 80), tl=r.choice([0.0, 8.0, 24.0]), fl=r.choice([0.0, 25.0]),
            f=[r.uniform(200, 900), r.uniform(600, 2400), r.uniform(1400, 3400), 3250.0, 3700.0, 4900.0],
            b=[r.uniform(40, 300), r.uniform(40, 300), r.uniform(60, 400), 200.0, 200.0, 1000.0],
            fnz=r.choice([280.0, 450.0]), a=[0.0, 0.0] + [r.choice([0.0, 45.0, 57.0]) for _ in range(4)],
            ab=r.choice([0.0, 57.0]))))
        at += r.choice([1, 37, 50, 80, 400])
    return events, at + 300


def _run(events, total, block, config):
    s = kn.Synth(**config)
    out, at = [], 0
    bounds = [e[0] for e in events[1:]] + [total]
    for (start, frame), end in zip(events, bounds):
        assert start == at
        s.frame(**frame)
        while at < end:
            n = min(block, end - at)
            out.append(s.run(n))
            at += n
    return np.concatenate(out)


@pytest.mark.parametrize("config", [{}, {"source": 1}, {"n_cascade": 4}, {"all_parallel": 1}, {"tap": 1}],
                         ids=str)
def test_any_block_split_is_bit_identical(config):
    for seed in range(6):
        events, total = _session(seed)
        whole = _run(events, total, total, config)
        assert np.isfinite(whole).all()
        for block in (1, 7, 50, 333):
            assert np.array_equal(_run(events, total, block, config), whole)


def test_the_seed_decides_the_noise_and_nothing_else():
    voiced = [render(4000, {"seed": s}, **VOWEL) for s in (8, 9)]
    assert np.array_equal(voiced[0], voiced[1])
    hiss = [render(4000, {"seed": s}, ah=55, **NOISE_ONLY) for s in (8, 8, 9)]
    assert np.array_equal(hiss[0], hiss[1])
    assert not np.array_equal(hiss[0], hiss[2])
    assert hiss[0].any()


def test_two_synthesizers_do_not_share_state():
    a, b = kn.Synth(), kn.Synth()
    a.frame(ah=50)
    b.frame(ah=50)
    first = a.run(500)
    b.run(123)                      # b moves on; a must not notice
    alone = kn.Synth()
    alone.frame(ah=50)
    whole = alone.run(1000)
    assert np.array_equal(np.concatenate([first, a.run(500)]), whole)


def test_wild_parameters_stay_finite():
    r = random.Random(1)
    full = kn.full_scale()
    for source in (1, 2):
        s = kn.Synth(source=source)
        for _ in range(300):
            wild = lambda: r.choice([-1e9, -50.0, 0.0, 1.0, 5000.0, 1e9, r.uniform(-200, 9000)])  # noqa: E731
            s.frame(f0=wild(), av=wild(), avs=wild(), ah=wild(), af=wild(), oq=wild(), tl=wild(), fl=wild(),
                    f=[wild() for _ in range(6)], b=[wild() for _ in range(6)],
                    fnp=wild(), bnp=wild(), fnz=wild(), bnz=wild(),
                    a=[wild() for _ in range(6)], an=wild(), ab=wild(),
                    bp=[wild() for _ in range(6)])
            x = s.run(r.choice([1, 50, 200]))
            assert np.isfinite(x).all()
            assert np.max(np.abs(x)) <= 1000.0 * full


def test_a_default_vowel_fits_the_output_range():
    x = render(8000, **VOWEL)[SETTLE:]
    peak = np.max(np.abs(x)) / kn.full_scale()
    assert 0.01 < peak < 1.0


# ---------------------------------------------------------------- the voicing source

@pytest.mark.parametrize("source", [1, 2])
@pytest.mark.parametrize("f0", [80.0, 100.0, 123.4, 197.0, 220.0])
def test_f0_is_kept_to_a_quarter_of_a_sample(source, f0):
    """K90, footnote 17: the period is quantized to a quarter of a sample, so 197 Hz comes out
    within 0.13 %; whole samples would give 196.1 Hz, 0.47 % flat."""
    x = render(40000, {"tap": 1, "source": source}, f0=f0, av=60)[SETTLE:]
    assert fundamental_hz(x, f0) == pytest.approx(f0, rel=0.003)


def _open_share(oq):
    """Percent of the period in which the source is doing anything (above 5 % of its peak)."""
    x = render(20000, {"tap": 1}, f0=100.0, av=60, oq=oq, tl=0)[SETTLE:]
    shape = np.abs(x[:len(x) // 100 * 100].reshape(-1, 100)).mean(axis=0)
    return 100.0 * float(np.mean(shape > 0.05 * shape.max()))


def test_open_quotient_is_the_share_of_the_period_the_glottis_is_open():
    """K90: OQ is the open time over the period.  The flow derivative of a t^2 - b t^3 is under
    5 % of its peak for 7.5 % of the open phase (at the opening and at its zero crossing), and the
    downsampling filter rings briefly after the closure."""
    shares = [_open_share(oq) for oq in (30.0, 50.0, 70.0)]
    for oq, share in zip((30.0, 50.0, 70.0), shares):
        assert 0.92 * oq - 7.0 <= share <= oq + 10.0, (oq, share)
    assert shares[0] < shares[1] < shares[2]


@pytest.mark.parametrize("tl", [10.0, 20.0, 30.0])
def test_tilt_is_db_down_at_3_khz(tl):
    """K90: TL is the extra tilt of the source spectrum in dB down at 3 kHz; the fundamental
    is left almost alone."""
    flat = render(30000, {"tap": 1}, f0=100.0, av=60, tl=0)[SETTLE:]
    tilted = render(30000, {"tap": 1}, f0=100.0, av=60, tl=tl)[SETTLE:]
    f, a = harmonic_db(flat, 100.0)
    _, b = harmonic_db(tilted, 100.0)
    at3k = float((a - b)[f == 3000.0][0])
    assert at3k == pytest.approx(tl, abs=2.0)
    assert abs(float((a - b)[0])) < 2.0
    assert np.all(np.diff((a - b)[4:35]) > -0.5)          # more tilt the higher the harmonic


def test_flutter_follows_k90s_three_sinusoids():
    """K90 Eq. (1): delta f0 = (FL/50)(F0/100)[sin 2pi 12.7t + sin 2pi 7.1t + sin 2pi 4.7t] Hz.
    At FL = 25 and 100 Hz that is 0.5 Hz per component: 0.61 Hz rms, at those three rates."""
    n = 1 << 16
    x = render(n + SETTLE, {"tap": 1}, f0=100.0, av=60, fl=25.0)[SETTLE:]
    X = np.fft.fft(x)
    f = np.fft.fftfreq(n, 1.0 / SR)
    X[~((f > 60.0) & (f < 140.0))] = 0.0                  # the fundamental alone, as an analytic signal
    phase = np.unwrap(np.angle(np.fft.ifft(2.0 * X)))
    inst = np.diff(phase) * SR / (2.0 * math.pi)
    inst = inst[5000:-5000]
    assert float(np.mean(inst)) == pytest.approx(100.0, abs=0.3)
    assert float(np.std(inst)) == pytest.approx(0.5 * math.sqrt(1.5), abs=0.2)
    dev = (inst - inst.mean()) * np.hanning(len(inst))
    D = np.abs(np.fft.rfft(dev, 1 << 20))
    fd = np.fft.rfftfreq(1 << 20, 1.0 / SR)
    for rate in (4.7, 7.1, 12.7):
        m = (fd > rate - 1.0) & (fd < rate + 1.0)
        assert fd[m][np.argmax(D[m])] == pytest.approx(rate, abs=0.3)
    steady = render(n + SETTLE, {"tap": 1}, f0=100.0, av=60, fl=0.0)[SETTLE:]
    # no flutter: every period the same
    assert np.max(np.abs(steady[:100] - steady[100:200])) < 1e-9 * np.max(np.abs(steady))


@pytest.mark.parametrize("config,frame", [({"tap": 1}, {}), ({"tap": 0}, {}), ({"tap": 1, "source": 1}, {}),
                                          ({"tap": 0, "source": 1}, {"avs": 0})], ids=str)
def test_av_is_in_db(config, frame):
    quiet = render(20000, config, f0=100.0, av=50, **frame)[SETTLE:]
    loud = render(20000, config, f0=100.0, av=60, **frame)[SETTLE:]
    assert db(loud) - db(quiet) == pytest.approx(10.0, abs=0.3)


# ---------------------------------------------------------------- the noise sources

@pytest.mark.parametrize("name,tap,extra", [("ah", 2, {}), ("ah", 0, {}), ("af", 3, {}),
                                            ("af", 0, {"ab": 57.0})])
def test_noise_amplitudes_are_in_db(name, tap, extra):
    quiet = render(20000, {"tap": tap}, **{name: 50.0}, **extra, **NOISE_ONLY)[SETTLE:]
    loud = render(20000, {"tap": tap}, **{name: 60.0}, **extra, **NOISE_ONLY)[SETTLE:]
    assert db(loud) - db(quiet) == pytest.approx(10.0, abs=0.3)


def test_noise_amplitude_is_interpolated_across_a_frame():
    """K80: AF and AH move linearly over an update interval, so ten samples into a 50-sample
    frame the noise has a fifth of its level, not all of it."""
    s = kn.Synth(tap=2)
    s.frame(ah=0, **NOISE_ONLY)
    s.run(500)
    s.frame(ah=60)
    start = s.run(10)
    s.run(490)
    steady = s.run(4000)
    assert 0.0 < np.mean(np.abs(start)) < 0.5 * np.mean(np.abs(steady))


# ---------------------------------------------------------------- the vocal tract

def _vowel_harmonics(config=None, **frame):
    x = render(SETTLE + 20000, config, **dict(VOWEL, **frame))[SETTLE:]
    return harmonic_db(x, 100.0)


@pytest.mark.parametrize("source", [1, 2])
def test_moving_a_cascade_formant_changes_the_spectrum_by_its_resonators_ratio(source):
    f, a = _vowel_harmonics({"source": source})
    _, b = _vowel_harmonics({"source": source}, f=[500, 1800, 2500, 3250, 3700, 4900])
    want = resonator_db(f, 1800.0, 90.0) - resonator_db(f, 1500.0, 90.0)
    assert np.max(np.abs((b - a) - want)) < 0.5


def test_a_bandwidth_is_the_resonators_bandwidth():
    f, a = _vowel_harmonics()
    _, b = _vowel_harmonics(b=[200, 90, 150, 200, 200, 1000])
    want = resonator_db(f, 500.0, 200.0) - resonator_db(f, 500.0, 60.0)
    assert np.max(np.abs((b - a) - want)) < 0.5


@pytest.mark.parametrize("F1", [100.0, 1450.0])
def test_a_formant_outside_the_papers_tables_is_still_that_resonator(F1):
    """The tables' ranges are one talker's English vowels; another voice's frames go lower
    and higher, and get the resonator they ask for."""
    f, a = _vowel_harmonics()
    _, b = _vowel_harmonics(f=[F1, 1500, 2500, 3250, 3700, 4900])
    want = resonator_db(f, F1, 60.0) - resonator_db(f, 500.0, 60.0)
    assert np.max(np.abs((b - a) - want)) < 0.5


@pytest.mark.parametrize("which,F,BW", [(0, 500.0, 10.0), (2, 2500.0, 20.0), (1, 1500.0, 3000.0)])
def test_a_bandwidth_outside_the_papers_tables_is_still_that_bandwidth(which, F, BW):
    default = [60.0, 90.0, 150.0, 200.0, 200.0, 1000.0]
    changed = list(default)
    changed[which] = BW
    f, a = _vowel_harmonics()
    _, b = _vowel_harmonics(b=changed)
    want = resonator_db(f, F, BW) - resonator_db(f, F, default[which])
    assert np.max(np.abs((b - a) - want)) < 0.5


def test_the_number_of_cascade_formants_is_nf():
    """K80: with four formants the fifth resonator leaves the cascade; with six, F6 joins it."""
    f, five = _vowel_harmonics({"n_cascade": 5})
    _, four = _vowel_harmonics({"n_cascade": 4})
    _, six = _vowel_harmonics({"n_cascade": 6})
    assert np.max(np.abs((five - four) - resonator_db(f, 3700.0, 200.0))) < 0.5
    assert np.max(np.abs((six - five) - resonator_db(f, 4900.0, 1000.0))) < 0.5


def test_the_nasal_pole_and_zero_cancel_when_they_coincide():
    """K80: FNZ = FNP for a sound that is not nasal; apart, they add a pole and a zero."""
    f, plain = _vowel_harmonics(fnp=280, fnz=280, bnp=90, bnz=90)
    _, moved = _vowel_harmonics(fnp=450, fnz=450, bnp=90, bnz=90)
    assert np.max(np.abs(moved - plain)) < 0.1
    _, nasal = _vowel_harmonics(fnp=270, fnz=450, bnp=100, bnz=100)
    want = resonator_db(f, 270.0, 100.0) - resonator_db(f, 450.0, 100.0)
    assert np.max(np.abs((nasal - plain) - want)) < 0.5


def _spectrum_db(x):
    n = 1 << 15
    return np.fft.rfftfreq(n, 1.0 / SR), 20.0 * np.log10(np.abs(np.fft.rfft(x[:n] * np.hanning(n))) + 1e-300)


def test_aspiration_goes_through_the_cascade():
    """The same noise through the cascade with F2 in two places: the two spectra differ by the
    two resonators' ratio, bin for bin."""
    a = render(SETTLE + (1 << 15), ah=60, **NOISE_ONLY)[SETTLE:]
    b = render(SETTLE + (1 << 15), ah=60, f=[500, 1800, 2500, 3250, 3700, 4900], **NOISE_ONLY)[SETTLE:]
    f, A = _spectrum_db(a)
    _, B = _spectrum_db(b)
    m = (f > 300.0) & (f < 4500.0)
    err = np.abs((B - A)[m] - (resonator_db(f[m], 1800.0, 90.0) - resonator_db(f[m], 1500.0, 90.0)))
    assert np.median(err) < 0.5 and np.percentile(err, 90) < 2.0


def _smooth_peak_hz(x, lo=300.0, hi=4900.0):
    f, S = _spectrum_db(x)
    power = np.convolve(10.0 ** (S / 10.0), np.ones(200) / 200.0, mode="same")     # about 60 Hz wide
    m = (f > lo) & (f < hi)
    return float(f[m][np.argmax(power[m])])


def test_frication_goes_through_the_parallel_formants():
    """K80: frication excites the parallel resonators, each with its own amplitude; the cascade
    plays no part, so the cascade's F1 does not matter."""
    n = SETTLE + (1 << 15)
    only3 = render(n, af=60, a=[0, 0, 60, 0, 0, 0], **NOISE_ONLY)[SETTLE:]
    assert _smooth_peak_hz(only3) == pytest.approx(2500.0, abs=200.0)
    only6 = render(n, af=60, a=[0, 0, 0, 0, 0, 60], **NOISE_ONLY)[SETTLE:]
    assert _smooth_peak_hz(only6) > 4000.0
    louder = render(n, af=60, a=[0, 0, 70, 0, 0, 0], **NOISE_ONLY)[SETTLE:]
    assert db(louder) - db(only3) == pytest.approx(10.0, abs=0.5)
    moved3 = render(n, af=60, a=[0, 0, 60, 0, 0, 0], f=[500, 1500, 3000, 3250, 3700, 4900], **NOISE_ONLY)[SETTLE:]
    assert _smooth_peak_hz(moved3) == pytest.approx(3000.0, abs=200.0)


def test_a_parallel_formant_has_its_cascade_bandwidth_unless_given_its_own():
    n = SETTLE + 4000
    frame = dict(af=60, a=[0, 57, 60, 48, 48, 46], **NOISE_ONLY)
    plain = render(n, **frame)
    assert np.array_equal(render(n, bp=[0, 0, 0, 0, 0, 0], **frame), plain)
    assert np.array_equal(render(n, bp=[60, 90, 150, 200, 200, 1000], **frame), plain)
    assert not np.array_equal(render(n, bp=[0, 0, 300, 0, 0, 0], **frame), plain)


def test_a_parallel_bandwidth_is_that_formants_bandwidth_for_frication():
    """K90 Table XII lists the parallel formants' bandwidths apart from the cascade's.  The same
    noise through the third parallel formant at two bandwidths: the two spectra differ by the two
    resonators' ratio, bin for bin."""
    n = SETTLE + (1 << 15)
    narrow = render(n, af=60, a=[0, 0, 60, 0, 0, 0], **NOISE_ONLY)[SETTLE:]
    wide = render(n, af=60, a=[0, 0, 60, 0, 0, 0], bp=[0, 0, 300, 0, 0, 0], **NOISE_ONLY)[SETTLE:]
    f, A = _spectrum_db(narrow)
    _, B = _spectrum_db(wide)
    m = (f > 300.0) & (f < 4500.0)
    err = np.abs((B - A)[m] - (resonator_db(f[m], 2500.0, 300.0) - resonator_db(f[m], 2500.0, 150.0)))
    assert np.median(err) < 0.5 and np.percentile(err, 90) < 2.0


def test_parallel_bandwidths_leave_the_cascade_alone():
    plain = render(8000, **VOWEL)
    assert np.array_equal(render(8000, bp=[300, 300, 300, 300, 300, 300], **VOWEL), plain)
    hiss = render(8000, ah=55, **NOISE_ONLY)
    assert np.array_equal(render(8000, ah=55, bp=[300, 300, 300, 300, 300, 300], **NOISE_ONLY), hiss)


def test_the_bypass_path_is_flat():
    """K80: AB is for fricatives with a flat spectrum ([f], [th]): no formant stands out."""
    x = render(SETTLE + (1 << 15), af=60, ab=60, **NOISE_ONLY)[SETTLE:]
    f, S = _spectrum_db(x)
    bands = [10.0 * math.log10(np.mean(10.0 ** (S[(f >= a) & (f < a + 1000.0)] / 10.0))) for a in (500, 1500, 2500, 3500)]
    assert max(bands) - min(bands) < 6.0


def test_voicing_modulates_the_noise():
    """K80: with voicing on, aspiration and frication are amplitude-modulated at the pitch period
    (half of each period at full level), so the noise carries a component at F0."""
    def period_shape(**frame):
        x = render(SETTLE + 40000, {"tap": 2}, ah=60, **frame)[SETTLE:]
        return (x.reshape(-1, 100) ** 2).mean(axis=0)
    plain = period_shape(**NOISE_ONLY)
    voiced = period_shape(f0=100.0, av=60)
    assert plain.max() / plain.min() < 2.0
    assert voiced.max() / max(voiced.min(), 1e-300) > 3.0
