# -*- coding: utf-8 -*-
"""
The PCF-8200 side: decode the 40-bit frames TALKHUN0 ships to the adapter.

Frame layout (datasheet page 5 / Fig. 4):
    byte 0: B1[2:0] | F1[4:0]
    byte 1: F5[0]   | B5[1:0] | PI[4:0]
    byte 2: FD[1]   | F3[2:0] | AM[3:0]
    byte 3: FD[0]   | B3[1:0] | F2[4:0]
    byte 4: B4[1:0] | F4[2:0] | B2[2:0]

Control write (datasheet Fig. 5) is two bytes, 0x00 then:
        D7  D6   D5    D4   D3  D2   D1   D0
         1   0  STOP  M/F   0   0   FS1  FS0
M/F is what BraiLab called "furcsa hang" -- it selects the female quantization
table and a four-formant filter, while the diad frames were authored for the
five-formant male model.  That mismatch is why it sounds odd rather than female.

Frequencies come from the MEA-8000 tables with a +1 index offset.  That offset
was inferred from Arato's thesis and is confirmed here against real hardware:
the /a/ steady state emitted by the binary is codec F1=21, F2=13, which maps to
622 Hz / 988 Hz against 625 Hz / 988 Hz measured by LPC from BraiLab audio.
"""

F1_TAB = [150, 162, 174, 188, 202, 217, 233, 250, 267, 286, 305, 325, 346, 368,
          391, 415, 440, 466, 494, 523, 554, 587, 622, 659, 698, 740, 784, 830,
          880, 932, 988, 1047]
F2_TAB = [440, 466, 494, 523, 554, 587, 622, 659, 698, 740, 784, 830, 880, 932,
          988, 1047, 1100, 1179, 1254, 1337, 1428, 1528, 1639, 1761, 1897,
          2047, 2214, 2400, 2609, 2842, 3105, 3400]
F3_TAB = [1179, 1337, 1528, 1761, 2047, 2400, 2842, 3400]
#: 2-bit bandwidth index, in Hz.
BW_TAB = [726, 309, 125, 50]

#: FS1/FS0 -> (relative speed, nominal frame duration in ms).  The talker maps
#: ESC S1..S4 onto 3, 0, 2, 1, so S1 is the slowest and S4 the fastest.
FS_TAB = {0: (1.00, 12.8), 1: (1.45, 8.8), 2: (1.23, 10.4), 3: (0.73, 17.6)}
#: Per-frame FD field multiplies the frame's duration.
FD_MULT = (1, 2, 3, 5)

#: The talker's pitch byte is linear in frequency at about this many Hz per
#: unit: HANGNOR sets '*' (42) for normal speech and that measures 107.3 Hz.
HZ_PER_PITCH_UNIT = 107.3 / 42.0


def decode_frame(f):
    """Unpack one 5-byte frame into its fields."""
    b0, b1, b2, b3, b4 = f
    return {
        'B1': (b0 >> 5) & 7, 'F1': b0 & 0x1F,
        'F5': (b1 >> 7) & 1, 'B5': (b1 >> 5) & 3, 'PI': b1 & 0x1F,
        'FD': (((b2 >> 7) & 1) << 1) | ((b3 >> 7) & 1),
        'F3': (b2 >> 4) & 7, 'AM': b2 & 0x0F,
        'B3': (b3 >> 5) & 3, 'F2': b3 & 0x1F,
        'B4': (b4 >> 6) & 3, 'F4': (b4 >> 3) & 7, 'B2': b4 & 7,
    }


def frame_hz(d):
    """Formant frequencies in Hz -- codes index the MEA-8000 tables directly.

    (An earlier +1 offset was a cross-dataset artifact: thesis codes describe
    TALKHUN0's diad data but were calibrated against TTS.dll/BINADATA audio,
    a different authoring.  Settled by ear against the original hardware.)
    """
    return {
        'F1': F1_TAB[min(d['F1'], len(F1_TAB) - 1)],
        'F2': F2_TAB[min(d['F2'], len(F2_TAB) - 1)],
        'F3': F3_TAB[min(d['F3'], len(F3_TAB) - 1)],
        'B1': BW_TAB[min(d['B1'] >> 1, 3)],
        'B2': BW_TAB[min(d['B2'] >> 1, 3)],
        'B3': BW_TAB[d['B3']],
        'B4': BW_TAB[d['B4']],
    }


def frame_ms(d, fs=0):
    """Nominal duration of one frame, honouring FS and the per-frame FD."""
    return FS_TAB[fs][1] * FD_MULT[d['FD']]


def decode_control(c):
    """Unpack the second byte of a control write."""
    b = c[-1]
    return {
        'is_control': bool(b & 0x80),
        'stop': bool(b & 0x20),
        'furcsa': bool(b & 0x10),       # M/F: female table + 4-formant filter
        'fs': b & 0x03,
        'speed': FS_TAB[b & 0x03][0],
        'frame_ms': FS_TAB[b & 0x03][1],
    }


def describe(frames, ctrls=(), fs=0):
    """A readable dump of a captured utterance."""
    out = []
    total = 0.0
    out.append("  #  raw            F1  F2 F3 AM PI FD  ->   F1Hz  F2Hz  F3Hz")
    out.append("-" * 66)
    for i, f in enumerate(frames):
        d = decode_frame(f)
        h = frame_hz(d)
        total += frame_ms(d, fs)
        out.append("  %2d  %s  %2d  %2d  %d %2d %2d  %d  -> %5d %5d %5d"
                   % (i, ' '.join('%02x' % b for b in f), d['F1'], d['F2'],
                      d['F3'], d['AM'], d['PI'], d['FD'],
                      h['F1'], h['F2'], h['F3']))
    out.append("")
    out.append("%d frames, %.0f ms nominal" % (len(frames), total))
    for c in ctrls:
        k = decode_control(c)
        out.append("control %s -> stop=%s furcsa=%s speed=%.2fx (%.1f ms/frame)"
                   % (' '.join('%02x' % b for b in c), k['stop'], k['furcsa'],
                      k['speed'], k['frame_ms']))
    return '\n'.join(out)
