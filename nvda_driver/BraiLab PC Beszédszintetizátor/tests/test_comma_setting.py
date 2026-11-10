# -*- coding: utf-8 -*-
"""The "Gentler comma intonation" checkbox, with NVDA and the wrapper stubbed.

The setting must exist only where it can work.  A new driver may meet an old
wrapper, or a TTS.dll the wrapper does not know; then the checkbox is not
offered, and nothing else about the driver changes.
"""
import pytest

from test_pitch_path import driverModule  # noqa: F401  (a fixture)


def _make(driverModule, commaSupported):
    brailab, fake = driverModule
    fake.commaSupported = commaSupported
    d = brailab.SynthDriver()
    fake.calls[:] = []
    return d, fake


def _ids(d):
    return [s.id for s in d._get_supportedSettings()]


@pytest.fixture(autouse=True)
def _reset(driverModule):
    yield
    driverModule[1].commaSupported = None


def test_the_checkbox_is_offered_when_the_wrapper_can_do_it(driverModule):
    d, _fake = _make(driverModule, True)
    assert _ids(d) == ["voice", "rate", "pitch", "volume", "useIntonation", "softComma"]


@pytest.mark.parametrize("supported", [False, None])
def test_no_checkbox_with_an_old_wrapper_or_an_unknown_tts_dll(driverModule, supported):
    """False: the wrapper said no.  None: a _brailab that never heard of it."""
    d, _fake = _make(driverModule, supported)
    assert _ids(d) == ["voice", "rate", "pitch", "volume", "useIntonation"]


def test_it_is_off_until_asked_for(driverModule):
    d, fake = _make(driverModule, True)
    assert d._get_softComma() is False
    assert not [c for c in fake.calls if c[0] == "set_comma_style"]


def test_checking_and_unchecking_reach_the_wrapper(driverModule):
    d, fake = _make(driverModule, True)
    d._set_softComma(True)
    assert d._get_softComma() is True
    d._set_softComma(False)
    assert d._get_softComma() is False
    assert [c for c in fake.calls if c[0] == "set_comma_style"] == [
        ("set_comma_style", 1), ("set_comma_style", 0)]


def test_setting_it_without_support_does_nothing(driverModule):
    """NVDA may still hold softComma = True in a profile saved with a newer wrapper."""
    d, fake = _make(driverModule, False)
    d._set_softComma(True)
    assert d._get_softComma() is False
    assert not [c for c in fake.calls if c[0] == "set_comma_style"]
