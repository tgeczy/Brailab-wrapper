# -*- coding: utf-8 -*-
# synthDrivers/brailab.py
#
# NVDA SynthDriver for Brailab PC (Hungarian TTS).
# Uses a 32-bit host process for 64-bit NVDA compatibility.

import os
import re
import threading
import queue

from logHandler import log
from synthDriverHandler import SynthDriver, synthDoneSpeaking, synthIndexReached
from speech.commands import IndexCommand, PitchCommand
from autoSettingsUtils.driverSetting import BooleanDriverSetting

from . import _brailab


minRate = 0
maxRate = 9

minPitch = -1
maxPitch = 1

minVol = -2
maxVol = 2

MAX_STRING_LENGTH = 450


# --- Text sanitization (unchanged from original) ---

_PUNCT_TRANSLATE = str.maketrans({
	"\u2018": "'",
	"\u2019": "'",
	"\u201c": '"',
	"\u201d": '"',
	"\u2013": "-",
	"\u2014": "-",
	"\u2026": "...",
	"\u00a0": " ",  # NBSP
})

_control_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]+")

_STRIP_CHARS = {
	"\ufeff",  # BOM
	"\u00ad",  # soft hyphen
	"\u200b", "\u200c", "\u200d",  # zero width
	"\u200e", "\u200f",  # LRM/RLM
	"\u202a", "\u202b", "\u202c", "\u202d", "\u202e",  # bidi embeds
	"\u2066", "\u2067", "\u2068", "\u2069",  # bidi isolates
}


# --- Say All coalescing heuristics ---
_COALESCE_MAX_CHARS = 900
_COALESCE_MAX_INDEXES = 48
_SENT_END_RE = re.compile("(?:[.!?]+|\\.{3})[)\\]\"\']*\\s*$")

def _looksLikeSentenceEnd(s: str) -> bool:
	if not s:
		return False
	return bool(_SENT_END_RE.search(s.strip()))

def _sanitizeText(s: str) -> str:
	if not s:
		return ""
	s = s.translate(_PUNCT_TRANSLATE)
	for ch in _STRIP_CHARS:
		s = s.replace(ch, "")
	s = _control_re.sub(" ", s)
	s = "".join((c if ord(c) <= 0xFFFF else " ") for c in s)
	s = " ".join(s.split())
	return s.strip()


def _brailabSafeText(s: str) -> str:
	s = _sanitizeText(s)
	if not s:
		return ""
	try:
		s = s.encode("cp1250", errors="replace").decode("cp1250", errors="replace")
	except Exception:
		pass
	s = s.replace("?", " ")
	s = " ".join(s.split())
	return s.strip()


# --- Background work queue ---

class BgThread(threading.Thread):
	def __init__(self):
		super().__init__(name=f"{self.__class__.__module__}.{self.__class__.__qualname__}")
		self.daemon = True

	def run(self):
		while True:
			func, args, kwargs = bgQueue.get()
			try:
				if not func:
					return
				func(*args, **kwargs)
			except Exception:
				log.error("Error running background synth function", exc_info=True)
			finally:
				bgQueue.task_done()


def _execWhenDone(func, *args, mustBeAsync=False, **kwargs):
	global bgQueue
	if mustBeAsync or bgQueue.unfinished_tasks != 0:
		bgQueue.put((func, args, kwargs))
	else:
		func(*args, **kwargs)


# --- SynthDriver ---

class SynthDriver(SynthDriver):
	name = "brailab"
	description = "Brailab PC"

	supportedSettings = (
		SynthDriver.VoiceSetting(),
		SynthDriver.RateSetting(minStep=10),
		SynthDriver.PitchSetting(minStep=50),
		SynthDriver.VolumeSetting(minStep=25),
		BooleanDriverSetting(
			"useIntonation",
			"&Use intonation",
			defaultVal=True,
			availableInSettingsRing=True
		),
	)

	# PitchCommand is how NVDA marks a capital letter: "capital pitch change
	# percentage" arrives as an offset on its own 0-100 scale.  A driver that
	# does not list it never receives one, so the setting does nothing at every
	# value -- which is what was happening here.
	supportedCommands = {IndexCommand, PitchCommand}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	from collections import OrderedDict
	from synthDriverHandler import VoiceInfo
	_voices = OrderedDict([("1", VoiceInfo("1", "Hungarian", "hu"))])

	def _getAvailableVoices(self):
		return self._voices

	def _get_voice(self):
		return "1"

	def _set_voice(self, value):
		pass  # Only one voice available

	@classmethod
	def check(cls):
		return _brailab.check()

	def __init__(self):
		# Ensure config.pre_configSave exists (bridge host compat)
		import config
		if not hasattr(config, 'pre_configSave'):
			import extensionPoints
			config.pre_configSave = extensionPoints.Action()
		super().__init__()

		def _indexCallback(index):
			if index is None:
				self.speaking = False
				synthDoneSpeaking.notify(synth=self)
			else:
				synthIndexReached.notify(synth=self, index=index)

		result = _brailab.initialize(index_callback=_indexCallback)

		self._hasComposite = _brailab.has_composite()

		# Cache initial parameter values from the host
		self._cachedTempo = result.get("tempo", 4)
		self._cachedPitch = result.get("pitch", 0)
		# What is actually set on the engine right now.  It follows _cachedPitch
		# except while a PitchCommand (a capital) is in force.
		self._appliedPitch = self._cachedPitch
		self._cachedVolume = result.get("volume", 0)

		# Background queue thread (for ordering speech requests)
		global bgQueue
		bgQueue = queue.Queue()
		self._bgThread = BgThread()
		self._bgThread.start()

		self.speaking = False
		self._useIntonation = True

	def _quantizePercent(self, value, step):
		try:
			v = int(value)
		except Exception:
			v = 0
		v = max(0, min(100, v))
		q = int(round(v / float(step))) * int(step)
		return max(0, min(100, q))

	def _set_useIntonation(self, val):
		self._useIntonation = bool(val)

	def _get_useIntonation(self):
		return bool(getattr(self, "_useIntonation", True))

	def terminate(self):
		self.cancel()
		try:
			bgQueue.put((None, None, None))
			self._bgThread.join()
		except Exception:
			pass
		_brailab.terminate()

	def cancel(self):
		self.speaking = False
		_brailab.stop()
		# Clear bg queue
		try:
			while True:
				bgQueue.get_nowait()
				bgQueue.task_done()
		except queue.Empty:
			pass
		except Exception:
			pass

	def pause(self, switch):
		_brailab.pause(switch)

	def _buildBlocks(self, speechSequence, coalesceSayAll=False):
		blocks = []
		textBuf = []
		pendingIndexes = []
		seenNonEmptyText = False
		pitchAdj = 0

		def flush():
			nonlocal seenNonEmptyText
			raw = " ".join(textBuf)
			textBuf.clear()
			safe = _brailabSafeText(raw)
			blocks.append((safe, pendingIndexes.copy(), pitchAdj))
			pendingIndexes.clear()
			seenNonEmptyText = False

		for item in speechSequence:
			if isinstance(item, str):
				if item:
					textBuf.append(item)
					if item.strip():
						seenNonEmptyText = True
			elif isinstance(item, PitchCommand):
				# Applies to everything after it, so close the current block:
				# that is what lets a capital sound higher than its neighbours.
				if textBuf:
					flush()
				pitchAdj = item.offset
				continue
			elif isinstance(item, IndexCommand):
				if not seenNonEmptyText and not textBuf:
					blocks.append(("", [item.index], pitchAdj))
					continue
				pendingIndexes.append(item.index)
				if not coalesceSayAll:
					flush()
					continue
				safeSoFar = _brailabSafeText(" ".join(textBuf))
				if (
					_looksLikeSentenceEnd(safeSoFar)
					or len(safeSoFar) >= _COALESCE_MAX_CHARS
					or len(pendingIndexes) >= _COALESCE_MAX_INDEXES
				):
					flush()

		if textBuf or pendingIndexes:
			flush()

		while blocks and (not blocks[-1][0]) and (not blocks[-1][1]):
			blocks.pop()

		anyText = any(bool(t) for (t, _, _) in blocks)
		allIndexes = []
		for (_, idxs, _) in blocks:
			allIndexes.extend(idxs)

		return blocks, anyText, allIndexes

	def _notifyIndexesAndDone(self, indexes):
		for i in indexes:
			synthIndexReached.notify(synth=self, index=i)
		synthDoneSpeaking.notify(synth=self)
		self.speaking = False

	def speak(self, speechSequence):
		# Shortcut: a single index command
		if len(speechSequence) == 1 and isinstance(speechSequence[0], IndexCommand):
			if self.speaking or bgQueue.unfinished_tasks != 0:
				_execWhenDone(self._notifyIndexesAndDone, [speechSequence[0].index], mustBeAsync=True)
			else:
				synthIndexReached.notify(synth=self, index=speechSequence[0].index)
				synthDoneSpeaking.notify(synth=self)
			return

		hasIndex = any(isinstance(i, IndexCommand) for i in speechSequence)
		blocks, anyText, allIndexes = self._buildBlocks(speechSequence, coalesceSayAll=hasIndex)

		if not anyText:
			if allIndexes:
				_execWhenDone(self._notifyIndexesAndDone, allIndexes, mustBeAsync=True)
			else:
				if self.speaking or bgQueue.unfinished_tasks != 0:
					_execWhenDone(self._notifyIndexesAndDone, [], mustBeAsync=True)
				else:
					synthDoneSpeaking.notify(synth=self)
			return

		if hasIndex and self._hasComposite:
			_execWhenDone(self._speakBgComposite, blocks, mustBeAsync=True)
		else:
			_execWhenDone(self._speakBg, blocks, mustBeAsync=True)

	def _speakBgComposite(self, blocks):
		"""Speak using the composite utterance API via IPC."""
		self.speaking = True
		noIntonation = 0 if self._useIntonation else 1

		try:
			_brailab.begin_utterance(noIntonation)
		except Exception:
			log.error("Brailab: begin_utterance failed", exc_info=True)
			self.speaking = False
			synthDoneSpeaking.notify(synth=self)
			return

		for (text, indexesAfter, pitchAdj) in blocks:
			if not self.speaking:
				break

			self._applyBlockPitch(pitchAdj)

			if text:
				segments = [text[i:i + MAX_STRING_LENGTH] for i in range(0, len(text), MAX_STRING_LENGTH)]
				for seg in segments:
					if not self.speaking:
						break
					seg = _brailabSafeText(seg)
					if not seg:
						continue
					try:
						_brailab.add_text(seg)
					except Exception:
						log.error("Brailab: add_text failed", exc_info=True)
						self.speaking = False
						break

			if self.speaking and indexesAfter:
				for i in indexesAfter:
					try:
						_brailab.add_index(int(i))
					except Exception:
						log.error("Brailab: add_index failed", exc_info=True)
						self.speaking = False
						break

		if not self.speaking:
			try:
				_brailab.stop()
			except Exception:
				pass
			self.speaking = False
			synthDoneSpeaking.notify(synth=self)
			return

		# Put the voice back the way the user set it: a capital must not leave
		# the whole synthesizer retuned.
		self._restorePitch()

		try:
			# commit_utterance blocks until the host finishes reading all audio.
			# Audio events flow to AudioWorker → WavePlayer automatically.
			_brailab.commit_utterance()
		except Exception:
			log.error("Brailab: commit_utterance failed", exc_info=True)
			self.speaking = False
			synthDoneSpeaking.notify(synth=self)

	def _speakBg(self, blocks):
		"""Speak using legacy single-chunk API via IPC."""
		self.speaking = True
		noIntonation = 0 if self._useIntonation else 1

		for (text, indexesAfter, pitchAdj) in blocks:
			if not self.speaking:
				break

			self._applyBlockPitch(pitchAdj)

			if text:
				segments = [text[i:i + MAX_STRING_LENGTH] for i in range(0, len(text), MAX_STRING_LENGTH)]
				for seg in segments:
					if not self.speaking:
						break
					seg = _brailabSafeText(seg)
					if not seg:
						continue
					try:
						# speak() blocks until the host finishes reading all audio
						_brailab.speak(seg, noIntonation)
					except Exception:
						log.error("Brailab: speak failed", exc_info=True)
						self.speaking = False
						break

		self._restorePitch()

		if not self.speaking:
			synthDoneSpeaking.notify(synth=self)
			return

		# The AudioWorker handles done notification via the index callback (None).
		# But if we get here without the host sending a final marker, notify manually.
		# In practice the host always sends final=True which triggers callback(None).

	# ----- Pitch, including NVDA's capital pitch change -----

	def _applyBlockPitch(self, adj):
		"""Set the engine's pitch for one block, user setting plus NVDA's offset.

		`adj` is a PitchCommand offset on NVDA's 0-100 scale, which is how the
		capital pitch change percentage arrives.  The user's own setting stays in
		`_cachedPitch` untouched -- only `_appliedPitch` moves -- so a capital
		does not permanently retune the voice.  Restored by `_restorePitch()`
		when the utterance ends.
		"""
		want = self._cachedPitch
		if adj:
			pct = max(0, min(100, self._get_pitch() + adj))
			want = self._percentToParam(pct, minPitch, maxPitch)
		if want != self._appliedPitch:
			try:
				_brailab.set_pitch(want)
				self._appliedPitch = want
			except Exception:
				log.error("Brailab: set_pitch failed", exc_info=True)

	def _restorePitch(self):
		if self._appliedPitch != self._cachedPitch:
			try:
				_brailab.set_pitch(self._cachedPitch)
				self._appliedPitch = self._cachedPitch
			except Exception:
				log.error("Brailab: set_pitch restore failed", exc_info=True)

	# ----- Settings ring -----

	def _get_rate(self):
		return self._paramToPercent(self._cachedTempo, minRate, maxRate)

	def _set_rate(self, value):
		raw = self._percentToParam(value, minRate, maxRate)
		self._cachedTempo = raw
		_brailab.set_tempo(raw)

	def _get_pitch(self):
		p = self._paramToPercent(self._cachedPitch, minPitch, maxPitch)
		return self._quantizePercent(p, 50)

	def _set_pitch(self, value):
		value = self._quantizePercent(value, 50)
		raw = self._percentToParam(value, minPitch, maxPitch)
		self._cachedPitch = raw
		self._appliedPitch = raw
		_brailab.set_pitch(raw)

	def _get_volume(self):
		v = self._paramToPercent(self._cachedVolume, minVol, maxVol)
		return self._quantizePercent(v, 25)

	def _set_volume(self, value):
		value = self._quantizePercent(value, 25)
		raw = self._percentToParam(value, minVol, maxVol)
		self._cachedVolume = raw
		_brailab.set_volume(raw)


# ---------------------------------------------------------------------------
# 64-bit NVDA 2026.1+: use the built-in bridge to run the full driver in a
# 32-bit host process.  Audio plays from the host directly via nvwave.
# On 32-bit (including the bridge host), this block is skipped and the
# SynthDriver class defined above is used as-is.
# ---------------------------------------------------------------------------
import ctypes as _ctypes
if _ctypes.sizeof(_ctypes.c_void_p) == 8:
	from _bridge.clients.synthDriverHost32.synthDriver import SynthDriverProxy32 as _Proxy32

	class SynthDriver(_Proxy32):
		name = "brailab"
		description = "Brailab PC"
		synthDriver32Path = os.path.dirname(__file__)
		synthDriver32Name = "brailab"

		# On 64-bit NVDA this proxy is the class NVDA actually talks to, so it
		# is this supportedCommands that decides what NVDA will send.  Listing
		# PitchCommand here is what makes "capital pitch change percentage"
		# reach the 32-bit driver at all; the bridge forwards the sequence and
		# the real driver applies it per block.
		supportedCommands = {IndexCommand, PitchCommand}

		# The bridge proxy only has _get_/_set_ for these 6 settings.
		# Filter out everything else so the voice dialog doesn't crash.
		_BRIDGE_SAFE = frozenset({"voice", "variant", "rate", "pitch", "volume", "rateBoost"})

		def _get_supportedSettings(self):
			return [s for s in super()._get_supportedSettings() if s.id in self._BRIDGE_SAFE]

		@classmethod
		def check(cls):
			if not super().check():
				return False
			base = os.path.dirname(__file__)
			return (
				os.path.isfile(os.path.join(base, "brailab_wrapper.dll"))
				and _brailab._find_tts_dll(base) != ""
			)
