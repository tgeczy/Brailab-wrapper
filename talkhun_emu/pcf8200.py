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

The tables below are the PUBLIC fallback: MAME's open-source MEA-8000 values
(F1/F2/F3/BW) plus our own ear-tuned reconstructions (in synth.py).  If an
external directory of measured quantization tables is available on the machine
(see load_real_tables), the emulator reads those instead and this fallback is
bypassed; no such tables are stored in this repository.
"""

import csv
import os

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


# --------------------------------------------------------------------------
# The chip's real quantization tables.
#
# The chip decodes each frame's 5-bit/3-bit/2-bit codes into control
# parameters through an internal ROM.  Those values are bundled in
# pcf8200_tables.py and are the emulator's default; render() with real=False
# still selects the public MAME + reconstructed tables above for comparison.
# For experimentation the real tables can be overridden by an external
# directory of CSVs -- set PCF8200_TABLES to that directory (columns as in
# male_/female_formant_codes.csv, amplitudes.csv, pitch_increments.csv).
# --------------------------------------------------------------------------


def _read_formant_csv(path):
    """Read male/female_formant_codes.csv into per-column code ladders.

    Each column runs only as far as its field is wide (F1/F2 to code 31, F3/F4
    and B1/B2 to code 7, B3/B4/B5 to code 3, F5 to code 1); the CSV leaves the
    rest of each column blank, so a blank cell just ends that ladder.
    """
    cols = {}
    with open(path, newline='') as fh:
        reader = csv.DictReader(fh)
        names = [n for n in reader.fieldnames if n != 'code']
        for n in names:
            cols[n] = []
        for row in reader:
            for n in names:
                v = row[n].strip()
                if v != '':
                    cols[n].append(int(round(float(v))))
    return cols


def _read_indexed_csv(path, value_col):
    """Read a code,value CSV into a list ordered by code."""
    pairs = []
    with open(path, newline='') as fh:
        for row in csv.DictReader(fh):
            pairs.append((int(row['code']), float(row[value_col])))
    pairs.sort()
    return [v for _, v in pairs]


def _qc(b):
    """Structural QC on a table bundle -- field widths, monotonic F1/F2 and
    amplitude ladders, antisymmetric pitch increments.  Raises on a malformed
    set rather than letting the emulator mis-speak.  Checks shape only, never
    a specific frequency, so it holds for the bundled and the external tables
    alike.
    """
    assert [len(x) for x in b['male_F']] == [32, 32, 8, 8, 2], 'male F widths'
    assert [len(x) for x in b['male_B']] == [8, 8, 4, 4, 4], 'male B widths'
    assert [len(x) for x in b['female_F']] == [32, 32, 8, 8], 'female F widths'
    assert [len(x) for x in b['female_B']] == [8, 8, 4, 4], 'female B widths'
    for tab in (b['male_F'][0], b['male_F'][1],
                b['female_F'][0], b['female_F'][1]):
        assert all(tab[i] < tab[i + 1] for i in range(len(tab) - 1)), \
            'F1/F2 ladders must increase'
    a = b['ampl']
    assert len(a) == 16 and a[0] == 0 and \
        all(a[i] <= a[i + 1] for i in range(15)), 'amplitude ladder'
    p = b['pi']
    assert len(p) == 32 and p[0] == 0.0 and p[16] == 0.0, \
        'pitch increment ladder (code 16 = unvoiced)'
    for i in range(1, 16):          # codes 17..31 are the negatives of 15..1
        assert abs(p[16 + i] + p[16 - i]) < 1e-6, 'pitch antisymmetry'
    return b


def load_real_tables(path=None):
    """Load the chip's real quantization tables from an external CSV directory,
    or None if PCF8200_TABLES is unset / "none" / missing.

    Returns a validated dict of per-formant frequency and bandwidth ladders
    (male and female), the amplitude fractions, the pitch-increment ladder,
    and the start-pitch scale.  This is the override path; the default tables
    are bundled (see _inlined_tables).
    """
    if path is None:
        path = os.environ.get('PCF8200_TABLES')
    if not path or str(path).strip().lower() == 'none' or not os.path.isdir(path):
        return None
    try:
        male = _read_formant_csv(os.path.join(path, 'male_formant_codes.csv'))
        fem = _read_formant_csv(os.path.join(path, 'female_formant_codes.csv'))
        ampl = [int(round(v)) for v in
                _read_indexed_csv(os.path.join(path, 'amplitudes.csv'),
                                  'amplitude')]
        pit = _read_indexed_csv(
            os.path.join(path, 'pitch_increments.csv'),
            'pitch_increment_Hz_per_std_frame')
    except (OSError, ValueError, KeyError):
        return None

    amax = float(ampl[-1]) or 1.0
    return _qc({
        'male_F': [male['F1_Hz'], male['F2_Hz'], male['F3_Hz'],
                   male['F4_Hz'], male['F5_Hz']],
        'male_B': [male['B1_Hz'], male['B2_Hz'], male['B3_Hz'],
                   male['B4_Hz'], male['B5_Hz']],
        'female_F': [fem['F1_Hz'], fem['F2_Hz'], fem['F3_Hz'], fem['F4_Hz']],
        'female_B': [fem['B1_Hz'], fem['B2_Hz'], fem['B3_Hz'], fem['B4_Hz']],
        'ampl': [a / amax for a in ampl],
        'pi': pit,
        # Start-pitch byte = Hz * 0.4096, so Hz = byte * 10000/4096.
        'pitch_hz_per_unit': 10000.0 / 4096.0,
    })


def _inlined_tables():
    """The chip tables bundled in pcf8200_tables.py -- the default real set."""
    try:
        import pcf8200_tables as T
    except ImportError:
        return None
    return _qc({
        'male_F': [list(x) for x in T.MALE_F],
        'male_B': [list(x) for x in T.MALE_B],
        'female_F': [list(x) for x in T.FEMALE_F],
        'female_B': [list(x) for x in T.FEMALE_B],
        'ampl': list(T.AMPL),
        'pi': list(T.PI),
        'pitch_hz_per_unit': T.PITCH_HZ_PER_UNIT,
    })


#: Resolved once at import.  The bundled tables are the default; an external
#: PCF8200_TABLES directory overrides them.  REAL is the active table bundle,
#: REAL_TABLES the convenience boolean (True whenever any real set is present).
REAL = load_real_tables() or _inlined_tables()
REAL_TABLES = REAL is not None


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
