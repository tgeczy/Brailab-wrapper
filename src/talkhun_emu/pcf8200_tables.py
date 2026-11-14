# -*- coding: utf-8 -*-
"""PCF-8200 on-chip quantization tables.

The PCF-8200 is a formant speech synthesizer: each 40-bit speech frame carries
short codes (5, 3, 2 or 1 bits per parameter), and the chip's internal ROM
expands them into control values -- formant centre frequencies and bandwidths
in Hz, an amplitude, and a pitch increment.  These lists ARE that expansion,
one entry per code: they state how the silicon behaves, and the emulator reads
them to reproduce the chip.

Structure (all frequencies in Hz):
  MALE_F / FEMALE_F   formant centre frequencies, one list per formant.  Male
                      speech uses five formants, female four (F5 unused).  F1
                      and F2 are 32-step ladders, F3/F4 8-step, F5 a single bit.
  MALE_B / FEMALE_B   the matching bandwidth ladders.  Code 0 = 3000 Hz, i.e.
                      maximally damped -- effectively "formant off".
  AMPL                the 4-bit amplitude code as a fraction of full scale.
  PI                  the 5-bit pitch increment, Hz per standard frame; code
                      16 = 0 is the unvoiced flag (noise source), and codes
                      17..31 are the negatives of 15..1.

The frame bit-layout and byte protocol are in the public PCF-8200 datasheet;
these code-expansion tables are stated here as factual chip behaviour.
"""

MALE_F = [
    # F1
    [100, 109, 119, 130, 141, 154, 168, 183, 199, 217, 237, 258, 282, 307,
     335, 365, 398, 433, 472, 515, 561, 612, 667, 727, 793, 864, 942, 1027,
     1119, 1220, 1330, 1450],
    # F2
    [500, 526, 554, 583, 614, 646, 680, 716, 754, 793, 835, 879, 925, 974,
     1025, 1079, 1136, 1195, 1258, 1324, 1394, 1467, 1545, 1626, 1711, 1801,
     1896, 1996, 2101, 2211, 2328, 2450],
    # F3
    [1500, 1690, 1903, 2143, 2414, 2719, 3063, 3450],
    # F4
    [2550, 2766, 2999, 3253, 3528, 3826, 4149, 4500],
    # F5
    [3900, 4600],
]

MALE_B = [
    # B1
    [3000, 600, 303, 153, 77, 39, 20, 10],
    # B2
    [3000, 800, 433, 234, 126, 68, 37, 20],
    # B3
    [3000, 600, 190, 60],
    # B4
    [3000, 700, 265, 100],
    # B5
    [3000, 800, 335, 140],
]

FEMALE_F = [
    # F1
    [100, 110, 121, 134, 147, 162, 179, 197, 217, 239, 263, 290, 319, 351,
     387, 426, 469, 517, 569, 627, 691, 761, 838, 923, 1017, 1120, 1234, 1359,
     1497, 1649, 1816, 2000],
    # F2
    [500, 529, 561, 594, 629, 666, 705, 747, 791, 837, 886, 939, 994, 1053,
     1115, 1180, 1250, 1323, 1401, 1484, 1571, 1664, 1762, 1866, 1976, 2092,
     2216, 2346, 2484, 2631, 2786, 2950],
    # F3
    [2050, 2251, 2473, 2715, 2982, 3275, 3597, 3950],
    # F4
    [3500, 3662, 3831, 4007, 4192, 4386, 4588, 4800],
]

FEMALE_B = [
    # B1
    [3000, 700, 414, 245, 145, 86, 51, 30],
    # B2
    [3000, 1000, 626, 391, 245, 153, 96, 60],
    # B3
    [3000, 700, 265, 100],
    # B4
    [3000, 800, 322, 130],
]

# Amplitude (AM, 4-bit) as a fraction of full scale; ~3 dB (x sqrt 2) per step
# above code 4.
AMPL = [
    0.0, 0.0078125, 0.01171875, 0.015625, 0.021484375, 0.03125, 0.044921875,
    0.0625, 0.087890625, 0.125, 0.17578125, 0.25, 0.353515625, 0.5,
    0.70703125, 1.0,
]

# Pitch increment (PT, 5-bit), Hz per standard frame.  Code 16 = 0 = unvoiced
# flag (selects the noise source); 17..31 negate 15..1.
PI = [
    0.0, 1.2, 2.4, 3.7, 4.9, 6.1, 7.3, 8.5, 9.8, 11.0, 13.4, 15.9, 19.5, 25.6,
    34.2, 45.2, 0.0, -45.2, -34.2, -25.6, -19.5, -15.9, -13.4, -11.0, -9.8,
    -8.5, -7.3, -6.1, -4.9, -3.7, -2.4, -1.2,
]

# Start-pitch byte scale: byte = Hz * 0.4096, so Hz = byte * 10000/4096.
PITCH_HZ_PER_UNIT = 10000.0 / 4096.0
