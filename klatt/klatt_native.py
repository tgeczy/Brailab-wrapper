# -*- coding: utf-8 -*-
"""The Klatt synthesizer (csrc/klatt.c) through ctypes: frames in, numpy audio out.

    from klatt import klatt_native as kn
    s = kn.Synth()                     # the papers' defaults: 10 kHz, KLGLOTT88 source
    s.frame(f=[700, 1220, 2600, 3250, 3700, 4900], b=[130, 70, 160, 200, 200, 1000])
    audio = s.run(5000) / kn.full_scale()
"""
import ctypes
import os
import platform
import struct

import numpy as np

_c_double_p = ctypes.POINTER(ctypes.c_double)

CONFIG_FIELDS = ("sample_rate", "samples_per_frame", "n_cascade", "source", "all_parallel",
                 "tap", "seed", "gain_db")
TAP_OUTPUT, TAP_VOICING, TAP_ASPIRATION, TAP_FRICATION = 0, 1, 2, 3
SOURCE_IMPULSIVE, SOURCE_KLGLOTT88 = 1, 2


class Config(ctypes.Structure):
    """Mirror of klatt_config: all doubles, in the header's order."""
    _fields_ = [(name, ctypes.c_double) for name in CONFIG_FIELDS]


class Frame(ctypes.Structure):
    """Mirror of klatt_frame: all doubles, in the header's order."""
    _fields_ = [("f0", ctypes.c_double), ("av", ctypes.c_double), ("avs", ctypes.c_double),
                ("ah", ctypes.c_double), ("af", ctypes.c_double), ("oq", ctypes.c_double),
                ("tl", ctypes.c_double), ("fl", ctypes.c_double),
                ("f", ctypes.c_double * 6), ("b", ctypes.c_double * 6),
                ("fnp", ctypes.c_double), ("bnp", ctypes.c_double),
                ("fnz", ctypes.c_double), ("bnz", ctypes.c_double),
                ("a", ctypes.c_double * 6), ("an", ctypes.c_double), ("ab", ctypes.c_double),
                ("bp", ctypes.c_double * 6)]


def _lib_path():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bin")
    if os.name == "nt":
        return os.path.join(here, "x64" if struct.calcsize("P") == 8 else "x86", "klatt.dll")
    return os.path.join(here, "linux-" + platform.machine(), "libklatt.so")


_lib = None


def load():
    """The library, or None if it hasn't been built (python csrc/build_native.py)."""
    global _lib
    if _lib is None:
        path = _lib_path()
        if not os.path.exists(path):
            return None
        lib = ctypes.CDLL(path)
        lib.klatt_state_size.restype = ctypes.c_int
        lib.klatt_config_defaults.argtypes = [ctypes.POINTER(Config)]
        lib.klatt_config_defaults.restype = None
        lib.klatt_frame_defaults.argtypes = [ctypes.POINTER(Frame)]
        lib.klatt_frame_defaults.restype = None
        lib.klatt_init.argtypes = [ctypes.c_void_p, ctypes.POINTER(Config)]
        lib.klatt_init.restype = ctypes.c_int
        lib.klatt_set_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(Frame)]
        lib.klatt_set_frame.restype = None
        lib.klatt_run.argtypes = [ctypes.c_void_p, ctypes.c_int, _c_double_p]
        lib.klatt_run.restype = None
        lib.klatt_full_scale.restype = ctypes.c_double
        lib.klatt_resonator.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, _c_double_p]
        lib.klatt_resonator.restype = None
        _lib = lib
    return _lib


def full_scale():
    return load().klatt_full_scale()


def resonator(f, bw, sample_rate=10000.0):
    """(A, B, C) of the papers' digital resonator."""
    abc = (ctypes.c_double * 3)()
    load().klatt_resonator(f, bw, sample_rate, abc)
    return tuple(abc)


def default_config():
    c = Config()
    load().klatt_config_defaults(ctypes.byref(c))
    return c


def default_frame():
    f = Frame()
    load().klatt_frame_defaults(ctypes.byref(f))
    return f


def _fill(struct_, values):
    for name, value in values.items():
        if not hasattr(struct_, name):
            raise TypeError("no parameter named %r" % name)
        current = getattr(struct_, name)
        if hasattr(current, "__len__"):
            if len(value) != len(current):
                raise ValueError("%s takes %d values" % (name, len(current)))
            current[:] = [float(v) for v in value]
        else:
            setattr(struct_, name, float(value))


class Synth:
    """One running synthesizer.  Keyword arguments are klatt_config fields."""

    def __init__(self, **config):
        self.lib = load()
        if self.lib is None:
            raise OSError("no native library at " + _lib_path())
        self.config = default_config()
        _fill(self.config, config)
        self._state = ctypes.create_string_buffer(self.lib.klatt_state_size())
        if self.lib.klatt_init(self._state, ctypes.byref(self.config)):
            raise ValueError("klatt_init refused the config")
        self.current = default_frame()
        self.lib.klatt_set_frame(self._state, ctypes.byref(self.current))

    def frame(self, **values):
        """Change some parameters; the rest stay as they are.  In force from the next sample."""
        _fill(self.current, values)
        self.lib.klatt_set_frame(self._state, ctypes.byref(self.current))
        return self

    def run(self, n):
        out = np.empty(n)
        if n:
            self.lib.klatt_run(self._state, n, out.ctypes.data_as(_c_double_p))
        return out
