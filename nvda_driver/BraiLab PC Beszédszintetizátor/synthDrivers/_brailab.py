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
		self._sequence = 0
		self._current_seq = 0
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
		self._player = player
		self._audio_worker = AudioWorker(player, self._audio_queue,
										 lambda: self._sequence)
		self._audio_worker.start()

	# ------------------------------------------------------------------
	# Speech (blocking — called from BgThread in the driver)
	def do_speak(self, text: str, no_intonation: int) -> None:
		self._should_stop = False
		self._current_seq = self._sequence
		rc = self._dll.bl_startSpeakW(self._handle, text, no_intonation)
		if rc != 0:
			LOGGER.error("bl_startSpeakW returned %d", rc)
			self._audio_queue.put((b"", None, True, self._current_seq))
			return
		self._read_loop()

	def do_begin_utterance(self, no_intonation: int) -> None:
		self._should_stop = False
		self._current_seq = self._sequence
		self._dll.bl_beginUtterance(self._handle, no_intonation)

	def do_add_text(self, text: str) -> None:
		self._dll.bl_addTextUtteranceW(self._handle, text)

	def do_add_index(self, index: int) -> None:
		self._dll.bl_addIndexUtterance(self._handle, index)

	def do_commit_utterance(self) -> None:
		self._should_stop = False
		rc = self._dll.bl_commitUtterance(self._handle)
		if rc != 0:
			LOGGER.error("bl_commitUtterance returned %d", rc)
			self._audio_queue.put((b"", None, True, self._current_seq))
			return
		self._read_loop()

	def _read_loop(self) -> None:
		"""Poll bl_read() and push audio chunks to the queue."""
		while not self._should_stop:
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
				self._audio_queue.put((b"", None, True, self._current_seq))
				return

			t = self._out_type.value
			v = self._out_value.value

			if t == BL_ITEM_AUDIO and n > 0:
				self._audio_queue.put((bytes(self._audio_buf.raw[:n]), None, False, self._current_seq))
			elif t == BL_ITEM_INDEX:
				self._audio_queue.put((b"", v, False, self._current_seq))
			elif t == BL_ITEM_DONE:
				self._audio_queue.put((b"", None, True, self._current_seq))
				return
			elif t == BL_ITEM_ERROR:
				LOGGER.error("Wrapper error %d", v)
				self._audio_queue.put((b"", None, True, self._current_seq))
				return
			elif t == BL_ITEM_NONE:
				time.sleep(0.001)

	# ------------------------------------------------------------------
	# Control
	def stop(self) -> None:
		self._sequence += 1
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

	_format = result.get("format", {})
	_has_composite = result.get("hasComposite", False)

	_client.initialize_audio(
		channels=_format.get("channels", 1),
		sample_rate=_format.get("sampleRate", 10000),
		bits_per_sample=_format.get("bitsPerSample", 16),
	)

	return result


def has_composite() -> bool:
	return _has_composite


def speak(text: str, no_intonation: int = 0) -> None:
	"""Legacy single-chunk speech (blocks until done)."""
	_client.do_speak(text, no_intonation)


def begin_utterance(no_intonation: int = 0) -> None:
	_client.do_begin_utterance(no_intonation)


def add_text(text: str) -> None:
	_client.do_add_text(text)


def add_index(index: int) -> None:
	_client.do_add_index(index)


def commit_utterance() -> None:
	_client.do_commit_utterance()


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


def get_format() -> Dict[str, int]:
	return dict(_format)


def check() -> bool:
	"""Check if the required files are available."""
	base = os.path.abspath(os.path.dirname(__file__))
	wrapper_dll = os.path.join(base, "brailab_wrapper.dll")
	tts_dll = _find_tts_dll(base)
	return os.path.isfile(wrapper_dll) and bool(tts_dll)


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
