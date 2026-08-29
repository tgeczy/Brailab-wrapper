# -*- coding: utf-8 -*-
"""The PCF8200 command protocol: 5-byte speech frames + 2-byte control writes.

This is the chip's own wire format -- the same bytes a BraiLab or Ciber board
clocks into the PCF8200 -- expressed in Python so you can build, decode and
render it.  Frame layout (Philips datasheet Fig. 4):

    byte 0: B1[2:0] | F1[4:0]
    byte 1: F5[0]   | B5[1:0] | PI[4:0]
    byte 2: FD[1]   | F3[2:0] | AM[3:0]
    byte 3: FD[0]   | B3[1:0] | F2[4:0]
    byte 4: B4[1:0] | F4[2:0] | B2[2:0]

Control write (Fig. 5) is two bytes 0x00 then:
    D7=1 D6=0 D5=STOP D4=M/F D3=0 D2=0 D1=FS1 D0=FS0
M/F selects the female (four-formant) quantization table.

Each frame carries short codes; the chip's ROM (tables.py) expands them into
formant centre frequencies/bandwidths (Hz), an amplitude and a pitch increment.
"""
from . import tables as T

# FS1/FS0 -> (relative speed, nominal standard-frame duration in ms)
FS_TAB = {0: (1.00, 12.8), 1: (1.45, 8.8), 2: (1.23, 10.4), 3: (0.73, 17.6)}
FD_MULT = (1, 2, 3, 5)          # per-frame FD field multiplies the duration
PI_NOISE = 16                   # PI code 16 = unvoiced (noise excitation)
CODEC_OFFSET = 0                # formant codes index the tables directly

#: Field widths (max code) for building frames.
FIELD_MAX = dict(F1=31, F2=31, F3=7, F4=7, F5=1,
                 B1=7, B2=7, B3=3, B4=3, B5=3, AM=15, PI=31, FD=3)


def decode_frame(f):
    """Unpack one 5-byte frame (bytes/list) into its field codes."""
    b0, b1, b2, b3, b4 = f
    return {
        'B1': (b0 >> 5) & 7, 'F1': b0 & 0x1F,
        'F5': (b1 >> 7) & 1, 'B5': (b1 >> 5) & 3, 'PI': b1 & 0x1F,
        'FD': (((b2 >> 7) & 1) << 1) | ((b3 >> 7) & 1),
        'F3': (b2 >> 4) & 7, 'AM': b2 & 0x0F,
        'B3': (b3 >> 5) & 3, 'F2': b3 & 0x1F,
        'B4': (b4 >> 6) & 3, 'F4': (b4 >> 3) & 7, 'B2': b4 & 7,
    }


def encode_frame(F1=0, F2=0, F3=0, F4=0, F5=0, B1=0, B2=0, B3=0, B4=0, B5=0,
                 AM=0, PI=0, FD=0):
    """Build a 5-byte frame from field codes (inverse of decode_frame)."""
    g = {k: int(v) for k, v in dict(F1=F1, F2=F2, F3=F3, F4=F4, F5=F5, B1=B1,
                                    B2=B2, B3=B3, B4=B4, B5=B5, AM=AM, PI=PI,
                                    FD=FD).items()}
    for k, v in g.items():
        if not (0 <= v <= FIELD_MAX[k]):
            raise ValueError("%s code %d out of range 0..%d" % (k, v, FIELD_MAX[k]))
    b0 = (g['B1'] << 5) | g['F1']
    b1 = (g['F5'] << 7) | (g['B5'] << 5) | g['PI']
    b2 = (((g['FD'] >> 1) & 1) << 7) | (g['F3'] << 4) | g['AM']
    b3 = ((g['FD'] & 1) << 7) | (g['B3'] << 5) | g['F2']
    b4 = (g['B4'] << 6) | (g['F4'] << 3) | g['B2']
    return bytes([b0, b1, b2, b3, b4])


def decode_control(c):
    """Unpack a control write (last byte carries the flags)."""
    b = c[-1] if hasattr(c, '__len__') else c
    return {'is_control': bool(b & 0x80), 'stop': bool(b & 0x20),
            'female': bool(b & 0x10), 'fs': b & 0x03,
            'speed': FS_TAB[b & 0x03][0], 'frame_ms': FS_TAB[b & 0x03][1]}


def control_byte(stop=False, female=False, fs=0):
    """Build the control-write flag byte (send as bytes([0x00, this]))."""
    return 0x80 | (0x20 if stop else 0) | (0x10 if female else 0) | (fs & 3)


def nearest_code(hz, ladder):
    """Nearest quantization code for a target frequency `hz` in a table ladder."""
    return min(range(len(ladder)), key=lambda i: abs(ladder[i] - hz))


def frame_params(d, female=False, ampl_compress=1.0):
    """Expand a decoded frame's codes into control values via the chip tables.

    Returns dict: formants [(Hz, bandwidthHz), ...] (5 male / 4 female), linear
    `ampl`, pitch increment `pi` (Hz per standard frame), and `noise` (bool).
    """
    off = CODEC_OFFSET
    if female:
        F, B = T.FEMALE_F, T.FEMALE_B
        formants = [
            (F[0][min(d['F1'] + off, 31)], B[0][d['B1']]),
            (F[1][min(d['F2'] + off, 31)], B[1][d['B2']]),
            (F[2][min(d['F3'] + off, 7)],  B[2][d['B3']]),
            (F[3][min(d['F4'], 7)],        B[3][d['B4']]),
        ]
    else:
        F, B = T.MALE_F, T.MALE_B
        formants = [
            (F[0][min(d['F1'] + off, 31)], B[0][d['B1']]),
            (F[1][min(d['F2'] + off, 31)], B[1][d['B2']]),
            (F[2][min(d['F3'] + off, 7)],  B[2][d['B3']]),
            (F[3][min(d['F4'], 7)],        B[3][d['B4']]),
            (F[4][d['F5']],                B[4][d['B5']]),
        ]
    return {'formants': formants,
            'ampl': (T.AMPL[d['AM']]) ** ampl_compress,
            'pi': T.PI[d['PI']],
            'noise': d['PI'] == PI_NOISE}
