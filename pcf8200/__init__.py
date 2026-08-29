# -*- coding: utf-8 -*-
"""pcf8200 -- a software Philips PCF8200 formant speech synthesiser in pure numpy.

The PCF8200 is the formant chip behind the Hungarian BraiLab and the Spanish
Ciber232 talkers for the blind (early 1990s).  This package is a from-scratch
software model of it -- matched by ear and by measurement to real silicon -- so
you can drive the chip from Python: either at its own command level (5-byte
frames + control writes, exactly what a board clocks in), or phonetically from
formant frequencies.  It speaks whatever formants you give it: Hungarian,
Spanish, Polish, anything.

Two ways in
-----------
1. The chip's command protocol (authentic):
       from pcf8200 import PCF8200
       chip = PCF8200(voice="male")
       chip.pitch_hz(110)
       chip.frame_codes(F1=22, F2=13, F3=4, AM=13, PI=2, FD=2)   # a steady /a/
       chip.stop()
       chip.to_wav("a.wav")

2. Phonetically, from formant frequencies (easiest for a new language):
       from pcf8200 import Chip, Voice, POLISH
       v = Voice(pitch=115)
       for ph in "mama":                       # (vowels shown; add consonants)
           if ph in POLISH: v.vowel(POLISH[ph])
       Chip().to_wav("mama.wav", Chip().render(v))

The quantization tables (tables.py) state the chip's factual code->Hz behaviour
and are free to use; the frame/byte protocol is the public Philips datasheet.
"""
from .chip import Chip, render, write_wav, RATE, TILT_HZ, LOWPASS_HZ
from .device import PCF8200
from .voice import Voice
from .protocol import (decode_frame, encode_frame, decode_control, control_byte,
                       frame_params, nearest_code, FS_TAB, FD_MULT)
from .phonemes import VOWELS, POLISH, FRICATIVES
from . import tables

__version__ = "1.0.0"
__all__ = ["PCF8200", "Chip", "Voice", "render", "write_wav",
           "decode_frame", "encode_frame", "decode_control", "control_byte",
           "frame_params", "nearest_code", "VOWELS", "POLISH", "FRICATIVES",
           "tables", "RATE", "FS_TAB", "FD_MULT"]
