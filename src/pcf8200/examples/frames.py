# -*- coding: utf-8 -*-
"""Drive the chip at its COMMAND level: start pitch, 5-byte frames, STOP.

Builds a steady /a/ from field codes chosen off the chip's own tables, exactly
the shape a BraiLab/Ciber board would clock in.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from pcf8200 import PCF8200, nearest_code, tables

chip = PCF8200(voice="male")
chip.pitch_hz(110)

F1 = nearest_code(700,  tables.MALE_F[0])
F2 = nearest_code(1220, tables.MALE_F[1])
F3 = nearest_code(2600, tables.MALE_F[2])
for _ in range(8):
    chip.frame_codes(F1=F1, F2=F2, F3=F3, F5=1, AM=13, PI=2, FD=2)
chip.stop()

chip.to_wav("a_command.wav")
print("wrote a_command.wav  (steady /a/ from raw frame codes)")
