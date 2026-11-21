# -*- coding: utf-8 -*-
"""The wrapper and the real TTS.dll, for the audit's findings that only the engine shows (#2).

TTS.dll says nothing at all for some text (a long run of colons, a few hundred characters of phone numbers):
no audio and no completion callback.  The wrapper used to wait three minutes for it and then end the utterance
with an error, dropping every index after it, so NVDA's say all stopped dead.  Now a piece with no audio two
seconds after its start is given up on, and the utterance goes on to its next part.

Each check runs in a process of its own (TTS.dll keeps state for the life of the process), under 32-bit Python,
and only where TTS.dll and its data files are present (they are not in the repository)."""
import os
import struct
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVERS = os.path.join(os.path.dirname(HERE), "synthDrivers")
TTS = os.path.join(DRIVERS, "Brailab", "TTS.dll")

pytestmark = [
    pytest.mark.skipif(struct.calcsize("P") != 4, reason="TTS.dll is 32-bit: run with 32-bit Python"),
    pytest.mark.skipif(not os.path.isfile(TTS), reason="TTS.dll is not in the repository"),
]

SCRIPT = r"""
import ctypes, sys, time
wrapper, tts = sys.argv[1], sys.argv[2]
w = ctypes.cdll.LoadLibrary(wrapper)
w.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int); w.bl_initW.restype = ctypes.c_void_p
for name, args in (("bl_beginUtterance", (ctypes.c_void_p, ctypes.c_int)), ("bl_addTextUtteranceW", (ctypes.c_void_p, ctypes.c_wchar_p)),
                   ("bl_addIndexUtterance", (ctypes.c_void_p, ctypes.c_int)), ("bl_commitUtterance", (ctypes.c_void_p,)),
                   ("bl_startSpeakW", (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int))):
    getattr(w, name).argtypes = args
w.bl_read.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_int)
h = w.bl_initW(tts, 1500)
assert h
buf = ctypes.create_string_buffer(65536)
kind, value = ctypes.c_int(), ctypes.c_int()

def read(limit):
    out, t0 = [], time.time()
    while time.time() - t0 < limit:
        n = w.bl_read(h, ctypes.byref(kind), ctypes.byref(value), buf, len(buf))
        k = kind.value
        if k == 1 and n > 0:
            if not out or out[-1][0] != "audio":
                out.append(["audio", 0])
            out[-1][1] += n
        elif k == 4:
            out.append(["index", value.value])
        elif k == 3:
            out.append(["error", value.value])
        elif k == 2:
            out.append(["done", round(time.time() - t0, 1)])
            return out
        else:
            time.sleep(0.001)
    out.append(["timeout", limit])
    return out

w.bl_beginUtterance(h, 0)
w.bl_addTextUtteranceW(h, "Első mondat.")
w.bl_addIndexUtterance(h, 1)
w.bl_addTextUtteranceW(h, ":" * 200)
w.bl_addIndexUtterance(h, 2)
w.bl_addTextUtteranceW(h, "Harmadik mondat.")
w.bl_addIndexUtterance(h, 3)
w.bl_commitUtterance(h)
print(read(40))
w.bl_startSpeakW(h, ":" * 200, 0)
print(read(40))
w.bl_startSpeakW(h, "Szia.", 0)
print(read(20))
sys.stdout.flush()
import os; os._exit(0)
"""


def _run():
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", SCRIPT, os.path.join(DRIVERS, "brailab_wrapper.dll"), TTS],
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr
    return [eval(line) for line in out.stdout.strip().splitlines()]


def test_a_silent_piece_is_given_up_on_and_the_utterance_goes_on():
    composite, alone, after = _run()
    kinds = [k for k, _ in composite]
    assert kinds == ["audio", "index", "index", "audio", "index", "done"], composite
    assert [v for k, v in composite if k == "index"] == [1, 2, 3]
    assert composite[-1][1] < 30, "the silent piece held the utterance up"
    assert [k for k, _ in alone] == ["done"] and alone[-1][1] < 5, alone
    assert after[0][0] == "audio" and after[-1][0] == "done", "the engine did not speak after a silent piece"
