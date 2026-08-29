# -*- coding: utf-8 -*-
"""Starter formant tables (male vocal tract, Hz) -- extend freely.

Each entry is [F1, F2, F3] in Hz; Voice pads F4/F5.  These are typical adult-male
values; nudge them to taste, or measure your own from recordings (Praat, LPC).
The point of the library is that YOU supply the phonetics -- these are just a
usable starting point so a language is a dict, not a research project.
"""

# language-agnostic cardinal-ish vowels
VOWELS = {
    "a": [700, 1220, 2600],
    "e": [530, 1840, 2480],
    "i": [270, 2290, 3010],
    "o": [570, 840, 2410],
    "u": [300, 870, 2240],
}

# Polish vowels (6 oral + 2 nasal, approximated as their oral base for now).
# a e i o u  y[ɨ]  ą[ɔ̃≈o]  ę[ɛ̃≈e]  -- refine against native recordings.
POLISH = {
    "a": [700, 1090, 2600],
    "e": [500, 1750, 2500],
    "i": [280, 2100, 2900],
    "o": [500, 900, 2500],
    "u": [320, 700, 2450],
    "y": [350, 1600, 2500],     # close central [ɨ]
    "ą": [520, 900, 2500],      # nasal o (base)
    "ę": [500, 1650, 2500],     # nasal e (base)
}

# a couple of unvoiced consonants as (formants, bandwidths) for Voice.fricative
FRICATIVES = {
    "s": dict(formants=(4500, 5500, 6500), bw=(600, 600, 600)),
    "sz": dict(formants=(2500, 3500, 4500), bw=(700, 700, 700)),   # Polish sz [ʃ]
    "f": dict(formants=(1200, 4000, 6000), bw=(1000, 1000, 1000)),
}
