# -*- coding: utf-8 -*-
# synthDrivers/brailabEmulated.py
#
# Emulated BraiLab PC for NVDA: the 1991 TALKHUN engine on MAME's 8086 feeding a
# software model of the Philips PCF8200, all in C, IN-PROCESS inside NVDA -- no
# hardware, no vendor DLL, no subprocess, no numpy.  Same driver shell as the real
# TTS.dll "brailab" synth (settings, Say-All coalescing, chunking, index markers,
# nvwave), and it can do FURCSA hang, the weird voice the DLL lost.
#
# The library comes in both widths, so this runs in 32- and 64-bit NVDA alike.
# TALKHUN0.COM is Arato's work and lives only in the release package's archive/.

import os
import queue
import threading

import nvwave

from logHandler import log
from synthDriverHandler import SynthDriver, synthDoneSpeaking, synthIndexReached
from speech.commands import IndexCommand, PitchCommand
from autoSettingsUtils.driverSetting import BooleanDriverSetting

from ._brailab_native import brailab_voice

_COM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "archive", "TALKHUN0.COM")


class SynthDriver(SynthDriver):
    name = "brailabEmulated"
    description = "Brailab PC (emulated, PCF8200)"

    supportedSettings = (
        SynthDriver.RateSetting(),
        SynthDriver.PitchSetting(),
        SynthDriver.VolumeSetting(),
        BooleanDriverSetting("furcsa", "&Furcsa (weird voice)", defaultVal=False,
                             availableInSettingsRing=True),
        BooleanDriverSetting("useIntonation", "&Use intonation", defaultVal=True,
                             availableInSettingsRing=True),
    )
    # PitchCommand is how NVDA marks a capital letter -- "capital pitch change
    # percentage" arrives as an offset on its own 0-100 scale.  A driver that
    # does not list it never sees one, so the setting silently does nothing at
    # every value, which is exactly what was happening here.
    supportedCommands = {IndexCommand, PitchCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        try:
            return os.path.isfile(_COM) and brailab_voice.load_library() is not None
        except OSError:
            return False

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._pitch = 50
        self._volume = 90
        self._furcsa = False
        self._useIntonation = True
        self.speaking = False
        self._gen = 0                     # bumped on cancel; stale utterances/callbacks self-check

        with open(_COM, "rb") as f:
            self._voice = brailab_voice.Voice(f.read())

        try:
            outputDevice = __import__("config").conf["speech"]["outputDevice"]
        except Exception:
            outputDevice = __import__("config").conf["audio"]["outputDevice"]
        self._player = nvwave.WavePlayer(1, brailab_voice.RATE, 16, outputDevice=outputDevice)

        self._bgQueue = queue.Queue()
        self._bgThread = threading.Thread(target=self._bgRun,
                                          name="brailabEmulated.bg", daemon=True)
        self._bgThread.start()

    # ----- rendering (only the bg thread touches the voice) -----

    def _timeScale(self):
        return 0.9 - 0.55 * (max(0, min(100, self._rate)) / 100.0)

    def _pitchFactor(self, adj=0):
        """NVDA's 0-100 pitch as a factor to transpose the engine's own contour.

        `adj` is what NVDA has asked for on top of the user's setting -- a
        PitchCommand carrying the capital pitch change percentage.  The two are
        clamped together, so a user already at 90 who asks for another 30 gets
        the top rather than an out-of-range request.  50 is the voice as the
        engine renders it, and the slider spans an octave: half above, half
        below.
        """
        pitch = min(100, max(0, self._pitch + adj))
        return 2.0 ** ((pitch - 50) / 100.0)

    def _renderStream(self, text, pitchAdj=0):
        # The voice splits at the engine's own intonation units and streams each
        # one's blocks, fading only the very start and end of the whole text.
        return self._voice.stream(text, pitch=self._pitchFactor(pitchAdj),
                                  time_scale=self._timeScale(), furcsa=self._furcsa,
                                  intonation=self._useIntonation,
                                  gain=0.25 + 1.0 * (self._volume / 100.0))

    # ----- Say-All-friendly block building -----

    def _buildBlocks(self, speechSequence):
        """Split the sequence into (text, indexesAfter, pitchAdj) blocks.

        A PitchCommand applies to everything after it, so a block is closed
        whenever the offset changes: that is what lets a capital be spoken
        higher than the words on either side of it.
        """
        blocks = []
        buf = []
        pitchAdj = 0

        def flush(indexesAfter, adj):
            blocks.append((" ".join(buf).strip(), indexesAfter, adj))
            buf.clear()

        for item in speechSequence:
            if isinstance(item, str):
                buf.append(item)
            elif isinstance(item, IndexCommand):
                flush([item.index], pitchAdj)
            elif isinstance(item, PitchCommand):
                # An offset on NVDA's own 0-100 scale; 0 means the user's
                # setting again.  Close the current block so the change lands
                # exactly here rather than colouring text already buffered.
                if buf:
                    flush([], pitchAdj)
                pitchAdj = item.offset
        if buf:
            flush([], pitchAdj)
        while blocks and (not blocks[-1][0]) and (not blocks[-1][1]):
            blocks.pop()
        anyText = any(t for (t, _, _) in blocks)
        allIndexes = [i for (_, idxs, _) in blocks for i in idxs]
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
        for (text, indexesAfter, pitchAdj) in blocks:
            if gen != self._gen:
                return
            if text:
                try:
                    for pcm in self._renderStream(text, pitchAdj):
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
        # never under a render still running; and NVDA may terminate twice
        if self._voice is not None and not self._bgThread.is_alive():
            self._voice.close()
        try:
            if self._player:
                self._player.close()
        except Exception:
            pass
        self._player = None
        self._voice = None

    # ----- settings -----

    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        self._rate = max(0, min(100, int(value)))

    def _get_pitch(self):
        return self._pitch

    def _set_pitch(self, value):
        self._pitch = max(0, min(100, int(value)))

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
