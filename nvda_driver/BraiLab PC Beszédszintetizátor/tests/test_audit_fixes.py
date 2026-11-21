# -*- coding: utf-8 -*-
"""The TTS.dll driver's fixes from the 2026-11-21 audit (issues #2 to #7, #10, #17), with NVDA and the wrapper
stubbed (the real-engine checks are in test_audit_real.py)."""
import importlib.util
import os
import queue
import sys
import threading
import time

import pytest

from test_pitch_path import driverModule, driver, ADDON, DRIVERS  # noqa: F401  (fixtures)

NUMBER_ROWS = "\n".join(" ".join(["06301234567", "06701234567", "06201234567"]) for _ in range(10))
PROSE = ("Ez egy hosszabb magyar mondat, amelyet a felhasználó végighallgat, és amelyben sok szó van egymás után, "
         "hogy a teljes szöveg jóval tovább tartson, mint egy rövid üzenet; a végén pedig még egy kicsit folytatódik "
         "a szöveg, mert négyszázötven karakterig szeretnénk eljutni egyetlen darabban, vessző nélkül is akár "
         "szóról szóra haladva egészen addig amíg a határt el nem érjük")


def test_a_run_of_commas_reaches_the_engine_as_one(driverModule):
    """#3: 429 commas in a row leave TTS.dll mute for good; #2: 323 give no audio."""
    brailab, _ = driverModule
    assert brailab._brailabSafeText("," * 450 + "Szia.") == ",Szia."
    assert brailab._brailabSafeText("a, , , , , b") == "a, b"
    assert brailab._brailabSafeText(":" * 200 + " alma") == ": alma"
    assert brailab._brailabSafeText("Egy, kettő; három: négy!") == "Egy, kettő; három: négy!"


def test_number_rows_go_to_the_engine_in_short_pieces(driverModule):
    """#2: TTS.dll gives no audio for about 300 characters of phone numbers."""
    brailab, _ = driverModule
    text = brailab._brailabSafeText(NUMBER_ROWS)
    pieces = brailab._splitForEngine(text)
    assert all(len(p) <= brailab.DIGIT_DENSE_LENGTH for p in pieces), [len(p) for p in pieces]
    assert " ".join(pieces).split() == text.split(), "a number was cut or lost"


def test_prose_is_split_as_before(driverModule):
    brailab, _ = driverModule
    assert brailab._splitForEngine(PROSE) == [PROSE]
    long = (PROSE + " ") * 3
    assert all(len(p) <= brailab.MAX_STRING_LENGTH for p in brailab._splitForEngine(long))


def test_a_job_queued_before_a_cancel_is_refused(driver):
    """#4: the worker must not take up an utterance that was cancelled while queued."""
    d, brailab, fake = driver
    seq = fake.sequence()
    blocks, _, _ = d._buildBlocks(["Ez nem hangozhat el.", brailab.IndexCommand(1)], coalesceSayAll=True)
    fake.stop()                                   # the cancel that came first
    fake.calls[:] = []
    d._speakBgComposite(blocks, seq)
    assert not any(c[0] in ("add_text", "commit_utterance") for c in fake.calls), fake.calls
    assert d.speaking is False


def test_a_break_is_said_as_silence_between_two_parts(driver):
    """#17: NVDA's BreakCommand before a delayed character description."""
    d, brailab, fake = driver
    Break = sys.modules["speech.commands"].BreakCommand
    blocks, _, _ = d._buildBlocks(["A", Break(500), "Ábel", brailab.IndexCommand(1)], coalesceSayAll=True)
    fake.calls[:] = []
    d._speakBgComposite(blocks, fake.sequence())
    kinds = [c[0] for c in fake.calls if c[0] in ("add_text", "commit_part", "push_silence", "begin_utterance",
                                                  "add_index", "commit_utterance")]
    assert kinds == ["begin_utterance", "add_text", "commit_part", "push_silence", "begin_utterance", "add_text",
                     "add_index", "commit_utterance"], fake.calls
    assert ("push_silence", 500) in fake.calls


def _real_brailab():
    """the real _brailab module, loaded on its own (the driver's tests have a fake in its place)"""
    spec = importlib.util.spec_from_file_location("_brailab_real", os.path.join(DRIVERS, "_brailab.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_wants_the_engine_data_files(tmp_path):
    """#6: without BINADATA.BIN and BINAHANK.BIN TTS.dll loads and is silent."""
    mod = _real_brailab()
    (tmp_path / "Brailab").mkdir()
    (tmp_path / "brailab_wrapper.dll").write_bytes(b"x")
    (tmp_path / "Brailab" / "TTS.dll").write_bytes(b"x")
    assert mod.check(str(tmp_path)) is False
    (tmp_path / "Brailab" / "BINADATA.BIN").write_bytes(b"x")
    assert mod.check(str(tmp_path)) is False
    (tmp_path / "Brailab" / "BINAHANK.BIN").write_bytes(b"x")
    assert mod.check(str(tmp_path)) is True


class _Player(object):
    def __init__(self, *a, **k):
        self.fed = []
        self.stops = 0

    def feed(self, data, onDone=None, **k):
        self.fed.append(bytes(data))
        if onDone:
            onDone()

    def idle(self):
        pass

    def stop(self):
        self.stops += 1

    def close(self):
        pass


def test_a_new_audio_worker_does_not_end_on_an_old_stop_sentinel(monkeypatch):
    """#7: a busy worker left its None behind; the next worker read it and quit."""
    mod = _real_brailab()
    monkeypatch.setitem(sys.modules, "nvwave", type(sys)("nvwave"))
    sys.modules["nvwave"].WavePlayer = _Player
    c = mod.BrailabDirectClient()
    c._audio_queue.put(None)                       # what a worker that left busy did not take
    c.initialize_audio(1, 10000, 16)
    time.sleep(0.3)
    assert c._audio_worker.is_alive()
    c._audio_worker.stop()


def test_a_chunk_fed_across_a_stop_is_stopped_again():
    """#10: a stop() that lands while a chunk goes down must not let it play on."""
    mod = _real_brailab()
    seqs = [0]
    player = _Player()
    real_feed = player.feed

    def feed(data, onDone=None, **k):
        real_feed(data, onDone)
        if data:
            seqs[0] += 1                           # the stop came while this chunk went down
    player.feed = feed
    q = queue.Queue()
    w = mod.AudioWorker(player, q, lambda: seqs[0])
    w.start()
    q.put((b"\x01\x00" * 100, None, False, 0))
    q.join()
    w.stop()
    assert player.stops == 1
