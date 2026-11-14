# -*- coding: utf-8 -*-
"""The voice in C gives the PCM of the pipeline it replaces.

`reference` is what the NVDA add-on did up to 3.2.2, in Python on Unicorn: clause by
clause, capture, transpose, render, then fades and scaling.  Sessions stay alive
across texts and settings, so any state the engine keeps has to agree too.

Needs what is not in the repository, so it skips without it: the program itself
(BRAILAB_ARCHIVE, else the repository's third_party/brailab), Unicorn, and the built library.
"""
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import brailab_voice                                     # noqa: E402

ARCHIVE = os.environ.get('BRAILAB_ARCHIVE', os.path.join(os.path.dirname(os.path.dirname(HERE)), 'third_party', 'brailab'))
COM = os.path.join(ARCHIVE, 'TALKHUN0.COM')

pytestmark = pytest.mark.skipif(brailab_voice.load_library() is None or not os.path.exists(COM),
                                reason="needs talkhun.dll and TALKHUN0.COM")

ESC = "\x1b"
DELIMS = ".,;:?!"
TEXTS = ["Jó napot kívánok.", "BraiLab PC", "Mennyi az idő? Fél öt.", "szász, cica, fecske, és",
         "1234, 56.", "A", "I", "kérem", "Ez egy mondat; és ez egy másik: vége!", "...", " , ",
         "a,b,c", "Ez – mondta – „idézet”… tovább.", "Egy hosszabb mondat, amely több tagmondatból áll, és elég hosszú ahhoz, hogy "
         "egy blokknál is tovább tartson, mert sok szót kell kimondani benne egymás után.",
         "segítőszoftverek, élő, ÁRVÍZTŰRŐ TÜKÖRFÚRÓGÉP."]
HUNGARIAN = "áéíóöőúüűÁÉÍÓÖŐÚÜŰ"
SETTINGS = [dict(),
            dict(pitch=2.0 ** 0.25, time_scale=0.625, gain=0.7),
            dict(pitch=2.0 ** -0.5, time_scale=0.35, gain=1.25),
            dict(furcsa=True),
            dict(furcsa=True, pitch=1.3, time_scale=0.9),
            dict(intonation=False),
            dict(intonation=False, pitch=0.8, furcsa=True, time_scale=0.5)]


def clauses(text):
    out, start = [], 0
    for i, ch in enumerate(text):
        if ch in DELIMS:
            out.append(text[start:i + 1])
            start = i + 1
    if start < len(text):
        out.append(text[start:])
    return [c for c in out if c.strip()]


def to_pcm(x, gain, fade_in, fade_out):
    if fade_in or fade_out:
        x = x.copy()
        nf = min(40, len(x) // 2)
        if nf > 1:
            w = np.sin(np.linspace(0.0, np.pi / 2.0, nf)) ** 2
            if fade_in:
                x[:nf] *= w
            if fade_out:
                x[-nf:] *= w[::-1]
    return np.clip(x * (20000.0 * gain), -32767, 32767).astype("<i2").tobytes()


def reference(engine, chip_synth, text, pitch=1.0, time_scale=1.0, furcsa=False, intonation=True,
              gain=1.0):
    blocks = []
    for clause in clauses(text):
        c = clause + " " if len(clause) == 1 else clause
        engine.feed(ESC + ("F1" if furcsa else "F0"))
        seq = chip_synth.transpose_seq(engine.capture(c), pitch)
        blocks += list(chip_synth.render_chip_stream(seq, time_scale=time_scale,
                                                     flat_pitch=not intonation))
    return [to_pcm(b, gain, i == 0, i == len(blocks) - 1) for i, b in enumerate(blocks)]


@pytest.fixture(scope="module")
def old():
    """The Python pipeline, forced onto the reference core."""
    talkhun = pytest.importorskip("talkhun")
    saved = os.environ.get("PCF8200_BACKEND")
    os.environ["PCF8200_BACKEND"] = "python"
    import chip_synth
    yield talkhun.load(COM), chip_synth
    if saved is None:
        del os.environ["PCF8200_BACKEND"]
    else:
        os.environ["PCF8200_BACKEND"] = saved


@pytest.fixture(scope="module")
def voice():
    with open(COM, 'rb') as f:
        v = brailab_voice.Voice(f.read())
    yield v
    v.close()


@pytest.mark.parametrize("settings", SETTINGS, ids=str)
def test_the_same_pcm_as_the_python_pipeline(old, voice, settings):
    engine, chip_synth = old
    for text in TEXTS:
        want = reference(engine, chip_synth, text, **settings)
        got = list(voice.stream(text, **settings))
        assert [len(b) for b in got] == [len(b) for b in want], text
        assert got == want, text


def test_the_engine_reads_cwi2():
    """TALKHUN0 is from 1991: o and u double acute sit where CP437 has o and u circumflex."""
    assert brailab_voice.encode("őűŐŰ") == b"\x93\x96\x93\x96"
    assert brailab_voice.encode("áíóúÁÍÓÚ") == b"\xa0\xa1\xa2\xa3" * 2
    assert brailab_voice.encode("éöüÉÖÜ") == b"\x82\x94\x81\x90\x99\x9a"
    assert brailab_voice.encode("–") == b"\x1a"


@pytest.mark.parametrize("letter", HUNGARIAN)
def test_every_hungarian_letter_is_spoken_not_spelled(voice, letter):
    """A byte the engine doesn't know, it spells out as a code ("kód 8b"): four times as long as a vowel.

    Fed CP852, that is what o and u double acute and five capitals did, from 3.0 to 4.0.0."""
    plain = len(b"".join(voice.stream("aa.")))
    got = len(b"".join(voice.stream("a" + letter + "a.")))
    assert got < 2.5 * plain, (letter, got, plain)


def test_an_utterance_can_be_dropped_halfway(voice):
    first = list(voice.stream("Jó napot kívánok."))
    voice.begin("Egy hosszabb mondat, amely több tagmondatból áll, és elég hosszú.")
    assert voice.read()
    assert list(voice.stream("Jó napot kívánok.")) == first


def test_nothing_to_say(voice):
    assert list(voice.stream("")) == []
    assert list(voice.stream("  \n ")) == []


def test_a_setting_out_of_range_is_refused(voice):
    with pytest.raises(ValueError):
        voice.begin("a", time_scale=3.0)
    with pytest.raises(ValueError):
        voice.begin("a", pitch=0.0)


def test_a_wrong_program_is_refused():
    with pytest.raises(RuntimeError):
        brailab_voice.Voice(b"\xc3")
