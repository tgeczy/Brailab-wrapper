# -*- coding: utf-8 -*-
"""TALKHUN0 on MAME's 8086 (csrc/talkhun_host.c), with talkhun.py's interface.

The program is given as bytes: it is the authors', and not in this repository.
"""
import ctypes
import os
import platform
import struct

DELIMITERS = '.,;:?!'
_KINDS = ('frame', 'ctrl', 'pitch')
_LENGTHS = (5, 2, 1)


class _Item(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_int), ("data", ctypes.c_ubyte * 5)]


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
        lib.talkhun_create.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.talkhun_create.restype = ctypes.c_void_p
        lib.talkhun_destroy.argtypes = [ctypes.c_void_p]
        lib.talkhun_destroy.restype = None
        lib.talkhun_reset.argtypes = [ctypes.c_void_p]
        lib.talkhun_feed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.talkhun_capture.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                        ctypes.POINTER(ctypes.POINTER(_Item))]
        _lib = lib
    return _lib


class Talkhun:
    def __init__(self, image):
        self.lib = load_library()
        self._t = self.lib.talkhun_create(image, len(image))
        if not self._t:
            raise RuntimeError("TALKHUN0 did not install")

    def close(self):
        if self._t:
            self.lib.talkhun_destroy(self._t)
            self._t = None

    def reset(self):
        if self.lib.talkhun_reset(self._t):
            raise RuntimeError("reset did not return")

    def feed(self, text):
        if isinstance(text, str):
            text = text.encode('cp852', 'replace')
        if self.lib.talkhun_feed(self._t, text, len(text)):
            raise RuntimeError("feed did not return")

    def capture(self, text):
        """[('frame', [5 bytes]) | ('ctrl', [2]) | ('pitch', byte), ...]"""
        if not text:
            return []
        if isinstance(text, str):
            text = text.encode('cp852', 'replace')
        items = ctypes.POINTER(_Item)()
        n = self.lib.talkhun_capture(self._t, text, len(text), ctypes.byref(items))
        if n < 0:
            raise RuntimeError("capture did not return")
        out = []
        for i in range(n):
            kind = items[i].kind
            body = list(items[i].data[:_LENGTHS[kind]])
            out.append((_KINDS[kind], body[0] if kind == 2 else body))
        return out
