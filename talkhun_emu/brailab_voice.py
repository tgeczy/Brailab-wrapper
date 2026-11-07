# -*- coding: utf-8 -*-
"""The whole emulated voice (csrc/brailab_voice.c) through ctypes: text in, PCM out.

Standard library only, so an add-on carries this file and the library and nothing
else.  The program is given as bytes: it is the authors', and not in this repository.
"""
import codecs
import ctypes
import os
import platform
import struct

BLOCK = 4000
RATE = 10000
_short_p = ctypes.POINTER(ctypes.c_short)

# BRAILAB_VOICE_UNKNOWN, for each character CP852 hasn't got
codecs.register_error("brailab_voice", lambda e: (b"\x1a" * (e.end - e.start), e.end))


def _lib_path():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bin")
    if os.name == "nt":
        return os.path.join(here, "x64" if struct.calcsize("P") == 8 else "x86", "talkhun.dll")
    return os.path.join(here, "linux-" + platform.machine(), "libtalkhun.so")


_lib = None


def load_library():
    """The library, or None if it isn't here."""
    global _lib
    if _lib is None:
        path = _lib_path()
        if not os.path.exists(path):
            return None
        lib = ctypes.CDLL(path)
        lib.brailab_voice_create.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.brailab_voice_create.restype = ctypes.c_void_p
        lib.brailab_voice_destroy.argtypes = [ctypes.c_void_p]
        lib.brailab_voice_destroy.restype = None
        lib.brailab_voice_begin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                            ctypes.c_double, ctypes.c_double, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_double]
        lib.brailab_voice_read.argtypes = [ctypes.c_void_p, _short_p, ctypes.c_int]
        _lib = lib
    return _lib


class Voice:
    """One voice: one thread at a time."""

    def __init__(self, image):
        self.lib = load_library()
        self._v = self.lib.brailab_voice_create(image, len(image))
        if not self._v:
            raise RuntimeError("TALKHUN0 did not install")
        self._buffer = (ctypes.c_short * BLOCK)()

    def close(self):
        if self._v:
            self.lib.brailab_voice_destroy(self._v)
            self._v = None

    def begin(self, text, pitch=1.0, time_scale=1.0, furcsa=False, intonation=True, gain=1.0):
        if isinstance(text, str):
            text = text.encode("cp852", "brailab_voice")
        if self.lib.brailab_voice_begin(self._v, text, len(text), pitch, time_scale,
                                        int(furcsa), int(intonation), gain):
            raise ValueError("a setting is out of range")

    def read(self):
        """The next PCM bytes, b"" when the utterance is over."""
        n = self.lib.brailab_voice_read(self._v, self._buffer, BLOCK)
        if n < 0:
            raise RuntimeError("the engine stopped")
        return ctypes.string_at(self._buffer, n * 2)

    def stream(self, text, **settings):
        """Each block of `text`, as PCM bytes."""
        self.begin(text, **settings)
        while True:
            pcm = self.read()
            if not pcm:
                return
            yield pcm
