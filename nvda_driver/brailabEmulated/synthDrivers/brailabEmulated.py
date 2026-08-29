# -*- coding: utf-8 -*-
# synthDrivers/brailabEmulated.py
#
# Emulated BraiLab PC for NVDA: the 1991 TALKHUN engine under Unicorn feeding a
# software model of the Philips PCF8200 (chip_synth), all IN-PROCESS inside NVDA
# -- no hardware, no vendor DLL, no subprocess.  Same driver shell as the real
# TTS.dll "brailab" synth (settings, Say-All coalescing, chunking, index
# markers, nvwave), and it can do FURCSA hang, the weird voice the DLL lost.
#
# The engine + its deps (numpy/scipy/unicorn) ride in _brailab_engine/lib and go
# on sys.path here, the way PC-TALKER ships Unicorn.  TALKHUN0.COM is Arato's
# work and lives only in the release package's archive/, found via BRAILAB_ARCHIVE.

import os
import sys
import queue
import threading

import nvwave

from logHandler import log
from synthDriverHandler import SynthDriver, synthDoneSpeaking, synthIndexReached
from speech.commands import IndexCommand
from autoSettingsUtils.driverSetting import BooleanDriverSetting

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.join(_HERE, "_brailab_engine")
_LIB = os.path.join(_ENGINE, "lib")
for _p in (_ENGINE, _LIB):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
# Release: TALKHUN0.COM sits in <addon>/archive.  Dev: fall back to the checkout.
_ARCHIVE = os.path.join(os.path.dirname(_HERE), "archive")
if os.path.isdir(_ARCHIVE):
    os.environ.setdefault("BRAILAB_ARCHIVE", _ARCHIVE)

import numpy as np                       # noqa: E402  (from the bundle, via sys.path)
import talkhun                            # noqa: E402
import chip_synth                         # noqa: E402

ESC = "\x1b"
MAX_STRING_LENGTH = 400
OUT_RATE = 10000                          # chip_synth's native rate; nvwave plays it
OUT_SCALE = 20000.0                       # float render -> int16


class SynthDriver(SynthDriver):
    name = "brailabEmulated"
    description = "Brailab PC (emulated, PCF8200)"

    supportedSettings = (
        SynthDriver.RateSetting(),
        SynthDriver.VolumeSetting(),
        BooleanDriverSetting("furcsa", "&Furcsa (weird voice)", defaultVal=False,
                             availableInSettingsRing=True),
        BooleanDriverSetting("useIntonation", "&Use intonation", defaultVal=True,
                             availableInSettingsRing=True),
    )
    supportedCommands = {IndexCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        # Available if the engine deps can be imported (they were, at module load).
        return "talkhun" in sys.modules and "chip_synth" in sys.modules

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._volume = 90
        self._furcsa = False
        self._useIntonation = True
        self.speaking = False
        self._gen = 0                     # bumped on cancel; stale utterances/callbacks self-check

        self._engine = talkhun.load()     # boots TALKHUN under Unicorn (~1-2 s, once)

        try:
            outputDevice = __import__("config").conf["speech"]["outputDevice"]
        except Exception:
            outputDevice = __import__("config").conf["audio"]["outputDevice"]
        self._player = nvwave.WavePlayer(1, OUT_RATE, 16, outputDevice=outputDevice)

        self._bgQueue = queue.Queue()
        self._bgThread = threading.Thread(target=self._bgRun,
                                          name="brailabEmulated.bg", daemon=True)
        self._bgThread.start()

    # ----- rendering (bg thread only touches the engine) -----

    def _timeScale(self):
        return 0.9 - 0.55 * (max(0, min(100, self._rate)) / 100.0)

    def _toPCM(self, x, gain, fade_in, fade_out):
        # 4 ms raised-cosine fade only at the very start / very end of the whole
        # utterance (onset pop / end click) -- never between streamed blocks, so
        # there are no seams.
        if fade_in or fade_out:
            x = x.copy()
            nf = min(40, len(x) // 2)
            if nf > 1:
                w = np.sin(np.linspace(0.0, np.pi / 2.0, nf)) ** 2
                if fade_in:
                    x[:nf] *= w
                if fade_out:
                    x[-nf:] *= w[::-1]
        return np.clip(x * (OUT_SCALE * gain), -32767, 32767).astype("<i2").tobytes()

    def _renderStream(self, text):
        # A lone capital reads as a Roman numeral in TALKHUN ("I" -> "első"); a
        # trailing space makes the engine read it as the letter instead. Only
        # single-character utterances (character echo / spelling) need this.
        if len(text) == 1:
            text = text + " "
        self._engine.feed(ESC + ("F1" if self._furcsa else "F0"))
        seq = self._engine.capture(text)
        gain = 0.25 + 1.0 * (self._volume / 100.0)
        # Stream the OUTPUT of ONE continuous render: chip_synth guarantees the
        # concatenated blocks are bit-identical to a whole render_chip_fast, so the
        # SOUND is unchanged (one intonation contour, no per-piece pitch reset), but
        # the first block reaches the player after ~0.4 s of speech is ready instead
        # of after the whole utterance renders.  Hold the previous block so the last
        # one can be faded out; fade in only the first.
        prev = None
        first = True
        for blk in chip_synth.render_chip_stream(
                seq, time_scale=self._timeScale(),
                flat_pitch=not self._useIntonation):
            if prev is not None:
                yield self._toPCM(prev, gain, first, False)
                first = False
            prev = blk
        if prev is not None:
            yield self._toPCM(prev, gain, first, True)

    # ----- Say-All-friendly block building -----

    def _buildBlocks(self, speechSequence):
        blocks = []
        buf = []

        def flush(indexesAfter):
            blocks.append((" ".join(buf).strip(), indexesAfter))
            buf.clear()

        for item in speechSequence:
            if isinstance(item, str):
                buf.append(item)
            elif isinstance(item, IndexCommand):
                flush([item.index])
        if buf:
            flush([])
        while blocks and (not blocks[-1][0]) and (not blocks[-1][1]):
            blocks.pop()
        anyText = any(t for (t, _) in blocks)
        allIndexes = [i for (_, idxs) in blocks for i in idxs]
        return blocks, anyText, allIndexes

    # ----- SynthDriver API -----

    def speak(self, speechSequence):
        blocks, anyText, allIndexes = self._buildBlocks(speechSequence)
        gen = self._gen                   # valid until a cancel bumps _gen
        if not anyText:
            def done(idxs=allIndexes, gen=gen):
                if gen != self._gen:
                    return
                for i in idxs:
                    synthIndexReached.notify(synth=self, index=i)
                synthDoneSpeaking.notify(synth=self)
            self._bgQueue.put(done)
            return
        self._bgQueue.put(lambda: self._speakBg(blocks, gen))

    def _speakBg(self, blocks, gen):
        for (text, indexesAfter) in blocks:
            if gen != self._gen:
                return
            if text:
                for i in range(0, len(text), MAX_STRING_LENGTH):
                    if gen != self._gen:
                        return
                    try:
                        for pcm in self._renderStream(text[i:i + MAX_STRING_LENGTH]):
                            if gen != self._gen:
                                return
                            if pcm:
                                self._player.feed(pcm)
                    except Exception:
                        log.error("brailabEmulated: render failed", exc_info=True)
                        return
            if gen == self._gen and indexesAfter:
                idxs = list(indexesAfter)

                def cb(idxs=idxs, gen=gen):
                    if gen == self._gen:
                        for i in idxs:
                            synthIndexReached.notify(synth=self, index=i)
                self._player.feed(b"", 0, onDone=cb)

        def doneCb(gen=gen):
            if gen == self._gen:
                synthDoneSpeaking.notify(synth=self)
        self._player.feed(b"", 0, onDone=doneCb)
        self._player.idle()

    def cancel(self):
        self._gen += 1                    # invalidate the in-flight utterance + its callbacks
        self.speaking = False
        try:
            self._player.stop()
        except Exception:
            pass
        try:
            while True:
                self._bgQueue.get_nowait()
                self._bgQueue.task_done()
        except queue.Empty:
            pass
        except Exception:
            pass

    def pause(self, switch):
        try:
            self._player.pause(switch)
        except Exception:
            pass

    def _bgRun(self):
        while True:
            func = self._bgQueue.get()
            try:
                if func is None:
                    return
                func()
            except Exception:
                log.error("brailabEmulated: bg error", exc_info=True)
            finally:
                self._bgQueue.task_done()

    def terminate(self):
        self.cancel()
        try:
            self._bgQueue.put(None)
            self._bgThread.join(timeout=2)
        except Exception:
            pass
        try:
            if self._player:
                self._player.close()
        except Exception:
            pass
        self._player = None
        self._engine = None

    # ----- settings -----

    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        self._rate = max(0, min(100, int(value)))

    def _get_volume(self):
        return self._volume

    def _set_volume(self, value):
        self._volume = max(0, min(100, int(value)))

    def _get_furcsa(self):
        return self._furcsa

    def _set_furcsa(self, value):
        self._furcsa = bool(value)

    def _get_useIntonation(self):
        return self._useIntonation

    def _set_useIntonation(self, value):
        self._useIntonation = bool(value)
