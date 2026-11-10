# -*- coding: utf-8 -*-
"""A symbol must not be spoken twice: once by NVDA, once more by TTS.dll.

NVDA replaces "-" with its name at symbol level "most" and above, and keeps the
character too (preserve: always).  TTS.dll names symbols itself, so the driver
takes out the ones NVDA preserves and TTS.dll would say.

Measured with the real TTS.dll: "alma körte" is 0.77 s of speech, "alma - körte"
1.22 s, "alma mínusz körte" 1.28 s.  "ETI minusz-Eloquence", which is what NVDA
sent, was 2.14 s against 1.63 s for "ETI-Eloquence".
"""
import pytest

from test_pitch_path import driverModule  # noqa: F401  (a fixture)


@pytest.mark.parametrize("text, expected", [
    # what NVDA sends for "ETI-Eloquence" at symbol level "most", Hungarian
    ("ETI minusz-Eloquence", "ETI minusz Eloquence"),
    # and below that level, where NVDA means the dash to be silent
    ("ETI-Eloquence", "ETI Eloquence"),
    ("alma – körte", "alma körte"),
    ("alma — körte", "alma körte"),
    ("alma (körte) dió", "alma körte dió"),
    ("«alma»", "alma"),
    ("és így tovább…", "és így tovább."),
    ("és így tovább...", "és így tovább."),
    # intonation punctuation stays
    ("Szia, világ! Jól vagyok; köszönöm: szép nap.", "Szia, világ! Jól vagyok; köszönöm: szép nap."),
    ("-", ""),
])
def test_the_driver_removes_what_tts_dll_would_say_again(driverModule, text, expected):
    assert driverModule[0]._brailabSafeText(text) == expected
