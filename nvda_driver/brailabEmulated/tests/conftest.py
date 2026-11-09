# -*- coding: utf-8 -*-
"""Enough of NVDA to load and drive the emulated BraiLab driver outside NVDA.

Lifted from panthera-speech's tests, which lifted it from TGSpeechBox.  The fakes
model the behaviour that real driver bugs turned on, and nothing else:

* `WavePlayer.idle()` blocks until the audio drains, and `stop()` cuts it short.
* `stop()` costs `STREAM_START` on the next `feed()`, as tearing a real output
  stream down and starting it again does.
* `feed()`'s `onDone` fires once that chunk has finished sounding, never sooner,
  and `stop()` drops the waiting ones uncalled.  Indexes ride on exactly this.
* `synthDoneSpeaking` and `synthIndexReached` record when they fired.
* `SynthDriver`'s metaclass turns `_get_x`/`_set_x` into properties from the class's
  own namespace, as NVDA's AutoPropertyType does.

The driver is loaded as `synthDrivers.brailabEmulated` from the add-on laid out by
build.py, so its relative import is the one NVDA uses.  That needs TALKHUN0.COM and
the built library, neither in the repository, so without them every test skips.
"""
import os
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(ADDON_SRC))
STAGE = os.path.join(ROOT, "build", "test-addon")

#: What a real output stream costs to start after being stopped.
STREAM_START = 0.12
OUT_RATE = 10000.0


class FakeWavePlayer(object):
    """NVDA's player, in the ways the driver can tell."""

    def __init__(self, *a, **k):
        self.args = a
        self.pcm = bytearray()
        self.fed = 0
        self.stops = 0
        self.idles = 0
        self.startups = 0
        self.closed = False
        self._lock = threading.Lock()
        self._until = 0.0
        self._running = False
        self._callbacks = []            # (when the chunk ends, callback), in feed order

    def feed(self, data, size=None, onDone=None):
        with self._lock:
            self.fed += 1
            self.pcm += data
            now = time.perf_counter()
            if not self._running:
                self._running = True
                self.startups += 1
                now += STREAM_START
            self._until = max(self._until, now) + len(data) / 2.0 / OUT_RATE
            if onDone is not None:
                self._callbacks.append((self._until, onDone))
        self._fire()

    def _fire(self, everything=False):
        due = []
        with self._lock:
            now = time.perf_counter()
            while self._callbacks and (everything or self._callbacks[0][0] <= now):
                due.append(self._callbacks.pop(0)[1])
        for callback in due:
            callback()

    def stop(self):
        with self._lock:
            self.stops += 1
            self._until = 0.0
            self._running = False
            del self._callbacks[:]

    def idle(self):
        self.idles += 1
        while True:
            self._fire()
            with self._lock:
                left = self._until - time.perf_counter()
            if left <= 0:
                with self._lock:
                    self._running = False
                self._fire(everything=True)
                return
            time.sleep(min(left, 0.005))

    def pause(self, switch):
        pass

    def close(self):
        self.stop()
        self.closed = True


class Notifier(object):
    """Records each notification and lets a test wait for the next one."""

    def __init__(self):
        self.calls = []
        self._event = threading.Event()

    def notify(self, **k):
        self.calls.append((time.perf_counter(), k))
        self._event.set()

    def wait(self, timeout=10.0):
        ok = self._event.wait(timeout)
        self._event.clear()
        return ok

    def reset(self):
        del self.calls[:]
        self._event.clear()


def _install_fake_nvda():
    if "synthDriverHandler" in sys.modules:
        return

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    mod("nvwave", WavePlayer=FakeWavePlayer)

    class _Log(object):
        def __init__(self):
            self.messages = []

        def _rec(self, level, msg, *a, **k):
            self.messages.append((level, msg % a if a else msg))

        info = debug = debugWarning = warning = _rec

        def error(self, msg, *a, **k):
            self._rec("error", msg, *a)
    mod("logHandler", log=_Log())
    mod("config", conf={"audio": {"outputDevice": "default"},
                        "speech": {"outputDevice": "default"}})

    class IndexCommand(object):
        def __init__(self, index):
            self.index = index

    class PitchCommand(object):
        def __init__(self, offset=0, multiplier=1):
            self.offset = offset
    speech = mod("speech")
    speech.commands = mod("speech.commands", IndexCommand=IndexCommand,
                          PitchCommand=PitchCommand)

    class _Setting(object):
        def __init__(self, *a, **k):
            self.id = a[0] if a else k.get("id")
            self.displayName = a[1] if len(a) > 1 else k.get("displayName")
            self.defaultVal = k.get("defaultVal", a[2] if len(a) > 2 else None)

    class _AutoPropertyType(type):
        def __init__(cls, name, bases, namespace, **kw):
            super().__init__(name, bases, namespace, **kw)
            for attr in {k[5:] for k in namespace if k[:5] in ("_get_", "_set_")}:
                if attr in namespace:
                    raise TypeError("%s is already a class attribute" % attr)
                setattr(cls, attr, property(namespace.get("_get_" + attr),
                                            namespace.get("_set_" + attr)))

    def _builtin(setting_id):
        return lambda: _Setting(setting_id)

    class SynthDriver(object, metaclass=_AutoPropertyType):
        RateSetting = staticmethod(_builtin("rate"))
        PitchSetting = staticmethod(_builtin("pitch"))
        VolumeSetting = staticmethod(_builtin("volume"))

        def __init__(self):
            pass
    mod("synthDriverHandler", SynthDriver=SynthDriver, synthDoneSpeaking=Notifier(),
        synthIndexReached=Notifier())
    asu = mod("autoSettingsUtils")
    asu.driverSetting = mod("autoSettingsUtils.driverSetting", BooleanDriverSetting=_Setting)


def _stage_addon():
    """Lay the add-on out and put its synthDrivers on the package path, as NVDA's
    addonHandler does.  False if what it needs isn't on this machine."""
    sys.path.insert(0, ADDON_SRC)
    import build
    try:
        build.lay_out(STAGE)
    except SystemExit:
        return False
    if "synthDrivers" not in sys.modules:
        pkg = types.ModuleType("synthDrivers")
        pkg.__path__ = [os.path.join(STAGE, "synthDrivers")]
        sys.modules["synthDrivers"] = pkg
    return True


_install_fake_nvda()
STAGED = _stage_addon()
