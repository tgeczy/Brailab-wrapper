# -*- coding: utf-8 -*-
"""The audio core in C (csrc/pcf8200.c), with the same interface as pcf8200_core.Core.

pcf8200_core.py stays the reference: research and tuning happen there, and
tests/test_native.py holds the two together.  The parameters are the reference's,
passed down as one struct, so there is nothing to keep in step by hand.
"""
import ctypes
import os
import platform
import struct

import numpy as np

try:
    from . import pcf8200_core as core
except ImportError:
    import pcf8200_core as core

MAX_FORMANTS = 5
_c_double_p = ctypes.POINTER(ctypes.c_double)
_c_ubyte_p = ctypes.POINTER(ctypes.c_ubyte)


class _Params(ctypes.Structure):
    """Mirror of pcf8200_params (csrc/pcf8200.h): all doubles, in the header's order."""
    _fields_ = [("rate", ctypes.c_double), ("source_tilt_hz", ctypes.c_double),
                ("noise_gain", ctypes.c_double), ("pitch_min_hz", ctypes.c_double),
                ("pitch_max_hz", ctypes.c_double), ("harmonic_fade", ctypes.c_double),
                ("lowpass", ctypes.c_double), ("lp_sos", ctypes.c_double * 10),
                ("highpass_hz", ctypes.c_double), ("gain", ctypes.c_double),
                ("knee", ctypes.c_double), ("seed", ctypes.c_double)]


def params(source_tilt=core.TILT_HZ, noise_gain=core.NOISE_GAIN, seed=core.SEED,
           lowpass=True, highpass=core.HIGHPASS_HZ, gain=1.0, knee=0.0):
    """The struct for these Core arguments."""
    p = _Params()
    p.rate = core.RATE
    p.source_tilt_hz = source_tilt or 0.0
    p.noise_gain = noise_gain
    p.pitch_min_hz = core.PITCH_MIN_HZ
    p.pitch_max_hz = core.PITCH_MAX_HZ
    p.harmonic_fade = core.HARMONIC_FADE
    p.lowpass = 1.0 if lowpass else 0.0
    p.lp_sos[:] = core.LP_SOS[0] + core.LP_SOS[1]
    p.highpass_hz = highpass or 0.0
    p.gain = gain
    p.knee = knee or 0.0
    p.seed = seed & 0xFFFFFFFF
    return p


def _lib_path():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bin")
    if os.name == "nt":
        return os.path.join(here, "x64" if struct.calcsize("P") == 8 else "x86", "pcf8200.dll")
    return os.path.join(here, "linux-" + platform.machine(), "libpcf8200.so")


_lib = None


def load():
    """The library, or None if it isn't here."""
    global _lib
    if _lib is None:
        path = _lib_path()
        if not os.path.exists(path):
            return None
        lib = ctypes.CDLL(path)
        lib.pcf8200_init.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(_Params)]
        lib.pcf8200_run.argtypes = [ctypes.c_void_p, _c_double_p, _c_double_p, _c_ubyte_p,
                                    _c_double_p, _c_double_p, ctypes.c_int, _c_double_p]
        lib.pcf8200_run.restype = None
        lib.pcf8200_phase.argtypes = [ctypes.c_void_p]
        lib.pcf8200_phase.restype = ctypes.c_double
        lib.pcf8200_noise_state.argtypes = [ctypes.c_void_p]
        lib.pcf8200_noise_state.restype = ctypes.c_uint32
        _lib = lib
    return _lib


def _doubles(a):
    return a.ctypes.data_as(_c_double_p)


class NativeCore:
    """core.Core, in C."""

    def __init__(self, nf, **kw):
        self.lib = load()
        if self.lib is None:
            raise OSError("no native library at " + _lib_path())
        self.nf = nf
        self._state = ctypes.create_string_buffer(self.lib.pcf8200_core_size())
        self._params = params(**kw)
        if self.lib.pcf8200_init(self._state, nf, ctypes.byref(self._params)):
            raise ValueError("nf must be 1 to %d" % MAX_FORMANTS)

    @property
    def phase(self):
        return self.lib.pcf8200_phase(self._state)

    @property
    def noise_state(self):
        return self.lib.pcf8200_noise_state(self._state)

    def run(self, amp, pitch, voiced, fc, bw):
        n = len(amp)
        if n == 0:
            return np.zeros(0)
        amp = np.ascontiguousarray(amp, dtype=float)
        pitch = np.ascontiguousarray(pitch, dtype=float)
        voiced = np.ascontiguousarray(voiced, dtype=np.uint8)
        fc = np.ascontiguousarray(fc, dtype=float)
        bw = np.ascontiguousarray(bw, dtype=float)
        out = np.empty(n)
        self.lib.pcf8200_run(self._state, _doubles(amp), _doubles(pitch),
                             voiced.ctypes.data_as(_c_ubyte_p), _doubles(fc), _doubles(bw),
                             n, _doubles(out))
        return out
