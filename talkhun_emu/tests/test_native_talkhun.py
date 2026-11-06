# -*- coding: utf-8 -*-
"""TALKHUN0 on MAME's 8086 sends the adapter the same bytes as on Unicorn.

Needs what is not in the repository, so it skips without it: the program itself
(BRAILAB_ARCHIVE or ../BRAILAB-archive), Unicorn, and the built library.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import talkhun_native as native                          # noqa: E402

ARCHIVE = os.environ.get('BRAILAB_ARCHIVE', os.path.join(os.path.dirname(HERE), 'BRAILAB-archive'))
COM = os.path.join(ARCHIVE, 'TALKHUN0.COM')

pytestmark = pytest.mark.skipif(native.load_library() is None or not os.path.exists(COM),
                                reason="needs talkhun.dll and TALKHUN0.COM")

TEXTS = ["Jó napot kívánok.", "BraiLab PC.", "Mennyi az idő? Fél öt.", "szász, cica, fecske, és",
         "1234, 56.", "A", "kérem", "Ez egy mondat; és ez egy másik: vége!"]


def _norm(seq):
    return [(k, v if isinstance(v, int) else bytes(v)) for k, v in seq]


def test_the_same_bytes_as_on_unicorn():
    talkhun = pytest.importorskip("talkhun")
    a = talkhun.load(COM)
    with open(COM, 'rb') as f:
        b = native.Talkhun(f.read())
    try:
        for esc in ("", "\x1bF1", "\x1bS4", "\x1bP=", "\x1bS1\x1bF0"):
            a.feed(esc)
            b.feed(esc)
            for text in TEXTS:
                x = _norm(a.capture(text))
                assert x and x == _norm(b.capture(text)), text
    finally:
        b.close()


def test_a_wrong_program_is_refused():
    with pytest.raises(RuntimeError):
        native.Talkhun(b"\xc3")
