# -*- coding: utf-8 -*-
"""BraiLabPC (braipc.py): the tempo is heard (#34), and a typed key reaches the program as the console gave it (#35).

The key tests need nothing; the tempo and pitch tests need Unicorn and TALKHUN.COM (third_party/brailab, or BRAILAB_ARCHIVE); it skips without them.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import dos_keys                                         # noqa: E402

ARCHIVE = os.environ.get("BRAILAB_ARCHIVE",
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "third_party", "brailab"))


def test_an_accented_key_reaches_the_program_as_its_own_byte():
    """#35: getch() gives the console's OEM byte; it was decoded as CP852 and cut to the code point's low byte,
    so a-acute (A0h) arrived as E1h and o-double-acute (8Bh) as the letter Q."""
    for byte in (0xA0, 0x82, 0xA1, 0xA2, 0x94, 0x8B, 0xA3, 0x81, 0xFB, 0xB5, 0x90):
        assert dos_keys.key_ax(byte) == byte, hex(byte)          # AL the byte, AH 0: no fixed key


def test_a_plain_key_has_its_scan_code():
    assert dos_keys.key_ax(ord("a")) == 0x1E61
    assert dos_keys.key_ax(ord("A")) == 0x1E41
    assert dos_keys.key_ax(ord("1")) == 0x0231
    assert dos_keys.key_ax(ord("!")) == 0x0221
    assert dos_keys.key_ax(ord("z")) == 0x2C7A
    assert dos_keys.key_ax(ord("/")) == 0x352F
    assert dos_keys.key_ax(0x0D) == 0x1C0D                       # Enter, as before
    assert dos_keys.key_ax(0x1B) == 0x011B


@pytest.mark.skipif(not os.path.exists(os.path.join(ARCHIVE, "TALKHUN.COM")), reason="needs TALKHUN.COM")
def test_each_tempo_is_heard():
    """#34: ESC S1 to S4 changed the control byte, but every one rendered and paced at 12.8 ms a frame."""
    pytest.importorskip("unicorn")
    import braipc
    import brailab_device
    lengths, frame_ms = {}, {}
    for name, code in braipc.TEMPOS:
        host, dev = brailab_device.boot(os.path.dirname(os.path.abspath(__file__)), archive_dir=ARCHIVE,
                                        config=[brailab_device.ESC_DEFAULTS, brailab_device.ESC_BIOS10_ON,
                                                b"\x1bS" + code.encode()])
        host.say("Jó napot kívánok.", seconds=8.0)
        assert any(k == "frame" for k, _ in dev.seq), name
        frame_ms[name] = dev.frame_ms
        lengths[name] = len(braipc._chiprender(dev.seq, False, 1.0, dev.frame_ms))
    assert frame_ms == {name: braipc.TEMPO_MS[code] for name, code in braipc.TEMPOS}, frame_ms
    # slower frames, longer speech
    order = sorted(frame_ms, key=frame_ms.get)
    assert [lengths[n] for n in order] == sorted(lengths.values()), (frame_ms, lengths)


@pytest.mark.skipif(not os.path.exists(os.path.join(ARCHIVE, "TALKHUN.COM")), reason="needs TALKHUN.COM")
def test_each_pitch_reaches_the_adapter():
    """The adapter took "busy" for the first poll only, which TALKHUN v4 spends on a STOP check: no start
    sequence ever went out, so the pitch menu (ESC P) and furcsa changed nothing the adapter received."""
    pytest.importorskip("unicorn")
    import braipc
    import brailab_device
    pitches = {}
    for name, code in braipc.PITCHES:
        host, dev = brailab_device.boot(os.path.dirname(os.path.abspath(__file__)), archive_dir=ARCHIVE,
                                        config=[brailab_device.ESC_DEFAULTS, brailab_device.ESC_BIOS10_ON,
                                                b"\x1bP" + code.encode()])
        host.say("Jó napot kívánok.", seconds=8.0)
        pitches[name] = [v for k, v in dev.seq if k == "pitch"]
        assert pitches[name], "a start sequence with its pitch byte"
        host.say("Viszontlátásra.", seconds=8.0)
        assert len([1 for k, _ in dev.seq if k == "pitch"]) >= 2, "a second utterance starts again"
    assert pitches["mély"][0] < pitches["normál"][0] < pitches["magas"][0], pitches
