# -*- coding: utf-8 -*-
# synthDrivers/brailab.py

import os
import ctypes
import threading
import queue
import time
import re

import nvwave
import config

from logHandler import log
from synthDriverHandler import SynthDriver, synthDoneSpeaking, synthIndexReached
from speech.commands import IndexCommand
from autoSettingsUtils.driverSetting import BooleanDriverSetting


minRate = 0
maxRate = 9

minPitch = -1
maxPitch = 1

minVol = -2
maxVol = 2

MAX_STRING_LENGTH = 450

BL_ITEM_NONE = 0
BL_ITEM_AUDIO = 1
BL_ITEM_DONE = 2
BL_ITEM_ERROR = 3


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


def _find_tts_dll(base_path: str) -> str:
	for p in (
		os.path.join(base_path, "brailab", "tts.dll"),
		os.path.join(base_path, "brailab", "TTS.dll"),
		os.path.join(base_path, "tts.dll"),
		os.path.join(base_path, "TTS.dll"),
	):
		if os.path.isfile(p):
			return p
	return ""


_PUNCT_TRANSLATE = str.maketrans({
	"’": "'",
	"‘": "'",
	"“": '"',
	"”": '"',
	"–": "-",
	"—": "-",
	"…": "...",
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


def _sanitizeText(s: str) -> str:
	if not s:
		return ""

	s = s.translate(_PUNCT_TRANSLATE)

	for ch in _STRIP_CHARS:
		s = s.replace(ch, "")

	s = _control_re.sub(" ", s)

	# Keep BMP only (avoid surrogate/emoji edge cases)
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

	# Brailab tends to behave better with space than '?'
	s = s.replace("?", " ")
	s = " ".join(s.split())
	return s.strip()


class SynthDriver(SynthDriver):
	name = "brailab"
	description = "Brailab PC (nvwave)"

	supportedSettings = (
		SynthDriver.RateSetting(minStep=10),
		# Pitch is -1/0/+1 => meaningful ring steps are 0/50/100.
		SynthDriver.PitchSetting(minStep=50),
		# Volume is -2..+2 => meaningful ring steps are 0/25/50/75/100.
		SynthDriver.VolumeSetting(minStep=25),
		BooleanDriverSetting(
			"useIntonation",
			"&Use intonation",
			defaultVal=True,
			availableInSettingsRing=True
		),
	)

	supportedCommands = {IndexCommand}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		base_path = os.path.dirname(__file__)
		tts_path = _find_tts_dll(base_path)
		wrapper_path = os.path.join(base_path, "brailab_wrapper.dll")
		return bool(tts_path) and os.path.isfile(wrapper_path)

	def __init__(self):
		super().__init__()

		self._base_path = os.path.dirname(__file__)
		self._tts_path = _find_tts_dll(self._base_path)
		self._wrapper_path = os.path.join(self._base_path, "brailab_wrapper.dll")

		if not self._tts_path:
			raise RuntimeError("Brailab: tts.dll not found")
		if not os.path.isfile(self._wrapper_path):
			raise RuntimeError("Brailab: brailab_wrapper.dll not found")

		self._dll = ctypes.cdll[self._wrapper_path]

		# Prototypes
		self._dll.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int)
		self._dll.bl_initW.restype = ctypes.c_void_p

		self._dll.bl_free.argtypes = (ctypes.c_void_p,)
		self._dll.bl_free.restype = None

		self._dll.bl_stop.argtypes = (ctypes.c_void_p,)
		self._dll.bl_stop.restype = None

		self._dll.bl_startSpeakW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
		self._dll.bl_startSpeakW.restype = ctypes.c_int

		self._dll.bl_read.argtypes = (
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_int),
			ctypes.POINTER(ctypes.c_int),
			ctypes.c_void_p,
			ctypes.c_int
		)
		self._dll.bl_read.restype = ctypes.c_int

		self._dll.bl_getTempo.argtypes = (ctypes.c_void_p,)
		self._dll.bl_getTempo.restype = ctypes.c_int
		self._dll.bl_setTempo.argtypes = (ctypes.c_void_p, ctypes.c_int)
		self._dll.bl_setTempo.restype = None

		self._dll.bl_getPitch.argtypes = (ctypes.c_void_p,)
		self._dll.bl_getPitch.restype = ctypes.c_int
		self._dll.bl_setPitch.argtypes = (ctypes.c_void_p, ctypes.c_int)
		self._dll.bl_setPitch.restype = None

		self._dll.bl_getVolume.argtypes = (ctypes.c_void_p,)
		self._dll.bl_getVolume.restype = ctypes.c_int
		self._dll.bl_setVolume.argtypes = (ctypes.c_void_p, ctypes.c_int)
		self._dll.bl_setVolume.restype = None

		# Init wrapper
		self._handle = self._dll.bl_initW(self._tts_path, 1500)
		if not self._handle:
			raise RuntimeError("Brailab: wrapper init failed")

		# Background queue thread
		global bgQueue
		bgQueue = queue.Queue()
		self._bgThread = BgThread()
		self._bgThread.start()

		self.speaking = False
		self._useIntonation = True

		# Output device
		try:
			outputDevice = config.conf["speech"]["outputDevice"]
		except Exception:
			outputDevice = config.conf["audio"]["outputDevice"]

		# Keep the known-good Brailab format.
		self._player = nvwave.WavePlayer(1, 10000, 16, outputDevice=outputDevice)

		# Reusable buffer for audio pulls
		self._bufSize = 65536
		self._audioBuf = ctypes.create_string_buffer(self._bufSize)

	def _quantizePercent(self, value, step):
		try:
			v = int(value)
		except Exception:
			v = 0
		if v < 0:
			v = 0
		if v > 100:
			v = 100
		q = int(round(v / float(step))) * int(step)
		if q < 0:
			q = 0
		if q > 100:
			q = 100
		return q

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

		if self._handle:
			try:
				self._dll.bl_free(self._handle)
			except Exception:
				log.error("Brailab: error in bl_free", exc_info=True)
			self._handle = None

		self._dll = None
		self._player = None

	def cancel(self):
		self.speaking = False

		# Stop wrapper + wave player
		if self._handle:
			try:
				self._dll.bl_stop(self._handle)
			except Exception:
				pass
		if self._player:
			try:
				self._player.stop()
			except Exception:
				pass

		# Clear bg queue properly
		try:
			while True:
				bgQueue.get_nowait()
				bgQueue.task_done()
		except queue.Empty:
			pass
		except Exception:
			pass

	def pause(self, switch):
		if self._player:
			self._player.pause(switch)

	def _buildBlocks(self, speechSequence):
		"""
		Convert NVDA speechSequence into (text, [indexesAfterText]) blocks,
		preserving IndexCommand order. This is what makes Say All work reliably.
		"""
		blocks = []
		textBuf = []

		def flush_with_indexes(indexesAfter):
			raw = " ".join(textBuf)
			textBuf.clear()
			safe = _brailabSafeText(raw)
			blocks.append((safe, indexesAfter))

		for item in speechSequence:
			if isinstance(item, str):
				textBuf.append(item)
			elif isinstance(item, IndexCommand):
				flush_with_indexes([item.index])
			else:
				# ignore other commands for this synth
				pass

		# trailing text with no index after it
		if textBuf:
			flush_with_indexes([])

		# Remove trailing empty blocks with no indexes
		while blocks and (not blocks[-1][0]) and (not blocks[-1][1]):
			blocks.pop()

		anyText = any(bool(t) for (t, _) in blocks)
		allIndexes = []
		for (_, idxs) in blocks:
			allIndexes.extend(idxs)

		return blocks, anyText, allIndexes

	def _notifyIndexesAndDone(self, indexes):
		# Used when there is no speech audio at all, but NVDA still needs indexes.
		for i in indexes:
			synthIndexReached.notify(synth=self, index=i)
		synthDoneSpeaking.notify(synth=self)
		self.speaking = False

	def speak(self, speechSequence):
		# Shortcut: a single index command
		if len(speechSequence) == 1 and isinstance(speechSequence[0], IndexCommand):
			# If we’re busy, keep ordering by queueing it.
			if self.speaking or bgQueue.unfinished_tasks != 0:
				_execWhenDone(self._notifyIndexesAndDone, [speechSequence[0].index], mustBeAsync=True)
			else:
				synthIndexReached.notify(synth=self, index=speechSequence[0].index)
				synthDoneSpeaking.notify(synth=self)
			return

		blocks, anyText, allIndexes = self._buildBlocks(speechSequence)

		# Nothing speakable: MUST still advance Say All by firing indexes (and done).
		if not anyText:
			if allIndexes:
				_execWhenDone(self._notifyIndexesAndDone, allIndexes, mustBeAsync=True)
			else:
				# No text and no indexes: still signal done so NVDA doesn’t wait.
				if self.speaking or bgQueue.unfinished_tasks != 0:
					_execWhenDone(self._notifyIndexesAndDone, [], mustBeAsync=True)
				else:
					synthDoneSpeaking.notify(synth=self)
			return

		_execWhenDone(self._speakBg, blocks, mustBeAsync=True)

	def _pumpUntilDone(self):
		outType = ctypes.c_int(0)
		outValue = ctypes.c_int(0)

		while self.speaking:
			madeProgress = False

			while True:
				try:
					n = self._dll.bl_read(
						self._handle,
						ctypes.byref(outType),
						ctypes.byref(outValue),
						self._audioBuf,
						self._bufSize
					)
				except Exception:
					log.error("Brailab: bl_read crashed", exc_info=True)
					return False

				t = outType.value
				v = outValue.value

				if t == BL_ITEM_AUDIO:
					if n > 0:
						madeProgress = True
						try:
							self._player.feed(self._audioBuf.raw[:n], n)
						except Exception:
							log.error("Brailab: nvwave feed error", exc_info=True)
							return False
					continue

				if t == BL_ITEM_DONE:
					return True

				if t == BL_ITEM_ERROR:
					log.error(f"Brailab: wrapper reported error {v}")
					return False

				break

			if not madeProgress:
				time.sleep(0.001)

		return False

	def _queueIndexMarker(self, indexes):
		if not indexes:
			return

		idxs = list(indexes)

		def cb(idxs=idxs):
			# If canceled, don’t keep firing indexes.
			if not self.speaking:
				return
			for i in idxs:
				synthIndexReached.notify(synth=self, index=i)

		# This acts like a marker in the audio stream.
		self._player.feed(b"", 0, onDone=cb)

	def _queueDoneMarker(self):
		def cb():
			if not self.speaking:
				return
			self.speaking = False
			synthDoneSpeaking.notify(synth=self)

		self._player.feed(b"", 0, onDone=cb)

	def _speakBg(self, blocks):
		self.speaking = True

		noIntonation = 0 if self._useIntonation else 1

		for (text, indexesAfter) in blocks:
			if not self.speaking:
				break

			# Speak text (can be empty)
			if text:
				segments = [text[i:i + MAX_STRING_LENGTH] for i in range(0, len(text), MAX_STRING_LENGTH)]

				for seg in segments:
					if not self.speaking:
						break

					seg = _brailabSafeText(seg)
					if not seg:
						continue

					try:
						rc = self._dll.bl_startSpeakW(self._handle, seg, noIntonation)
					except Exception:
						log.error("Brailab: bl_startSpeakW failed", exc_info=True)
						self.speaking = False
						break

					if rc != 0:
						log.error(f"Brailab: bl_startSpeakW returned {rc}")
						self.speaking = False
						break

					ok = self._pumpUntilDone()
					if not ok:
						# Fallback: strip non-ASCII for this segment to avoid engine fragility
						fallback = "".join((c if ord(c) < 128 else " ") for c in seg)
						fallback = " ".join(fallback.split())
						if fallback and fallback != seg and self.speaking:
							try:
								rc2 = self._dll.bl_startSpeakW(self._handle, fallback, noIntonation)
								if rc2 == 0:
									_ = self._pumpUntilDone()
							except Exception:
								pass
						# Stop the utterance chain
						self.speaking = False
						break

			# Queue index marker(s) even if text is empty.
			# This is what keeps Say All advancing.
			if self.speaking:
				self._queueIndexMarker(indexesAfter)

		if not self.speaking:
			# We stopped early; don’t hang NVDA waiting.
			synthDoneSpeaking.notify(synth=self)
			self.speaking = False
			return

		# Final done marker, then block until playback finishes.
		self._queueDoneMarker()
		self._player.idle()

	# ----- Settings ring -----

	def _get_rate(self):
		return self._paramToPercent(self._dll.bl_getTempo(self._handle), minRate, maxRate)

	def _set_rate(self, value):
		self._dll.bl_setTempo(self._handle, self._percentToParam(value, minRate, maxRate))

	def _get_pitch(self):
		p = self._paramToPercent(self._dll.bl_getPitch(self._handle), minPitch, maxPitch)
		return self._quantizePercent(p, 50)

	def _set_pitch(self, value):
		value = self._quantizePercent(value, 50)
		self._dll.bl_setPitch(self._handle, self._percentToParam(value, minPitch, maxPitch))

	def _get_volume(self):
		v = self._paramToPercent(self._dll.bl_getVolume(self._handle), minVol, maxVol)
		return self._quantizePercent(v, 25)

	def _set_volume(self, value):
		value = self._quantizePercent(value, 25)
		self._dll.bl_setVolume(self._handle, self._percentToParam(value, minVol, maxVol))
