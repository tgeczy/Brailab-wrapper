# -*- coding: utf-8 -*-
"""The real brailab_wrapper.dll and the real TTS.dll: API version 2 and the comma style.

Needs 32-bit Python and TTS.dll with its data beside the driver.  TTS.dll is its
authors' work and is not in the repository, so without it these tests skip.

The comma rule is changed in the loaded copy of TTS.dll only.  The tests read
that memory back to see what the wrapper wrote, and check at the end that the
file on disk is still what it was.
"""
import ctypes
import hashlib
import os
import struct
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVERS = os.path.join(os.path.dirname(HERE), "synthDrivers")
WRAPPER = os.path.join(DRIVERS, "brailab_wrapper.dll")
TTS = os.path.join(DRIVERS, "Brailab", "TTS.dll")

pytestmark = [
    pytest.mark.skipif(struct.calcsize("P") != 4, reason="TTS.dll is 32-bit: run with 32-bit Python"),
    pytest.mark.skipif(not os.path.isfile(TTS), reason="TTS.dll is not in the repository"),
]

# offset of the value (one past the B9 opcode) -> (original, soft)
SITES = {0x37AB: (480, 0), 0x3821: (-240, -120), 0x3831: (60, 60), 0x386F: (-300, -150),
         0x3899: (480, 0), 0x38AE: (-90, -45), 0x38EC: (-160, -80), 0x3930: (480, 0)}
DONE, ERROR = 2, 3


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Wrapper(object):
    def __init__(self):
        self.sha_before = _sha(TTS)
        w = self.dll = ctypes.cdll.LoadLibrary(WRAPPER)
        w.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int)
        w.bl_initW.restype = ctypes.c_void_p
        w.bl_free.argtypes = (ctypes.c_void_p,)
        w.bl_startSpeakW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
        w.bl_read.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                              ctypes.c_void_p, ctypes.c_int)
        for name in ("bl_commaStyleSupported", "bl_getCommaStyle"):
            getattr(w, name).argtypes = (ctypes.c_void_p,)
        w.bl_setCommaStyle.argtypes = (ctypes.c_void_p, ctypes.c_int)
        self.handle = w.bl_initW(TTS, 1500)
        assert self.handle, "bl_initW failed"
        # A second reference to the module the wrapper loaded, to read its memory.
        self.module = ctypes.WinDLL(TTS)
        self.base = self.module._handle
        self.buf = ctypes.create_string_buffer(65536)

    def values(self):
        return {off: struct.unpack("<i", ctypes.string_at(self.base + off, 4))[0] for off in SITES}

    def say(self, text):
        """Speak to the end; return the PCM."""
        kind, value = ctypes.c_int(), ctypes.c_int()
        assert self.dll.bl_startSpeakW(self.handle, text, 0) == 0
        pcm, deadline = bytearray(), time.time() + 30
        while time.time() < deadline:
            n = self.dll.bl_read(self.handle, ctypes.byref(kind), ctypes.byref(value), self.buf, len(self.buf))
            if kind.value == 1 and n > 0:
                pcm += self.buf.raw[:n]
            elif kind.value in (DONE, ERROR):
                assert kind.value == DONE, "wrapper error %d" % value.value
                return bytes(pcm)
            else:
                time.sleep(0.002)
        raise AssertionError("no DONE within 30 s")


@pytest.fixture(scope="module")
def wrapper():
    w = Wrapper()
    yield w
    if w.handle:
        w.dll.bl_free(w.handle)


def test_it_reports_api_version_2(wrapper):
    assert wrapper.dll.bl_getApiVersion() == 2


def test_this_tts_dll_is_the_build_it_knows(wrapper):
    assert wrapper.dll.bl_commaStyleSupported(wrapper.handle) == 1


def test_untouched_until_asked(wrapper):
    assert wrapper.dll.bl_getCommaStyle(wrapper.handle) == 0
    assert wrapper.say("Szia, világ.")
    assert wrapper.values() == {off: orig for off, (orig, _soft) in SITES.items()}


def test_soft_takes_effect_from_the_next_utterance_and_changes_the_speech(wrapper):
    text = "Szép, csendes szombat este, szia."
    original = wrapper.say(text)

    assert wrapper.dll.bl_setCommaStyle(wrapper.handle, 1) == 0
    assert wrapper.dll.bl_getCommaStyle(wrapper.handle) == 1
    # Not yet: the engine may be speaking.  The worker writes it before the next utterance.
    assert wrapper.values() == {off: orig for off, (orig, _soft) in SITES.items()}
    soft = wrapper.say(text)
    assert wrapper.values() == {off: s for off, (_orig, s) in SITES.items()}
    assert soft and soft != original

    assert wrapper.dll.bl_setCommaStyle(wrapper.handle, 0) == 0
    again = wrapper.say(text)
    assert wrapper.values() == {off: orig for off, (orig, _soft) in SITES.items()}
    assert len(again) == len(original)


def test_every_utterance_finishes_even_when_tts_dll_loses_its_callback(wrapper):
    """TTS.dll now and then never reports an utterance finished (see utteranceWentQuiet
    in the wrapper).  Before the wrapper watched for that itself, about one short
    utterance in fifty hung until a three-minute watchdog; eleven of twelve runs of 120
    did.  say() fails if any takes longer than 30 seconds."""
    wrapper.dll.bl_getLostCallbackCount.argtypes = (ctypes.c_void_p,)
    before = wrapper.dll.bl_getLostCallbackCount(wrapper.handle)
    started = time.time()
    for text in ["Egy.", "Szia.", "a", "Igen, jó."] * 15:
        assert wrapper.say(text)
    # 60 short utterances are under 25 s of speech; a single hang alone would add 180 s.
    assert time.time() - started < 60
    assert wrapper.dll.bl_getLostCallbackCount(wrapper.handle) >= before


def test_a_style_that_does_not_exist_is_refused(wrapper):
    assert wrapper.dll.bl_setCommaStyle(wrapper.handle, 7) == 1
    assert wrapper.dll.bl_getCommaStyle(wrapper.handle) == 0


def test_freeing_the_wrapper_puts_the_original_values_back(wrapper):
    assert wrapper.dll.bl_setCommaStyle(wrapper.handle, 1) == 0
    wrapper.say("Egy, kettő.")
    assert wrapper.values()[0x3899] == 0
    wrapper.dll.bl_free(wrapper.handle)
    wrapper.handle = None
    # our own reference keeps the module mapped
    assert wrapper.values() == {off: orig for off, (orig, _soft) in SITES.items()}


def test_the_file_on_disk_never_changed(wrapper):
    assert _sha(TTS) == wrapper.sha_before
