# -*- coding: utf-8 -*-
"""A Polish-flavoured demo -- vowels from the POLISH starter table + an 'sz'.

This is exactly the experiment the library is meant for: supply your language's
formant values and the chip speaks it.  Refine POLISH in pcf8200/phonemes.py
against native recordings (Praat LPC) to taste.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from pcf8200 import Chip, Voice, POLISH, FRICATIVES

v = Voice(pitch=115)
# "a - e - i - o - u - y"  then  "o sz a"
for ph in ["a", "e", "i", "o", "u", "y"]:
    v.vowel(POLISH[ph], dur=0.24); v.silence(0.05)
v.vowel(POLISH["o"], dur=0.16).fricative(**FRICATIVES["sz"], dur=0.16).vowel(POLISH["a"], dur=0.20)

chip = Chip()
chip.to_wav("polish.wav", chip.render(v))
print("wrote polish.wav  (Polish vowels + o-sz-a)")
