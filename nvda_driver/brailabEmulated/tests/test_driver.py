# -*- coding: utf-8 -*-
"""The emulated BraiLab driver, loaded the way NVDA loads it, on a player that keeps
real time.  See conftest.py for what the fakes promise."""
import os
import subprocess
import sys
import time

import pytest

import conftest
import nvwave
import synthDriverHandler as sdh
from speech.commands import IndexCommand, PitchCommand

pytestmark = pytest.mark.skipif(not conftest.STAGED,
                                reason="needs TALKHUN0.COM and the built talkhun.dll")

done = sdh.synthDoneSpeaking
reached = sdh.synthIndexReached


@pytest.fixture
def driver():
    from synthDrivers import brailabEmulated
    done.reset()
    reached.reset()
    d = brailabEmulated.SynthDriver()
    yield d
    d.terminate()


def say(d, *sequence):
    """Speak, and wait until NVDA would hear it has finished."""
    done.reset()
    reached.reset()
    d.speak(list(sequence))
    assert done.wait(), "synthDoneSpeaking never came"
    d._bgQueue.join()
    return bytes(d._player.pcm)


def voice_pcm(text, **settings):
    from synthDrivers._brailab_native import brailab_voice
    with open(os.path.join(conftest.STAGE, "archive", "TALKHUN0.COM"), "rb") as f:
        v = brailab_voice.Voice(f.read())
    try:
        return b"".join(v.stream(text, **settings))
    finally:
        v.close()


def test_it_loads_without_numpy_or_unicorn():
    code = ("import sys; sys.path.insert(0, %r); import conftest; "
            "from synthDrivers import brailabEmulated; "
            "assert brailabEmulated.SynthDriver.check(); "
            "print(sorted(m for m in ('numpy', 'unicorn', 'scipy') if m in sys.modules))"
            % os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True).stdout
    assert out.strip().splitlines()[-1] == "[]"


def test_the_player_gets_the_voice_at_10_khz(driver):
    assert driver._player.args == (1, 10000, 16)
    pcm = say(driver, "Jó napot kívánok.")
    assert pcm == voice_pcm("Jó napot kívánok.", time_scale=0.625,
                            gain=0.25 + 0.9)


def test_settings_are_properties_and_reach_the_voice(driver):
    driver.rate, driver.pitch, driver.volume = 80, 70, 40
    driver.furcsa, driver.useIntonation = True, False
    assert (driver.rate, driver.pitch, driver.volume) == (80, 70, 40)
    assert driver.furcsa is True and driver.useIntonation is False
    pcm = say(driver, "Jó napot.")
    assert pcm == voice_pcm("Jó napot.", pitch=2.0 ** 0.2, time_scale=0.9 - 0.55 * 0.8,
                            furcsa=True, intonation=False, gain=0.25 + 0.4)


def test_indexes_fire_in_order_once_their_audio_has_played(driver):
    t0 = time.perf_counter()
    say(driver, "Egy.", IndexCommand(1), "Kettő, három.", IndexCommand(2))
    got = [(t, k["index"]) for t, k in reached.calls]
    assert [i for _, i in got] == [1, 2]
    first = len(voice_pcm("Egy.", time_scale=0.625, gain=1.15)) / 2.0 / 10000
    assert got[0][0] - t0 >= first, "index 1 came before its audio had played"
    assert done.calls[0][0] >= got[1][0], "done before the last index"
    assert len(done.calls) == 1


def test_a_sequence_with_no_text_still_reports(driver):
    say(driver, IndexCommand(5))
    assert [k["index"] for _, k in reached.calls] == [5]
    assert driver._player.pcm == b""


def test_a_capital_is_higher_and_no_longer(driver):
    plain = say(driver, "B")
    driver._player.pcm.clear()
    high = say(driver, PitchCommand(30), "B", PitchCommand(0))
    assert len(high) == len(plain) and high != plain
    assert high == voice_pcm("B", pitch=2.0 ** 0.3, time_scale=0.625, gain=1.15)


def test_cancel_drops_the_rest_and_its_reports(driver):
    long = "Egy nagyon hosszú mondat, sok szóval, ami sokáig tart, és közben megszakítjuk."
    done.reset()
    reached.reset()
    driver.speak([long, IndexCommand(1), long, IndexCommand(2)])
    deadline = time.time() + 5
    while not driver._player.pcm and time.time() < deadline:
        time.sleep(0.005)
    assert driver._player.pcm, "nothing was played"
    driver.cancel()
    driver._bgQueue.join()
    time.sleep(0.3)
    assert reached.calls == [] and done.calls == [], "a cancelled utterance reported"
    driver._player.pcm.clear()
    pcm = say(driver, "Jó napot kívánok.")
    assert pcm == voice_pcm("Jó napot kívánok.", time_scale=0.625, gain=1.15)


def test_the_first_audio_is_quick(driver):
    say(driver, "Bemelegítés.")
    driver._player.pcm.clear()
    t0 = time.perf_counter()
    driver.speak(["Egy nagyon hosszú mondat, sok szóval, ami sokáig tart, és sok tagmondatból "
                  "áll, hogy a teljes szöveg jóval tovább tartson egy blokknál."])
    while not driver._player.pcm:
        time.sleep(0.001)
    assert time.perf_counter() - t0 < 0.1
    driver.cancel()


def test_terminate_stops_the_thread_and_closes_the_player(driver):
    player = driver._player
    driver.terminate()
    assert player.closed and not driver._bgThread.is_alive()
