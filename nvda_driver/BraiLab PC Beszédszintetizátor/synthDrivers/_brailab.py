"""Client-side helper for Brailab speech synthesis.

Loads brailab_wrapper.dll directly via ctypes.  On 64-bit NVDA 2026.1+
the entire synth driver (including this module) runs inside NVDA's built-in
32-bit bridge host, so this code always operates in a 32-bit process.
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

LOGGER = logging.getLogger(__name__)

def _load_first_feed():
	"""brailab_feed.py: beside this file in the add-on (build.py puts it there), two
	folders up in the repository, where the emulated driver shares it."""
	try:
		from . import brailab_feed
		return brailab_feed
	except ImportError:
		pass
	import importlib.util
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
						"brailab_feed.py")
	if not os.path.isfile(path):
		return None
	spec = importlib.util.spec_from_file_location("brailab_feed", path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


# an utterance's first feed, and indexes with no audio behind them (#3, #2)
_first = _load_first_feed()

# Stream item types from brailab_wrapper.h
BL_ITEM_NONE = 0
BL_ITEM_AUDIO = 1
BL_ITEM_DONE = 2
BL_ITEM_ERROR = 3
BL_ITEM_INDEX = 4

AudioChunk = Tuple[bytes, Optional[int], bool, int]  # (data, index, is_final, seq)


# ---------------------------------------------------------------------------
# Audio handling (shared by both 32-bit and 64-bit modes)
# ---------------------------------------------------------------------------

class AudioWorker(threading.Thread):
	"""Pulls audio events from the queue and feeds them to nvwave.WavePlayer."""

	def __init__(self, player, audio_queue: "queue.Queue[Optional[AudioChunk]]",
				 get_sequence: Callable[[], int]):
		super().__init__(daemon=True, name="BrailabAudioWorker")
		self._player = player
		self._queue = audio_queue
		self._get_sequence = get_sequence
		self._running = True
		self._stopping = False
		self._player_lock = threading.RLock()

	def run(self) -> None:
		while self._running:
			try:
				chunk = self._queue.get(timeout=0.1)
			except queue.Empty:
				continue
			if chunk is None:
				break

			data, index, is_final, seq = chunk

			# Skip stale chunks from cancelled speech
			if seq < self._get_sequence():
				self._queue.task_done()
				continue

			# Empty data with no index: just a final marker
			if not data and index is None:
				if is_final:
					with self._player_lock:
						if not self._stopping:
							self._player.idle()
					if not self._stopping:
						self._invoke_index_callback(None)
				self._queue.task_done()
				continue

			on_done = None
			if index is not None:
				def _callback(i=index):
					self._invoke_index_callback(i)
				on_done = _callback

			wrapped_on_done = self._make_on_done(on_done, is_final)

			if self._stopping:
				self._queue.task_done()
				continue

			try:
				with self._player_lock:
					if not self._stopping and self._player:
						self._player.feed(data, onDone=wrapped_on_done)
						# A stop() that came while this chunk went down: the chunk
						# would play at the head of the next utterance.  Stop again
						# from here, after the feed (#10).
						if data and seq < self._get_sequence():
							self._player.stop()
			except FileNotFoundError:
				LOGGER.warning("Sound device not found during feed")
			except Exception:
				LOGGER.exception("WavePlayer feed failed")
			self._queue.task_done()

	def stop(self) -> None:
		self._stopping = True
		self._running = False
		self._queue.put(None)

	def _make_on_done(self, callback, is_final: bool):
		def _on_done() -> None:
			try:
				if callback:
					callback()
			except Exception:
				LOGGER.exception("Index callback failed")
			if is_final:
				self._schedule_idle()
		return _on_done

	def _schedule_idle(self) -> None:
		pass

	def _invoke_index_callback(self, value: Optional[int]) -> None:
		if _on_index_reached:
			try:
				_on_index_reached(value)
			except Exception:
				LOGGER.exception("Index callback failed")


# ---------------------------------------------------------------------------
# 32-bit direct client (loads DLL in-process)
# ---------------------------------------------------------------------------

class BrailabDirectClient:
	"""Direct ctypes access to brailab_wrapper.dll for 32-bit NVDA."""

	def __init__(self) -> None:
		self._dll = None
		self._handle = None
		self._audio_queue: "queue.Queue[Optional[AudioChunk]]" = queue.Queue()
		self._player = None
		self._audio_worker: Optional[AudioWorker] = None
		self._should_stop = False
		self._has_composite = False
		self._api_version = 1
		self._comma_supported = False
		self._sequence = 0          # bumped first thing by stop(); a job carries the value it was queued under
		self._current_seq = 0
		self._added_indexes = []    # the utterance's indexes not yet seen back from the wrapper (#2)
		# Audio format
		self._sample_rate = 0
		self._channels = 0
		self._bits_per_sample = 0
		# Read buffer
		self._buf_size = 65536
		self._audio_buf = None
		self._out_type = None
		self._out_value = None

	def ensure_started(self) -> None:
		pass  # No host process needed

	def do_initialize(self, dll_path: str, tts_path: str, init_value: int) -> Dict[str, Any]:
		"""Load the wrapper DLL and initialize the engine."""
		self._dll = ctypes.cdll.LoadLibrary(dll_path)
		self._setup_ctypes()

		# Allocate read buffers
		self._audio_buf = ctypes.create_string_buffer(self._buf_size)
		self._out_type = ctypes.c_int(0)
		self._out_value = ctypes.c_int(0)

		self._handle = self._dll.bl_initW(tts_path, init_value)
		if not self._handle:
			raise RuntimeError("bl_initW returned NULL")

		# Detect composite API
		try:
			_ = self._dll.bl_beginUtterance
			_ = self._dll.bl_addTextUtteranceW
			_ = self._dll.bl_addIndexUtterance
			_ = self._dll.bl_commitUtterance
			self._has_composite = True
		except AttributeError:
			self._has_composite = False

		# A wrapper from before API version 2 has no bl_getApiVersion, and none
		# of what came with it.  Each newer feature is then simply not offered.
		try:
			self._api_version = int(self._dll.bl_getApiVersion())
		except AttributeError:
			self._api_version = 1
		# The comma setting also needs the one TTS.dll build the wrapper knows.
		try:
			self._comma_supported = bool(self._dll.bl_commaStyleSupported(self._handle))
		except AttributeError:
			self._comma_supported = False

		# Query audio format
		sr = ctypes.c_int(0)
		ch = ctypes.c_int(0)
		bps = ctypes.c_int(0)
		if self._dll.bl_getFormat(self._handle, ctypes.byref(sr), ctypes.byref(ch), ctypes.byref(bps)):
			self._sample_rate = sr.value
			self._channels = ch.value
			self._bits_per_sample = bps.value
		else:
			self._sample_rate = 10000
			self._channels = 1
			self._bits_per_sample = 16

		return {
			"format": {
				"sampleRate": self._sample_rate,
				"channels": self._channels,
				"bitsPerSample": self._bits_per_sample,
			},
			"hasComposite": self._has_composite,
			"apiVersion": self._api_version,
			"commaSupported": self._comma_supported,
			"tempo": self._dll.bl_getTempo(self._handle),
			"pitch": self._dll.bl_getPitch(self._handle),
			"volume": self._dll.bl_getVolume(self._handle),
		}

	def _setup_ctypes(self):
		dll = self._dll
		dll.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int)
		dll.bl_initW.restype = ctypes.c_void_p
		dll.bl_free.argtypes = (ctypes.c_void_p,)
		dll.bl_free.restype = None
		dll.bl_stop.argtypes = (ctypes.c_void_p,)
		dll.bl_stop.restype = None
		dll.bl_startSpeakW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
		dll.bl_startSpeakW.restype = ctypes.c_int
		dll.bl_read.argtypes = (
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_int),
			ctypes.POINTER(ctypes.c_int),
			ctypes.c_void_p,
			ctypes.c_int,
		)
		dll.bl_read.restype = ctypes.c_int
		dll.bl_getTempo.argtypes = (ctypes.c_void_p,)
		dll.bl_getTempo.restype = ctypes.c_int
		dll.bl_setTempo.argtypes = (ctypes.c_void_p, ctypes.c_int)
		dll.bl_setTempo.restype = None
		dll.bl_getPitch.argtypes = (ctypes.c_void_p,)
		dll.bl_getPitch.restype = ctypes.c_int
		dll.bl_setPitch.argtypes = (ctypes.c_void_p, ctypes.c_int)
		dll.bl_setPitch.restype = None
		dll.bl_getVolume.argtypes = (ctypes.c_void_p,)
		dll.bl_getVolume.restype = ctypes.c_int
		dll.bl_setVolume.argtypes = (ctypes.c_void_p, ctypes.c_int)
		dll.bl_setVolume.restype = None
		dll.bl_getFormat.argtypes = (
			ctypes.c_void_p,
			ctypes.POINTER(ctypes.c_int),
			ctypes.POINTER(ctypes.c_int),
			ctypes.POINTER(ctypes.c_int),
		)
		dll.bl_getFormat.restype = ctypes.c_int
		# Composite API (optional)
		try:
			dll.bl_beginUtterance.argtypes = (ctypes.c_void_p, ctypes.c_int)
			dll.bl_beginUtterance.restype = ctypes.c_int
			dll.bl_addTextUtteranceW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
			dll.bl_addTextUtteranceW.restype = ctypes.c_int
			dll.bl_addIndexUtterance.argtypes = (ctypes.c_void_p, ctypes.c_int)
			dll.bl_addIndexUtterance.restype = ctypes.c_int
			dll.bl_commitUtterance.argtypes = (ctypes.c_void_p,)
			dll.bl_commitUtterance.restype = ctypes.c_int
		except AttributeError:
			pass
		# API version 2 (optional): version, comma intonation
		try:
			dll.bl_getApiVersion.argtypes = ()
			dll.bl_getApiVersion.restype = ctypes.c_int
			dll.bl_commaStyleSupported.argtypes = (ctypes.c_void_p,)
			dll.bl_commaStyleSupported.restype = ctypes.c_int
			dll.bl_getCommaStyle.argtypes = (ctypes.c_void_p,)
			dll.bl_getCommaStyle.restype = ctypes.c_int
			dll.bl_setCommaStyle.argtypes = (ctypes.c_void_p, ctypes.c_int)
			dll.bl_setCommaStyle.restype = ctypes.c_int
		except AttributeError:
			pass

	# ------------------------------------------------------------------
	# Audio
	def initialize_audio(self, channels: int, sample_rate: int, bits_per_sample: int) -> None:
		if self._player:
			return
		import nvwave
		import config
		try:
			from buildVersion import version_year
		except ImportError:
			version_year = 2025

		if version_year >= 2025:
			device = config.conf["audio"]["outputDevice"]
			player = nvwave.WavePlayer(channels, sample_rate, bits_per_sample,
									   outputDevice=device)
		else:
			device = config.conf["speech"]["outputDevice"]
			player = nvwave.WavePlayer(channels, sample_rate, bits_per_sample,
									   outputDevice=device, buffered=True)
		if _first is not None:
			# FirstFeed: indexes given with no audio behind them (a piece TTS.dll
			# says nothing for) are never called by NVDA's player on a stopped
			# stream; FirstFeed starts it with one silent sample (#2, #3).
			player = _first.FirstFeed(player, sample_rate)
		self._player = player
		# A fresh queue for every worker: a stop sentinel a busy worker left
		# behind must not end the next one at once (#7).
		self._audio_queue = queue.Queue()
		self._audio_worker = AudioWorker(player, self._audio_queue,
										 lambda: self._sequence)
		self._audio_worker.start()

	# ------------------------------------------------------------------
	# Speech (blocking — called from BgThread in the driver).  Each takes the
	# sequence number the job was queued under: a stop() since then has bumped
	# it, and the job is refused rather than taken up (#4).
	def sequence(self) -> int:
		return self._sequence

	def _cancelled(self) -> bool:
		return self._current_seq != self._sequence

	def do_speak(self, text: str, no_intonation: int, seq: Optional[int] = None) -> bool:
		self._current_seq = self._sequence if seq is None else seq
		if self._cancelled():
			return False
		self._added_indexes = []
		rc = self._dll.bl_startSpeakW(self._handle, text, no_intonation)
		if rc != 0:
			LOGGER.error("bl_startSpeakW returned %d", rc)
			self._audio_queue.put((b"", None, True, self._current_seq))
			return True
		self._read_loop()
		return True

	def do_begin_utterance(self, no_intonation: int, seq: Optional[int] = None) -> bool:
		self._current_seq = self._sequence if seq is None else seq
		if self._cancelled():
			return False
		self._added_indexes = []
		self._dll.bl_beginUtterance(self._handle, no_intonation)
		return True

	def do_add_text(self, text: str) -> None:
		self._dll.bl_addTextUtteranceW(self._handle, text)

	def do_add_index(self, index: int) -> None:
		self._added_indexes.append(index)
		self._dll.bl_addIndexUtterance(self._handle, index)

	def do_commit_utterance(self, final: bool = True) -> None:
		"""Run the utterance built since begin.  final=False: a part of a longer one
		(before NVDA's pause), so its end is not the utterance's end."""
		if self._cancelled():
			return
		rc = self._dll.bl_commitUtterance(self._handle)
		if rc != 0:
			LOGGER.error("bl_commitUtterance returned %d", rc)
			self._owed_indexes()
			if final:
				self._audio_queue.put((b"", None, True, self._current_seq))
			return
		self._read_loop(final)

	def do_push_silence(self, ms: int) -> None:
		"""NVDA's pause (BreakCommand) between two parts of an utterance (#17)."""
		if self._cancelled() or ms <= 0:
			return
		n = int(self._sample_rate * max(1, self._channels) * (self._bits_per_sample // 8) * ms / 1000)
		n -= n % max(1, self._channels * (self._bits_per_sample // 8))
		self._audio_queue.put((b"\x00" * n, None, False, self._current_seq))

	def _owed_indexes(self) -> None:
		"""The utterance's indexes the wrapper never gave back (it gave up on a piece
		TTS.dll said nothing for, or failed): queued now, in order, so NVDA, which
		waits for an utterance's last index before it says more, is not left waiting
		(#2).  Not after a stop: NVDA wants none then."""
		if self._cancelled():
			return
		for i in self._added_indexes:
			self._audio_queue.put((b"", i, False, self._current_seq))
		self._added_indexes = []

	def _read_loop(self, final: bool = True) -> None:
		"""Poll bl_read() and push audio chunks to the queue."""
		while not self._cancelled():
			try:
				n = self._dll.bl_read(
					self._handle,
					ctypes.byref(self._out_type),
					ctypes.byref(self._out_value),
					self._audio_buf,
					self._buf_size,
				)
			except Exception:
				LOGGER.exception("bl_read crashed")
				self._owed_indexes()
				if final:
					self._audio_queue.put((b"", None, True, self._current_seq))
				return

			t = self._out_type.value
			v = self._out_value.value

			if t == BL_ITEM_AUDIO and n > 0:
				self._audio_queue.put((bytes(self._audio_buf.raw[:n]), None, False, self._current_seq))
			elif t == BL_ITEM_INDEX:
				if v in self._added_indexes:
					self._added_indexes.remove(v)
				self._audio_queue.put((b"", v, False, self._current_seq))
			elif t == BL_ITEM_DONE:
				self._owed_indexes()
				if final:
					self._audio_queue.put((b"", None, True, self._current_seq))
				return
			elif t == BL_ITEM_ERROR:
				LOGGER.error("Wrapper error %d", v)
				# The wrapper's DONE follows its ERROR: keep reading to it, so the
				# next utterance does not get this one's end.
				continue
			elif t == BL_ITEM_NONE:
				time.sleep(0.001)

	# ------------------------------------------------------------------
	# Control
	def stop(self) -> None:
		self._sequence += 1           # first: a job queued before now is refused from here on (#4)
		self._should_stop = True
		if self._handle:
			self._dll.bl_stop(self._handle)
		if self._player:
			try:
				self._player.stop()
			except Exception:
				LOGGER.exception("WavePlayer stop failed")

	def pause(self, switch: bool) -> None:
		if self._player:
			self._player.pause(switch)

	def set_tempo(self, value: int) -> None:
		self._dll.bl_setTempo(self._handle, value)

	def set_pitch(self, value: int) -> None:
		self._dll.bl_setPitch(self._handle, value)

	def set_volume(self, value: int) -> None:
		self._dll.bl_setVolume(self._handle, value)

	def set_comma_style(self, style: int) -> bool:
		"""0 = TTS.dll's own comma intonation, 1 = the gentler one.

		False if the wrapper or this TTS.dll cannot do it; nothing changes then.
		"""
		if not self._comma_supported:
			return False
		return self._dll.bl_setCommaStyle(self._handle, int(style)) == 0

	def comma_supported(self) -> bool:
		return self._comma_supported

	def has_composite_api(self) -> bool:
		return self._has_composite

	def get_format(self) -> Dict[str, int]:
		return {
			"sampleRate": self._sample_rate,
			"channels": self._channels,
			"bitsPerSample": self._bits_per_sample,
		}

	# ------------------------------------------------------------------
	# Shutdown
	def shutdown(self) -> None:
		if self._audio_worker:
			self._audio_worker.stop()
			self._audio_worker.join(timeout=1)
			self._audio_worker = None
		if self._player:
			self._player.close()
			self._player = None
		if self._handle:
			self._dll.bl_free(self._handle)
			self._handle = None



# ---------------------------------------------------------------------------
# Module-level singleton and public API
# ---------------------------------------------------------------------------

_client: BrailabDirectClient = BrailabDirectClient()
_on_index_reached: Optional[Callable] = None
_format: Dict[str, int] = {}
_has_composite: bool = False


def initialize(index_callback=None) -> Dict[str, Any]:
	"""Load the DLL and initialize the engine."""
	global _on_index_reached, _format, _has_composite
	_on_index_reached = index_callback

	addon_dir = os.path.abspath(os.path.dirname(__file__))
	tts_path = _find_tts_dll(addon_dir)
	dll_path = os.path.join(addon_dir, "brailab_wrapper.dll")

	result = _client.do_initialize(dll_path, tts_path, 1500)
	try:
		# TTS.dll loads without its data files and answers -1 to every getter;
		# it then gives no audio at all (#6).  Refuse it, so NVDA uses another synth.
		if -1 in (result.get("tempo"), result.get("pitch"), result.get("volume")):
			raise RuntimeError("TTS.dll did not initialise (are BINADATA.BIN and BINAHANK.BIN beside it?)")

		_format = result.get("format", {})
		_has_composite = result.get("hasComposite", False)

		_client.initialize_audio(
			channels=_format.get("channels", 1),
			sample_rate=_format.get("sampleRate", 10000),
			bits_per_sample=_format.get("bitsPerSample", 16),
		)
	except Exception:
		# Anything failing after the engine came up (no audio device yet, #5):
		# hand the engine back, or every later load in this process is refused.
		try:
			_client.shutdown()
		except Exception:
			LOGGER.exception("shutdown after a failed initialize")
		raise

	return result


def has_composite() -> bool:
	return _has_composite


def sequence() -> int:
	"""The stop count now: a job queued under this value is refused once stop() has run (#4)."""
	return _client.sequence()


def speak(text: str, no_intonation: int = 0, seq: Optional[int] = None) -> bool:
	"""Legacy single-chunk speech (blocks until done).  False: refused, a stop came since `seq`."""
	return _client.do_speak(text, no_intonation, seq)


def begin_utterance(no_intonation: int = 0, seq: Optional[int] = None) -> bool:
	"""False: refused, a stop came since `seq` (#4)."""
	return _client.do_begin_utterance(no_intonation, seq)


def add_text(text: str) -> None:
	_client.do_add_text(text)


def add_index(index: int) -> None:
	_client.do_add_index(index)


def commit_utterance(final: bool = True) -> None:
	_client.do_commit_utterance(final)


def push_silence(ms: int) -> None:
	_client.do_push_silence(ms)


def stop() -> None:
	_client.stop()


def pause(switch: bool) -> None:
	_client.pause(switch)


def terminate() -> None:
	_client.shutdown()


def set_tempo(value: int) -> None:
	_client.set_tempo(value)


def set_pitch(value: int) -> None:
	_client.set_pitch(value)


def set_volume(value: int) -> None:
	_client.set_volume(value)


def comma_supported() -> bool:
	"""Can this wrapper and this TTS.dll soften the comma intonation?"""
	return _client.comma_supported()


def set_comma_style(style: int) -> bool:
	return _client.set_comma_style(style)


def get_format() -> Dict[str, int]:
	return dict(_format)


def check(base: Optional[str] = None) -> bool:
	"""Check if the required files are available: the wrapper, TTS.dll, and the
	engine's two data files beside TTS.dll (without them it loads and is silent, #6)."""
	base = base or os.path.abspath(os.path.dirname(__file__))
	wrapper_dll = os.path.join(base, "brailab_wrapper.dll")
	tts_dll = _find_tts_dll(base)
	if not (os.path.isfile(wrapper_dll) and tts_dll):
		return False
	have = {f.lower() for f in os.listdir(os.path.dirname(tts_dll))}
	return "binadata.bin" in have and "binahank.bin" in have


def _find_tts_dll(base_path: str) -> str:
	for p in (
		os.path.join(base_path, "Brailab", "tts.dll"),
		os.path.join(base_path, "Brailab", "TTS.dll"),
		os.path.join(base_path, "brailab", "tts.dll"),
		os.path.join(base_path, "brailab", "TTS.dll"),
		os.path.join(base_path, "tts.dll"),
		os.path.join(base_path, "TTS.dll"),
	):
		if os.path.isfile(p):
			return p
	return ""
