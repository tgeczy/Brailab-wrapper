# -*- coding: utf-8 -*-
"""#37: text reaches TALKHUN0 the same way on every path.

talkhun.py and talkhun_native.py each had their own copy of the CWI-2 encoding ('replace', so '?' for a character
CWI-2 has not got).  The audit took the C voice to send 1Ah instead; it does not: brailab_voice.c turns 1Ah into
'?' too, so the paths agreed, and the test of the C voice against the Python pipeline holds them together.  Now
there is one Python function for it, brailab_voice.engine_bytes.  Whether an unknown character should end its
phrase with a question's melody at all is #8's question, for the ear.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import brailab_voice                                    # noqa: E402

ARCHIVE = os.environ.get("BRAILAB_ARCHIVE",
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "third_party", "brailab"))
COM = os.path.join(ARCHIVE, "TALKHUN0.COM")
TEXT = "Kovács – Nagy Péter, „idézet”… ő és ű."


def test_one_encoding_for_the_engine():
    assert brailab_voice.engine_bytes(TEXT) == brailab_voice.encode(TEXT).replace(b"\x1a", b"?")
    assert b"\x1a" not in brailab_voice.engine_bytes(TEXT)
    assert brailab_voice.engine_bytes("őű") == b"\x93\x96"


@pytest.mark.skipif(not os.path.exists(COM), reason="needs TALKHUN0.COM")
def test_both_capture_paths_take_it_the_same_way():
    import talkhun_native
    with open(COM, "rb") as f:
        t = talkhun_native.Talkhun(f.read())
    assert t.capture(TEXT) == t.capture(brailab_voice.engine_bytes(TEXT))
    pytest.importorskip("unicorn")
    import talkhun
    u = talkhun.load()
    assert u.capture(TEXT) == u.capture(brailab_voice.engine_bytes(TEXT))
