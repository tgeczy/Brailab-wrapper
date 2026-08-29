# -*- coding: utf-8 -*-
"""Say the five cardinal vowels through the software PCF8200 (formant layer)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from pcf8200 import Chip, Voice, VOWELS

v = Voice(pitch=120)
for ph in "aeiou":
    v.vowel(VOWELS[ph], dur=0.26)
    v.silence(0.05)

chip = Chip()
chip.to_wav("vowels.wav", chip.render(v))
print("wrote vowels.wav  (a e i o u)")
