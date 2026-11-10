# -*- coding: utf-8 -*-
"""Text longer than TTS.dll's 512-character limit is cut where a pause belongs.

The driver used to cut every 450 characters wherever that fell, often inside a
word: a long post was read with a word broken in two and the melody restarting
mid-sentence.
"""
import pytest

from test_pitch_path import driverModule  # noqa: F401  (a fixture)

SENTENCE = "Ez egy közepesen hosszú magyar mondat, amelyben van egy vessző is. "


def _words(pieces):
    return " ".join(pieces).split()


def test_short_text_is_one_piece(driverModule):
    assert driverModule[0]._splitForEngine("Szia, világ.") == ["Szia, világ."]


def test_long_text_is_cut_at_sentence_ends(driverModule):
    brailab = driverModule[0]
    text = (SENTENCE * 30).strip()
    pieces = brailab._splitForEngine(text)
    assert len(pieces) > 1
    assert all(len(p) <= brailab.MAX_STRING_LENGTH for p in pieces)
    assert all(p.endswith(".") for p in pieces), "a piece ended in the middle of a sentence"
    assert _words(pieces) == text.split(), "words were lost, added or broken"


def test_one_endless_sentence_is_cut_after_a_comma(driverModule):
    brailab = driverModule[0]
    text = ("alma, körte, szilva, barack, " * 60).strip().rstrip(",") + "."
    pieces = brailab._splitForEngine(text)
    assert all(len(p) <= brailab.MAX_STRING_LENGTH for p in pieces)
    assert all(p.endswith(",") for p in pieces[:-1])
    assert _words(pieces) == text.split()


def test_without_any_punctuation_it_is_cut_between_words(driverModule):
    brailab = driverModule[0]
    text = " ".join("szó%d" % i for i in range(400))
    pieces = brailab._splitForEngine(text)
    assert all(len(p) <= brailab.MAX_STRING_LENGTH for p in pieces)
    assert _words(pieces) == text.split()


def test_only_a_word_longer_than_the_limit_is_cut_inside(driverModule):
    brailab = driverModule[0]
    text = "a" * 1000
    pieces = brailab._splitForEngine(text)
    assert [len(p) for p in pieces] == [450, 450, 100]
    assert "".join(pieces) == text


@pytest.mark.parametrize("n", [449, 450, 451, 512, 900, 2000])
def test_no_piece_ever_exceeds_the_limit(driverModule, n):
    brailab = driverModule[0]
    text = (SENTENCE * 40)[:n]
    assert all(0 < len(p) <= brailab.MAX_STRING_LENGTH for p in brailab._splitForEngine(text))
