# -*- coding: utf-8 -*-
"""Switching away from the synthesizer and back, in one process.

TTS.dll starts two threads it cannot end.  The wrapper used to unload it in
bl_free all the same: each round leaked those two threads, asleep in unmapped
code, and where TTS.dll had been the only user of winmm.dll the hooks went with
it, so from the second bl_initW on the voice returned no audio at all.  bl_free
now leaves TTS.dll loaded and bl_initW takes the same engine up again.

Run in a process of its own, where nothing else holds winmm.dll: that is the
case that went silent.
"""
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
import ctypes, os, sys, time
wrapper, tts = sys.argv[1], sys.argv[2]
k32 = ctypes.windll.kernel32
k32.GetModuleHandleW.restype = ctypes.c_void_p
k32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
w = ctypes.cdll.LoadLibrary(wrapper)
w.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int); w.bl_initW.restype = ctypes.c_void_p
w.bl_free.argtypes = (ctypes.c_void_p,)
w.bl_startSpeakW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
w.bl_read.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                      ctypes.c_void_p, ctypes.c_int)
buf = ctypes.create_string_buffer(65536)
kind, value = ctypes.c_int(), ctypes.c_int()
sizes, bases = [], []
for rnd in range(3):
    h = w.bl_initW(tts, 1500)
    assert h, "bl_initW failed in round %d" % rnd
    bases.append(k32.GetModuleHandleW("TTS.dll"))
    w.bl_startSpeakW(h, "Szia, világ.", 0)
    got, deadline = 0, time.time() + 20
    while time.time() < deadline:
        n = w.bl_read(h, ctypes.byref(kind), ctypes.byref(value), buf, len(buf))
        if kind.value == 1:
            got += n
        elif kind.value in (2, 3):
            break
        else:
            time.sleep(0.001)
    sizes.append(got)
    w.bl_free(h)
    assert k32.GetModuleHandleW("TTS.dll"), "TTS.dll was unloaded while its threads live"
print(sizes, len(set(bases)))
sys.stdout.flush()
os._exit(0)
"""


def test_the_voice_still_speaks_after_free_and_init_again():
    out = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", SCRIPT, os.path.join(DRIVERS, "brailab_wrapper.dll"), TTS],
        capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    sizes, modules = eval(out.stdout.strip().rsplit("]", 1)[0] + "]"), int(out.stdout.strip().rsplit(" ", 1)[1])
    assert len(sizes) == 3 and min(sizes) > 0, "a round returned no audio: %r" % (sizes,)
    assert len(set(sizes)) == 1, "the same text came out differently after a restart: %r" % (sizes,)
    assert modules == 1, "TTS.dll was loaded more than once"
