# -*- coding: utf-8 -*-
"""Drive the real brailab driver with NVDA stubbed out, and watch the pitch.

Capital pitch was debugged four times through NVDA itself, each round costing
Tomi an install and producing another plausible-but-wrong theory. This runs the
actual driver here instead: enough of NVDA to import it, a fake `_brailab` that
records every call, and the exact speech sequence NVDA builds for a capital
letter (`PitchCommand(30), "A", PitchCommand()`).

If set_pitch is not called with a raised value before the text is spoken, the
fault is in this driver and this test says where. If it is, the fault is
upstream and the driver is exonerated -- which is worth just as much.
"""
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
DRIVERS = os.path.join(ADDON, "synthDrivers")


class FakeBrailab(object):
    """Stands in for the IPC module, recording the order of everything."""

    def __init__(self):
        self.calls = []
        self.pitch = 0

    # -- what the driver calls --
    def initialize(self, index_callback=None):
        self.calls.append(("initialize",))
        return {"tempo": 4, "pitch": 0, "volume": 8}

    def has_composite(self):
        return True

    def set_pitch(self, v):
        self.calls.append(("set_pitch", v))
        self.pitch = v

    def set_tempo(self, v):
        self.calls.append(("set_tempo", v))

    def set_volume(self, v):
        self.calls.append(("set_volume", v))

    def begin_utterance(self, noIntonation=0):
        self.calls.append(("begin_utterance",))

    def add_text(self, t):
        # Record the pitch in force when the text was added, and the pitch the
        # host would actually latch, which is the one at commit time.
        self.calls.append(("add_text", t, self.pitch))

    def add_index(self, i):
        self.calls.append(("add_index", i))

    def commit_utterance(self):
        self.calls.append(("commit_utterance", self.pitch))

    def speak(self, text, noIntonation=0):
        self.calls.append(("speak", text, self.pitch))

    def stop(self):
        self.calls.append(("stop",))

    def pause(self, s):
        pass

    def terminate(self):
        pass

    def _find_tts_dll(self, base):
        return "fake.dll"

    # -- helpers for the tests --
    def pitchAt(self, kind):
        for c in self.calls:
            if c[0] == kind:
                return c[-1]
        return None


def _stub_nvda():
    """The pieces of NVDA the driver imports, and nothing more."""
    if "synthDriverHandler" in sys.modules:
        return

    logh = types.ModuleType("logHandler")

    class _Log(object):
        def __init__(self):
            self.messages = []

        def _rec(self, level, msg, *a, **k):
            self.messages.append((level, msg % a if a else msg))

        def info(self, m, *a, **k):
            self._rec("info", m, *a)

        def debug(self, m, *a, **k):
            self._rec("debug", m, *a)

        def warning(self, m, *a, **k):
            self._rec("warning", m, *a)

        def error(self, m, *a, **k):
            self._rec("error", m, *a)

        def isEnabledFor(self, lvl):
            return False

        DEBUG = 10

    logh.log = _Log()
    sys.modules["logHandler"] = logh

    # NVDA's real command classes: the driver's isinstance checks and the
    # `.offset` property must behave exactly as they do in NVDA.
    commands = types.ModuleType("speech.commands")

    class SynthCommand(object):
        pass

    class IndexCommand(SynthCommand):
        def __init__(self, index):
            self.index = index

    class BaseProsodyCommand(SynthCommand):
        def __init__(self, offset=0, multiplier=1):
            if offset != 0 and multiplier != 1:
                raise ValueError("offset and multiplier both specified")
            self._offset = offset
            self._multiplier = multiplier
            self.isDefault = offset == 0 and multiplier == 1

        @property
        def offset(self):
            if self._offset != 0:
                return self._offset
            if self._multiplier == 1:
                return 0
            raise RuntimeError("would need the synth's configured value")

    class PitchCommand(BaseProsodyCommand):
        pass

    class CharacterModeCommand(SynthCommand):
        def __init__(self, state):
            self.state = state

    class BreakCommand(SynthCommand):
        def __init__(self, time=0):
            self.time = time

    commands.IndexCommand = IndexCommand
    commands.PitchCommand = PitchCommand
    commands.CharacterModeCommand = CharacterModeCommand
    commands.BreakCommand = BreakCommand
    speech = types.ModuleType("speech")
    speech.commands = commands
    sys.modules["speech"] = speech
    sys.modules["speech.commands"] = commands

    sdh = types.ModuleType("synthDriverHandler")

    class _Setting(object):
        def __init__(self, *a, **k):
            self.id = (a[0] if a else k.get("id", "x"))

    class VoiceInfo(object):
        def __init__(self, id, name, language=None):
            self.id, self.name, self.language = id, name, language

    class SynthDriver(object):
        supportedCommands = frozenset()
        supportedSettings = ()

        @classmethod
        def VoiceSetting(cls, *a, **k):
            return _Setting("voice")

        @classmethod
        def RateSetting(cls, *a, **k):
            return _Setting("rate")

        @classmethod
        def PitchSetting(cls, *a, **k):
            return _Setting("pitch")

        @classmethod
        def VolumeSetting(cls, *a, **k):
            return _Setting("volume")

        def __init__(self):
            pass

        # The real conversions, verbatim from NVDA's SynthDriver.
        def _percentToParam(self, percent, min, max):
            return int(round(percent / 100.0 * (max - min) + min))

        def _paramToPercent(self, current, min, max):
            return int(round(float(current - min) / (max - min) * 100))

    class _Notifier(object):
        def notify(self, **k):
            pass

    sdh.SynthDriver = SynthDriver
    sdh.VoiceInfo = VoiceInfo
    sdh.synthDoneSpeaking = _Notifier()
    sdh.synthIndexReached = _Notifier()
    sys.modules["synthDriverHandler"] = sdh

    asu = types.ModuleType("autoSettingsUtils")
    ds = types.ModuleType("autoSettingsUtils.driverSetting")
    ds.DriverSetting = _Setting
    ds.BooleanDriverSetting = _Setting
    ds.NumericDriverSetting = _Setting
    asu.driverSetting = ds
    sys.modules["autoSettingsUtils"] = asu
    sys.modules["autoSettingsUtils.driverSetting"] = ds

    nvwave = types.ModuleType("nvwave")
    nvwave.WavePlayer = object
    sys.modules["nvwave"] = nvwave

    cfg = types.ModuleType("config")
    cfg.conf = {"speech": {"outputDevice": "default"},
                "audio": {"outputDevice": "default"}}
    sys.modules["config"] = cfg

    ep = types.ModuleType("extensionPoints")

    class Action(object):
        def register(self, f):
            pass

        def unregister(self, f):
            pass

        def notify(self, **k):
            pass

    ep.Action = Action
    sys.modules["extensionPoints"] = ep

    qh = types.ModuleType("queueHandler")
    qh.eventQueue = None
    qh.queueFunction = lambda q, f, *a, **k: f(*a, **k)
    sys.modules["queueHandler"] = qh

    import builtins
    if not hasattr(builtins, "_"):
        builtins._ = lambda s: s


@pytest.fixture(scope="module")
def driverModule():
    _stub_nvda()
    if ADDON not in sys.path:
        sys.path.insert(0, ADDON)
    # The driver does `from . import _brailab`, so it has to load as a member
    # of the synthDrivers package with the IPC module already stubbed in place.
    fake = FakeBrailab()
    pkg = types.ModuleType("synthDrivers")
    pkg.__path__ = [DRIVERS]
    sys.modules["synthDrivers"] = pkg
    sys.modules["synthDrivers._brailab"] = fake
    import importlib
    brailab = importlib.import_module("synthDrivers.brailab")
    return brailab, fake


@pytest.fixture
def driver(driverModule):
    brailab, fake = driverModule
    fake.calls[:] = []
    d = brailab.SynthDriver()
    fake.calls[:] = []
    return d, brailab, fake


def _speakAndWait(d, brailab, seq, timeout=5.0):
    """speak() hands the work to the driver's background thread, so wait for it."""
    import time
    d.speak(seq)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if brailab.bgQueue.unfinished_tasks == 0:
            break
        time.sleep(0.01)
    time.sleep(0.05)


def test_driver_advertises_pitch_command(driver):
    """Without this NVDA never sends a PitchCommand at all."""
    d, brailab, _fake = driver
    assert brailab.PitchCommand in d.supportedCommands


def test_capital_raises_the_pitch_before_the_text_is_spoken(driver):
    """The exact sequence NVDA builds for a capital letter.

    The pitch must be raised by the time the host latches it, which for the
    composite path is at commit_utterance().
    """
    d, brailab, fake = driver
    seq = [brailab.PitchCommand(offset=30), "A", brailab.PitchCommand()]
    _speakAndWait(d, brailab, seq)

    sets = [c for c in fake.calls if c[0] == "set_pitch"]
    assert sets, "set_pitch was never called: %r" % (fake.calls,)

    spoken = fake.pitchAt("speak")
    committed = fake.pitchAt("commit_utterance")
    effective = spoken if spoken is not None else committed
    assert effective is not None, "nothing was spoken at all: %r" % (fake.calls,)
    assert effective > 0, (
        "the capital was spoken at pitch %r, not raised. calls: %r"
        % (effective, fake.calls))


def test_pitch_returns_to_the_user_setting_afterwards(driver):
    """A capital must not leave the whole voice retuned."""
    d, brailab, fake = driver
    _speakAndWait(d, brailab, [brailab.PitchCommand(offset=30), "A",
                               brailab.PitchCommand()])
    assert fake.pitch == d._cachedPitch, (
        "pitch left at %r, user setting is %r" % (fake.pitch, d._cachedPitch))


def test_plain_text_never_touches_the_pitch(driver):
    d, _brailab, fake = driver
    _speakAndWait(d, _brailab, ["hello there"])
    assert not [c for c in fake.calls if c[0] == "set_pitch"]


def test_trailing_index_must_not_reset_the_capital_pitch(driver):
    """The real sequence NVDA sends, captured from a live session.

    NVDA follows the letter with an IndexCommand, which becomes a block of its
    own carrying no text and the pitch offset already back at 0. In the
    composite path the host latches the pitch at commit_utterance(), so that
    trailing block used to call set_pitch(0) *before* the commit and the capital
    came out at normal pitch -- with every earlier step in the chain correct,
    which is what made this so hard to see.
    """
    d, brailab, fake = driver
    seq = [
        brailab.PitchCommand(offset=30),
        sys.modules["speech.commands"].CharacterModeCommand(True),
        "A",
        brailab.PitchCommand(),
        brailab.IndexCommand(1),
    ]
    _speakAndWait(d, brailab, seq)

    committed = fake.pitchAt("commit_utterance")
    spoken = fake.pitchAt("speak")
    effective = spoken if spoken is not None else committed
    assert effective, (
        "capital latched at pitch %r; calls: %r" % (effective, fake.calls))
