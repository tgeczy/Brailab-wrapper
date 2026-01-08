// brailab_wrapper.cpp
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX

#define BRAILAB_WRAPPER_EXPORTS
#include "brailab_wrapper.h"

#include <windows.h>
#include <mmsystem.h>
#include <intrin.h>

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include <chrono>
#include <climits>

#include "MinHook.h"

#pragma comment(lib, "user32.lib")

// ------------------------------------------------------------
// Brailab exports
// ------------------------------------------------------------
typedef void(__stdcall *TTS_DoneCallback)(void);

typedef int  (__stdcall *TTS_InitFunc)(int initValue, TTS_DoneCallback cb);
typedef void (__stdcall *TTS_StartSayWFunc)(const wchar_t* text);
typedef void (__stdcall *TTS_StartSayNoIntonationWFunc)(const wchar_t* text);
typedef void (__stdcall *TTS_StopFunc)(void);

typedef int  (__stdcall *TTS_GetIntFunc)(void);
typedef void (__stdcall *TTS_SetIntFunc)(int);

// ------------------------------------------------------------
// SEH-safe helpers (NO STL, NO RAII). Keep these tiny.
// ------------------------------------------------------------
static __declspec(noinline) int seh_ttsInit(TTS_InitFunc fn, int initValue, TTS_DoneCallback cb) {
	if (!fn) return 0;
	__try { fn(initValue, cb); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

static __declspec(noinline) int seh_ttsStop(TTS_StopFunc fn) {
	if (!fn) return 0;
	__try { fn(); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

static __declspec(noinline) int seh_ttsStartSayW(TTS_StartSayWFunc fn, const wchar_t* text) {
	if (!fn || !text) return 0;
	__try { fn(text); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

static __declspec(noinline) int seh_ttsStartSayNoIntW(TTS_StartSayNoIntonationWFunc fn, const wchar_t* text) {
	if (!fn || !text) return 0;
	__try { fn(text); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

static __declspec(noinline) int seh_ttsGetInt(TTS_GetIntFunc fn, int* outVal) {
	if (!fn || !outVal) return 0;
	__try { *outVal = fn(); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { *outVal = 0; return 0; }
}

static __declspec(noinline) int seh_ttsSetInt(TTS_SetIntFunc fn, int v) {
	if (!fn) return 0;
	__try { fn(v); return 1; }
	__except (EXCEPTION_EXECUTE_HANDLER) { return 0; }
}

// ------------------------------------------------------------
// WinMM function pointer types + originals
// ------------------------------------------------------------
typedef MMRESULT (WINAPI *waveOutOpenFunc)(LPHWAVEOUT, UINT, LPCWAVEFORMATEX, DWORD_PTR, DWORD_PTR, DWORD);
typedef MMRESULT (WINAPI *waveOutPrepareHeaderFunc)(HWAVEOUT, LPWAVEHDR, UINT);
typedef MMRESULT (WINAPI *waveOutWriteFunc)(HWAVEOUT, LPWAVEHDR, UINT);
typedef MMRESULT (WINAPI *waveOutUnprepareHeaderFunc)(HWAVEOUT, LPWAVEHDR, UINT);
typedef MMRESULT (WINAPI *waveOutResetFunc)(HWAVEOUT);
typedef MMRESULT (WINAPI *waveOutCloseFunc)(HWAVEOUT);

static waveOutOpenFunc            g_waveOutOpenOrig = nullptr;
static waveOutPrepareHeaderFunc   g_waveOutPrepareHeaderOrig = nullptr;
static waveOutWriteFunc           g_waveOutWriteOrig = nullptr;
static waveOutUnprepareHeaderFunc g_waveOutUnprepareHeaderOrig = nullptr;
static waveOutResetFunc           g_waveOutResetOrig = nullptr;
static waveOutCloseFunc           g_waveOutCloseOrig = nullptr;

// ------------------------------------------------------------
// Stream queue items
// ------------------------------------------------------------
struct StreamItem {
	int type = BL_ITEM_NONE;
	int value = 0;
	uint32_t gen = 0;
	std::vector<uint8_t> data;
	size_t offset = 0;

	StreamItem() = default;
	StreamItem(int t, int v, uint32_t g) : type(t), value(v), gen(g), offset(0) {}
};

// ------------------------------------------------------------
// Command queue
// ------------------------------------------------------------
struct Cmd {
	enum Type { CMD_SPEAK, CMD_QUIT } type = CMD_SPEAK;
	uint32_t cancelSnapshot = 0;
	std::wstring text;
	bool noIntonation = false;
};

struct BL_STATE {
	// DLL + exports
	HMODULE ttsModule = nullptr;

	TTS_InitFunc     ttsInit = nullptr;
	TTS_StartSayWFunc ttsStartSayW = nullptr;
	TTS_StartSayNoIntonationWFunc ttsStartSayNoIntonationW = nullptr;
	TTS_StopFunc     ttsStop = nullptr;

	TTS_GetIntFunc   ttsGetTempo = nullptr;
	TTS_SetIntFunc   ttsSetTempo = nullptr;
	TTS_GetIntFunc   ttsGetPitch = nullptr;
	TTS_SetIntFunc   ttsSetPitch = nullptr;
	TTS_GetIntFunc   ttsGetVolume = nullptr;
	TTS_SetIntFunc   ttsSetVolume = nullptr;

	// Serialize calls into tts.dll (worker thread will call most of them)
	std::mutex ttsMtx;

	// waveOutOpen capture
	WAVEFORMATEX lastFormat = {};
	bool formatValid = false;

	DWORD callbackType = 0;
	DWORD_PTR callbackTarget = 0;
	DWORD_PTR callbackInstance = 0;

	// done event signaled by Brailab callback
	HANDLE doneEvent = nullptr;

	// stop event signaled by bl_stop (lets hook/worker abort waits quickly)
	HANDLE stopEvent = nullptr;

	// Cancel + generations
	std::atomic<uint32_t> cancelToken{ 1 };
	std::atomic<uint32_t> genCounter{ 1 };
	std::atomic<uint32_t> activeGen{ 0 };   // hooks capture only while nonzero
	std::atomic<uint32_t> currentGen{ 0 };  // reader consumes only this gen

	// Output pacing data
	std::atomic<uint64_t> bytesPerSec{ 0 };
	std::atomic<ULONGLONG> lastAudioTick{ 0 };

	// Warmup credit: allow the first N ms of audio to be generated without sleeping.
	std::atomic<int> throttleCreditMs{ 0 };

	// Desired settings (setters store these; worker applies them before StartSay)
	std::atomic<int> desiredTempo{ 0 };
	std::atomic<int> desiredPitch{ 0 };
	std::atomic<int> desiredVolume{ 0 };

	// Worker
	std::mutex cmdMtx;
	std::condition_variable cmdCv;
	std::deque<Cmd> cmdQ;
	bool quitting = false;
	std::thread worker;

	// Output queue
	std::mutex outMtx;
	std::deque<StreamItem> outQ;
	size_t queuedAudioBytes = 0;

	size_t maxBufferedBytes = 0; // computed from format, else default
	size_t maxQueueItems = 8192;
};

static BL_STATE* g_state = nullptr;

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------
static bool isCallerFromModule(HMODULE expectedModule) {
	if (!expectedModule) return false;
	void* ra = _ReturnAddress();
	HMODULE caller = nullptr;
	if (!GetModuleHandleExW(
		GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
		reinterpret_cast<LPCWSTR>(ra),
		&caller
	)) {
		return false;
	}
	return caller == expectedModule;
}

static void signalWaveOutMessage(BL_STATE* s, UINT msg, WAVEHDR* hdr) {
	if (!s) return;

	const DWORD cbType = (s->callbackType & CALLBACK_TYPEMASK);

	if (cbType == CALLBACK_FUNCTION) {
		typedef void (CALLBACK *WaveOutProc)(HWAVEOUT, UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR);
		WaveOutProc proc = reinterpret_cast<WaveOutProc>(s->callbackTarget);
		if (proc) {
			proc(reinterpret_cast<HWAVEOUT>(s), msg, s->callbackInstance,
				reinterpret_cast<DWORD_PTR>(hdr), 0);
		}
		return;
	}

	if (cbType == CALLBACK_WINDOW) {
		HWND hwnd = reinterpret_cast<HWND>(s->callbackTarget);
		if (!hwnd) return;
		UINT mmMsg = 0;
		if (msg == WOM_OPEN) mmMsg = MM_WOM_OPEN;
		else if (msg == WOM_CLOSE) mmMsg = MM_WOM_CLOSE;
		else if (msg == WOM_DONE) mmMsg = MM_WOM_DONE;
		if (mmMsg) PostMessageW(hwnd, mmMsg, reinterpret_cast<WPARAM>(s), reinterpret_cast<LPARAM>(hdr));
		return;
	}

	if (cbType == CALLBACK_THREAD) {
		DWORD tid = static_cast<DWORD>(s->callbackTarget);
		UINT mmMsg = 0;
		if (msg == WOM_OPEN) mmMsg = MM_WOM_OPEN;
		else if (msg == WOM_CLOSE) mmMsg = MM_WOM_CLOSE;
		else if (msg == WOM_DONE) mmMsg = MM_WOM_DONE;
		if (mmMsg && tid) PostThreadMessageW(tid, mmMsg, reinterpret_cast<WPARAM>(s), reinterpret_cast<LPARAM>(hdr));
		return;
	}

	if (cbType == CALLBACK_EVENT) {
		HANDLE ev = reinterpret_cast<HANDLE>(s->callbackTarget);
		if (ev) SetEvent(ev);
		return;
	}
}

static void clearOutputQueueLocked(BL_STATE* s) {
	s->outQ.clear();
	s->queuedAudioBytes = 0;
}

static void computeBufferLimits(BL_STATE* s) {
	// Make buffer large enough that we NEVER drop during normal speech.
	// Since we now pace generation, this won't grow fast anyway.
	uint64_t bps = s->bytesPerSec.load(std::memory_order_relaxed);
	if (bps == 0) bps = 22050; // safe-ish default (11025 Hz mono 16-bit)

	// Allow up to 30 seconds buffered (still tiny in memory for 11025 mono).
	uint64_t bytes = bps * 30ULL;

	if (bytes < 256ULL * 1024ULL) bytes = 256ULL * 1024ULL;
	if (bytes > 8ULL * 1024ULL * 1024ULL) bytes = 8ULL * 1024ULL * 1024ULL;

	s->maxBufferedBytes = (size_t)bytes;
}

// UTF-16 -> CP1250 bytes (replace) -> UTF-16, then cleanup.
// Replace '?' with space.
static std::wstring sanitizeForBrailab(const wchar_t* in) {
	if (!in) return L"";

	BOOL usedDefault = FALSE;
	int blen = WideCharToMultiByte(
		1250,
		WC_NO_BEST_FIT_CHARS,
		in,
		-1,
		nullptr,
		0,
		"?",
		&usedDefault
	);
	if (blen <= 0) return L"";

	std::string bytes;
	bytes.resize((size_t)blen);
	WideCharToMultiByte(
		1250,
		WC_NO_BEST_FIT_CHARS,
		in,
		-1,
		&bytes[0],
		blen,
		"?",
		&usedDefault
	);

	int wlen = MultiByteToWideChar(1250, 0, bytes.c_str(), -1, nullptr, 0);
	if (wlen <= 0) return L"";

	std::wstring out;
	out.resize((size_t)wlen);
	MultiByteToWideChar(1250, 0, bytes.c_str(), -1, &out[0], wlen);

	if (!out.empty() && out.back() == L'\0') out.pop_back();

	for (auto& ch : out) {
		if ((ch < 0x20 && ch != L'\r' && ch != L'\n' && ch != L'\t') || (ch >= 0x7F && ch <= 0x9F)) {
			ch = L' ';
		}
		if (ch == 0x00A0) ch = L' ';
		if (ch == L'?') ch = L' ';
	}

	// collapse whitespace
	std::wstring collapsed;
	collapsed.reserve(out.size());
	bool prevSpace = true;
	for (wchar_t ch : out) {
		const bool isSpace = (ch == L' ' || ch == L'\t' || ch == L'\r' || ch == L'\n');
		if (isSpace) {
			if (!prevSpace) collapsed.push_back(L' ');
			prevSpace = true;
		} else {
			collapsed.push_back(ch);
			prevSpace = false;
		}
	}
	while (!collapsed.empty() && collapsed.back() == L' ') collapsed.pop_back();
	return collapsed;
}

static void enqueueAudioFromHook(BL_STATE* s, uint32_t gen, const void* data, size_t size) {
	if (!s || !data || size == 0) return;

	std::vector<uint8_t> copied(size);
	std::memcpy(copied.data(), data, size);

	s->lastAudioTick.store(GetTickCount64(), std::memory_order_relaxed);

	std::lock_guard<std::mutex> g(s->outMtx);

	const uint32_t curGen = s->currentGen.load(std::memory_order_relaxed);
	if (curGen == 0 || gen != curGen) return;

	const size_t limit = (s->maxBufferedBytes > 0) ? s->maxBufferedBytes : (size_t)(512 * 1024);

	auto dropOneAudio = [&]() -> bool {
		for (auto it = s->outQ.begin(); it != s->outQ.end(); ++it) {
			if (it->type == BL_ITEM_AUDIO) {
				size_t remaining = 0;
				if (it->data.size() > it->offset) remaining = it->data.size() - it->offset;
				if (s->queuedAudioBytes >= remaining) s->queuedAudioBytes -= remaining;
				else s->queuedAudioBytes = 0;
				s->outQ.erase(it);
				return true;
			}
		}
		return false;
	};

	// Avoid unbounded growth if consumer stalls for a long time.
	while ((s->queuedAudioBytes + copied.size() > limit) || (s->outQ.size() >= s->maxQueueItems)) {
		if (!dropOneAudio()) return;
	}

	StreamItem it(BL_ITEM_AUDIO, 0, gen);
	it.data = std::move(copied);
	it.offset = 0;

	s->queuedAudioBytes += it.data.size();
	s->outQ.push_back(std::move(it));
}

static void pushMarker(BL_STATE* s, int type, int value, uint32_t gen) {
	std::lock_guard<std::mutex> g(s->outMtx);
	const uint32_t curGen = s->currentGen.load(std::memory_order_relaxed);
	if (curGen == 0 || gen != curGen) return;
	s->outQ.push_back(StreamItem(type, value, gen));
}

static void __stdcall brailabDoneCallback() {
	BL_STATE* s = g_state;
	if (s && s->doneEvent) SetEvent(s->doneEvent);
}

// ------------------------------------------------------------
// Hooks
// ------------------------------------------------------------
static MMRESULT WINAPI hook_waveOutOpen(
	LPHWAVEOUT phwo,
	UINT uDeviceID,
	LPCWAVEFORMATEX pwfx,
	DWORD_PTR dwCallback,
	DWORD_PTR dwInstance,
	DWORD fdwOpen
) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutOpenOrig ? g_waveOutOpenOrig(phwo, uDeviceID, pwfx, dwCallback, dwInstance, fdwOpen)
			: MMSYSERR_ERROR;
	}

	if (phwo) *phwo = reinterpret_cast<HWAVEOUT>(s);

	if (pwfx) {
		s->lastFormat = *pwfx;
		s->formatValid = true;

		uint64_t bps = 0;
		if (pwfx->nAvgBytesPerSec) bps = (uint64_t)pwfx->nAvgBytesPerSec;
		if (!bps && pwfx->nSamplesPerSec && pwfx->nBlockAlign) bps = (uint64_t)pwfx->nSamplesPerSec * (uint64_t)pwfx->nBlockAlign;
		if (!bps) bps = 22050;
		s->bytesPerSec.store(bps, std::memory_order_relaxed);

		computeBufferLimits(s);
	}

	s->callbackType = fdwOpen;
	s->callbackTarget = dwCallback;
	s->callbackInstance = dwInstance;

	signalWaveOutMessage(s, WOM_OPEN, nullptr);
	return MMSYSERR_NOERROR;
}

static MMRESULT WINAPI hook_waveOutPrepareHeader(HWAVEOUT hwo, LPWAVEHDR pwh, UINT cbwh) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutPrepareHeaderOrig ? g_waveOutPrepareHeaderOrig(hwo, pwh, cbwh) : MMSYSERR_ERROR;
	}
	if (pwh) pwh->dwFlags |= WHDR_PREPARED;
	return MMSYSERR_NOERROR;
}

static MMRESULT WINAPI hook_waveOutUnprepareHeader(HWAVEOUT hwo, LPWAVEHDR pwh, UINT cbwh) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutUnprepareHeaderOrig ? g_waveOutUnprepareHeaderOrig(hwo, pwh, cbwh) : MMSYSERR_ERROR;
	}
	if (pwh) pwh->dwFlags &= ~WHDR_PREPARED;
	return MMSYSERR_NOERROR;
}

static MMRESULT WINAPI hook_waveOutWrite(HWAVEOUT hwo, LPWAVEHDR pwh, UINT cbwh) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutWriteOrig ? g_waveOutWriteOrig(hwo, pwh, cbwh) : MMSYSERR_ERROR;
	}

	if (!pwh) return MMSYSERR_INVALPARAM;

	const uint32_t gen = s->activeGen.load(std::memory_order_relaxed);
	const uint32_t curGen = s->currentGen.load(std::memory_order_relaxed);

	const bool capturing = (gen != 0 && gen == curGen);

	if (capturing && pwh->lpData && pwh->dwBufferLength > 0) {
		enqueueAudioFromHook(s, gen, pwh->lpData, (size_t)pwh->dwBufferLength);
	}

	// If we are not capturing (e.g. canceled), don't throttle; finish immediately.
	if (!capturing) {
		pwh->dwFlags |= WHDR_DONE;
		signalWaveOutMessage(s, WOM_DONE, pwh);
		return MMSYSERR_NOERROR;
	}

	// Throttle so Brailab can't synthesize miles ahead of real time.
	uint64_t bps = s->bytesPerSec.load(std::memory_order_relaxed);
	if (bps == 0) bps = 22050;

	uint32_t bufMs = (uint32_t)(((uint64_t)pwh->dwBufferLength * 1000ULL) / bps);
	if (bufMs > 500) bufMs = 500; // sanity cap per buffer

	// Warmup credit: allow first ~200ms to go through without sleeping (helps instant start).
	uint32_t sleepMs = bufMs;
	if (bufMs > 0) {
		int credit = s->throttleCreditMs.load(std::memory_order_relaxed);
		while (credit > 0) {
			int use = (credit < (int)bufMs) ? credit : (int)bufMs;
			int expected = credit;
			if (s->throttleCreditMs.compare_exchange_weak(expected, credit - use, std::memory_order_relaxed)) {
				sleepMs = bufMs - (uint32_t)use;
				break;
			}
			credit = s->throttleCreditMs.load(std::memory_order_relaxed);
		}
	}

	if (sleepMs > 0) {
		ULONGLONG end = GetTickCount64() + (ULONGLONG)sleepMs;
		while (true) {
			// abort early if canceled
			if (s->activeGen.load(std::memory_order_relaxed) != curGen) break;

			DWORD nowWait = 0;
			ULONGLONG now = GetTickCount64();
			if (now >= end) break;

			ULONGLONG remain = end - now;
			nowWait = (remain > 5) ? 5 : (DWORD)remain;

			// wait on stopEvent so cancel is immediate
			DWORD w = WaitForSingleObject(s->stopEvent, nowWait);
			if (w == WAIT_OBJECT_0) break;
		}
	}

	pwh->dwFlags |= WHDR_DONE;
	signalWaveOutMessage(s, WOM_DONE, pwh);
	return MMSYSERR_NOERROR;
}

static MMRESULT WINAPI hook_waveOutReset(HWAVEOUT hwo) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutResetOrig ? g_waveOutResetOrig(hwo) : MMSYSERR_ERROR;
	}
	return MMSYSERR_NOERROR;
}

static MMRESULT WINAPI hook_waveOutClose(HWAVEOUT hwo) {
	BL_STATE* s = g_state;
	if (!s || !s->ttsModule || !isCallerFromModule(s->ttsModule)) {
		return g_waveOutCloseOrig ? g_waveOutCloseOrig(hwo) : MMSYSERR_ERROR;
	}
	signalWaveOutMessage(s, WOM_CLOSE, nullptr);
	return MMSYSERR_NOERROR;
}

static void ensureHooksInstalled() {
	static LONG once = 0;
	if (InterlockedCompareExchange(&once, 1, 0) != 0) return;

	MH_STATUS st = MH_Initialize();
	if (st != MH_OK && st != MH_ERROR_ALREADY_INITIALIZED) return;

	MH_CreateHookApi(L"winmm.dll", "waveOutOpen", (LPVOID)hook_waveOutOpen, (LPVOID*)&g_waveOutOpenOrig);
	MH_CreateHookApi(L"winmm.dll", "waveOutPrepareHeader", (LPVOID)hook_waveOutPrepareHeader, (LPVOID*)&g_waveOutPrepareHeaderOrig);
	MH_CreateHookApi(L"winmm.dll", "waveOutUnprepareHeader", (LPVOID)hook_waveOutUnprepareHeader, (LPVOID*)&g_waveOutUnprepareHeaderOrig);
	MH_CreateHookApi(L"winmm.dll", "waveOutWrite", (LPVOID)hook_waveOutWrite, (LPVOID*)&g_waveOutWriteOrig);
	MH_CreateHookApi(L"winmm.dll", "waveOutReset", (LPVOID)hook_waveOutReset, (LPVOID*)&g_waveOutResetOrig);
	MH_CreateHookApi(L"winmm.dll", "waveOutClose", (LPVOID)hook_waveOutClose, (LPVOID*)&g_waveOutCloseOrig);

	MH_EnableHook(MH_ALL_HOOKS);
}

// ------------------------------------------------------------
// Worker loop
// ------------------------------------------------------------
static void workerLoop(BL_STATE* s) {
	if (!s) return;

	// Make worker responsive
	SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_ABOVE_NORMAL);

	while (true) {
		Cmd cmd;

		{
			std::unique_lock<std::mutex> lk(s->cmdMtx);
			s->cmdCv.wait(lk, [&]() { return s->quitting || !s->cmdQ.empty(); });
			if (s->quitting) return;

			cmd = std::move(s->cmdQ.front());
			s->cmdQ.pop_front();
		}

		if (cmd.type == Cmd::CMD_QUIT) return;

		const uint32_t snap = s->cancelToken.load(std::memory_order_relaxed);
		if (cmd.cancelSnapshot != snap) continue;

		const uint32_t gen = s->genCounter.fetch_add(1, std::memory_order_relaxed);

		// reset events for this utterance
		ResetEvent(s->stopEvent);
		ResetEvent(s->doneEvent);

		// allow first 200ms to generate without sleeping (helps instant start)
		s->throttleCreditMs.store(200, std::memory_order_relaxed);

		// gate on
		s->currentGen.store(gen, std::memory_order_relaxed);
		s->activeGen.store(gen, std::memory_order_relaxed);
		s->lastAudioTick.store(0, std::memory_order_relaxed);

		// clear output
		{
			std::lock_guard<std::mutex> g(s->outMtx);
			clearOutputQueueLocked(s);
		}

		std::wstring safe = sanitizeForBrailab(cmd.text.c_str());
		if (safe.empty()) {
			s->activeGen.store(0, std::memory_order_relaxed);
			pushMarker(s, BL_ITEM_DONE, 0, gen);
			continue;
		}

		// Apply settings ON THIS THREAD (fixes TLS/thread-affinity engines).
		{
			std::lock_guard<std::mutex> tg(s->ttsMtx);
			seh_ttsSetInt(s->ttsSetTempo, s->desiredTempo.load(std::memory_order_relaxed));
			seh_ttsSetInt(s->ttsSetPitch, s->desiredPitch.load(std::memory_order_relaxed));
			seh_ttsSetInt(s->ttsSetVolume, s->desiredVolume.load(std::memory_order_relaxed));
		}

		// Start speech (SEH safe)
		int startOk = 0;
		{
			std::lock_guard<std::mutex> tg(s->ttsMtx);
			if (cmd.noIntonation && s->ttsStartSayNoIntonationW) {
				startOk = seh_ttsStartSayNoIntW(s->ttsStartSayNoIntonationW, safe.c_str());
			} else {
				startOk = seh_ttsStartSayW(s->ttsStartSayW, safe.c_str());
			}
		}

		if (!startOk) {
			s->activeGen.store(0, std::memory_order_relaxed);
			pushMarker(s, BL_ITEM_ERROR, 1001, gen);
			pushMarker(s, BL_ITEM_DONE, 0, gen);
			continue;
		}

		// Wait for done or stop/cancel, with watchdog
		const auto t0 = std::chrono::steady_clock::now();
		const auto maxDur = std::chrono::seconds(180);

		HANDLE waits[2] = { s->doneEvent, s->stopEvent };

		bool stopped = false;
		while (true) {
			DWORD w = WaitForMultipleObjects(2, waits, FALSE, 50);

			if (w == WAIT_OBJECT_0) {
				// doneEvent
				break;
			}
			if (w == WAIT_OBJECT_0 + 1) {
				stopped = true;
				break;
			}

			if (s->cancelToken.load(std::memory_order_relaxed) != snap) {
				stopped = true;
				break;
			}

			if (std::chrono::steady_clock::now() - t0 > maxDur) {
				pushMarker(s, BL_ITEM_ERROR, 1002, gen);
				stopped = true;
				break;
			}
		}

		if (stopped) {
			// Stop inside worker thread (again: TLS-safe)
			{
				std::lock_guard<std::mutex> tg(s->ttsMtx);
				seh_ttsStop(s->ttsStop);
			}
			s->activeGen.store(0, std::memory_order_relaxed);
			// we still emit DONE so the reader doesn’t wait forever
			pushMarker(s, BL_ITEM_DONE, 0, gen);
			continue;
		}

		// Small tail-grace: wait until no new audio has arrived for ~30ms (max 250ms)
		ULONGLONG graceStart = GetTickCount64();
		while (true) {
			ULONGLONG last = s->lastAudioTick.load(std::memory_order_relaxed);
			ULONGLONG now = GetTickCount64();

			if (last != 0 && (now - last) >= 30) break;
			if ((now - graceStart) >= 250) break;

			// allow cancel
			if (WaitForSingleObject(s->stopEvent, 5) == WAIT_OBJECT_0) break;
		}

		// gate off BEFORE DONE marker so no audio appears after DONE
		s->activeGen.store(0, std::memory_order_relaxed);

		pushMarker(s, BL_ITEM_DONE, 0, gen);
	}
}

// ------------------------------------------------------------
// Exports
// ------------------------------------------------------------
extern "C" BL_API BL_STATE* __cdecl bl_initW(const wchar_t* ttsDllPath, int initValue) {
	if (!ttsDllPath) return nullptr;
	if (g_state) return nullptr;

	HMODULE mod = LoadLibraryW(ttsDllPath);
	if (!mod) return nullptr;

	auto* s = new BL_STATE();
	s->ttsModule = mod;

	s->ttsInit = (TTS_InitFunc)GetProcAddress(mod, "TTS_Init");
	s->ttsStartSayW = (TTS_StartSayWFunc)GetProcAddress(mod, "TTS_StartSay");
	s->ttsStartSayNoIntonationW = (TTS_StartSayNoIntonationWFunc)GetProcAddress(mod, "TTS_StartSayWithNoIntonation");
	s->ttsStop = (TTS_StopFunc)GetProcAddress(mod, "TTS_Stop");

	s->ttsGetTempo = (TTS_GetIntFunc)GetProcAddress(mod, "TTS_GetTempo");
	s->ttsSetTempo = (TTS_SetIntFunc)GetProcAddress(mod, "TTS_SetTempo");
	s->ttsGetPitch = (TTS_GetIntFunc)GetProcAddress(mod, "TTS_GetPitch");
	s->ttsSetPitch = (TTS_SetIntFunc)GetProcAddress(mod, "TTS_SetPitch");
	s->ttsGetVolume = (TTS_GetIntFunc)GetProcAddress(mod, "TTS_GetVolume");
	s->ttsSetVolume = (TTS_SetIntFunc)GetProcAddress(mod, "TTS_SetVolume");

	s->doneEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
	s->stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);

	if (!s->doneEvent || !s->stopEvent || !s->ttsInit || !s->ttsStartSayW || !s->ttsStop) {
		if (s->doneEvent) CloseHandle(s->doneEvent);
		if (s->stopEvent) CloseHandle(s->stopEvent);
		FreeLibrary(mod);
		delete s;
		return nullptr;
	}

	g_state = s;
	ensureHooksInstalled();

	{
		std::lock_guard<std::mutex> tg(s->ttsMtx);
		if (!seh_ttsInit(s->ttsInit, initValue, brailabDoneCallback)) {
			g_state = nullptr;
			CloseHandle(s->doneEvent);
			CloseHandle(s->stopEvent);
			FreeLibrary(mod);
			delete s;
			return nullptr;
		}
	}

	// Initialize desired settings from DLL if possible (defaults otherwise)
	{
		std::lock_guard<std::mutex> tg(s->ttsMtx);
		int v = 0;
		if (seh_ttsGetInt(s->ttsGetTempo, &v)) s->desiredTempo.store(v, std::memory_order_relaxed);
		if (seh_ttsGetInt(s->ttsGetPitch, &v)) s->desiredPitch.store(v, std::memory_order_relaxed);
		if (seh_ttsGetInt(s->ttsGetVolume, &v)) s->desiredVolume.store(v, std::memory_order_relaxed);
	}

	// Defaults for pacing if format unknown initially
	s->bytesPerSec.store(22050, std::memory_order_relaxed);
	computeBufferLimits(s);

	s->worker = std::thread(workerLoop, s);
	return s;
}

extern "C" BL_API void __cdecl bl_free(BL_STATE* s) {
	if (!s) return;

	// cancel + wake everything
	s->cancelToken.fetch_add(1, std::memory_order_relaxed);
	SetEvent(s->stopEvent);
	SetEvent(s->doneEvent);

	s->activeGen.store(0, std::memory_order_relaxed);
	s->currentGen.store(0, std::memory_order_relaxed);

	{
		std::lock_guard<std::mutex> lk(s->cmdMtx);
		s->quitting = true;
		s->cmdQ.clear();
	}
	s->cmdCv.notify_all();
	if (s->worker.joinable()) s->worker.join();

	{
		std::lock_guard<std::mutex> tg(s->ttsMtx);
		seh_ttsStop(s->ttsStop);
	}

	{
		std::lock_guard<std::mutex> g(s->outMtx);
		clearOutputQueueLocked(s);
	}

	if (s->doneEvent) CloseHandle(s->doneEvent);
	if (s->stopEvent) CloseHandle(s->stopEvent);
	if (s->ttsModule) FreeLibrary(s->ttsModule);

	if (g_state == s) g_state = nullptr;
	delete s;
}

extern "C" BL_API void __cdecl bl_stop(BL_STATE* s) {
	if (!s) return;

	s->cancelToken.fetch_add(1, std::memory_order_relaxed);

	// gate off and clear queue
	s->activeGen.store(0, std::memory_order_relaxed);
	s->currentGen.store(0, std::memory_order_relaxed);

	{
		std::lock_guard<std::mutex> g(s->outMtx);
		clearOutputQueueLocked(s);
	}

	// wake worker + hook throttles
	SetEvent(s->stopEvent);
	SetEvent(s->doneEvent);
}

extern "C" BL_API int __cdecl bl_startSpeakW(BL_STATE* s, const wchar_t* text, int noIntonation) {
	if (!s || !text) return 1;

	Cmd cmd;
	cmd.type = Cmd::CMD_SPEAK;
	cmd.cancelSnapshot = s->cancelToken.load(std::memory_order_relaxed);
	cmd.text = text;
	cmd.noIntonation = (noIntonation != 0);

	{
		std::lock_guard<std::mutex> lk(s->cmdMtx);
		s->cmdQ.push_back(std::move(cmd));
	}
	s->cmdCv.notify_one();
	return 0;
}

extern "C" BL_API int __cdecl bl_read(BL_STATE* s, int* outType, int* outValue, uint8_t* outAudio, int outCap) {
	if (outType) *outType = BL_ITEM_NONE;
	if (outValue) *outValue = 0;
	if (!s || !outAudio || outCap < 0) return 0;

	std::lock_guard<std::mutex> g(s->outMtx);

	const uint32_t curGen = s->currentGen.load(std::memory_order_relaxed);
	if (curGen == 0) {
		clearOutputQueueLocked(s);
		return 0;
	}

	// drop stale items
	while (!s->outQ.empty() && s->outQ.front().gen != curGen) {
		StreamItem& it = s->outQ.front();
		if (it.type == BL_ITEM_AUDIO) {
			size_t remaining = (it.data.size() > it.offset) ? (it.data.size() - it.offset) : 0;
			if (s->queuedAudioBytes >= remaining) s->queuedAudioBytes -= remaining;
			else s->queuedAudioBytes = 0;
		}
		s->outQ.pop_front();
	}

	if (s->outQ.empty()) return 0;

	StreamItem& front = s->outQ.front();
	if (outType) *outType = front.type;
	if (outValue) *outValue = front.value;

	if (front.type == BL_ITEM_AUDIO) {
		size_t remainingSz = (front.data.size() > front.offset) ? (front.data.size() - front.offset) : 0;
		int remaining = (remainingSz > (size_t)INT_MAX) ? INT_MAX : (int)remainingSz;
		int n = remaining;
		if (n > outCap) n = outCap;

		if (n > 0) {
			std::memcpy(outAudio, front.data.data() + front.offset, (size_t)n);
			front.offset += (size_t)n;

			if (s->queuedAudioBytes >= (size_t)n) s->queuedAudioBytes -= (size_t)n;
			else s->queuedAudioBytes = 0;
		}

		if (front.offset >= front.data.size()) {
			s->outQ.pop_front();
		}
		return n;
	}

	// DONE/ERROR
	s->outQ.pop_front();
	return 0;
}

// Settings API: store desired values; worker applies them.
extern "C" BL_API int __cdecl bl_getTempo(BL_STATE* s) {
	if (!s) return 0;
	return s->desiredTempo.load(std::memory_order_relaxed);
}
extern "C" BL_API void __cdecl bl_setTempo(BL_STATE* s, int tempo) {
	if (!s) return;
	s->desiredTempo.store(tempo, std::memory_order_relaxed);
}

extern "C" BL_API int __cdecl bl_getPitch(BL_STATE* s) {
	if (!s) return 0;
	return s->desiredPitch.load(std::memory_order_relaxed);
}
extern "C" BL_API void __cdecl bl_setPitch(BL_STATE* s, int pitch) {
	if (!s) return;
	s->desiredPitch.store(pitch, std::memory_order_relaxed);
}

extern "C" BL_API int __cdecl bl_getVolume(BL_STATE* s) {
	if (!s) return 0;
	return s->desiredVolume.load(std::memory_order_relaxed);
}
extern "C" BL_API void __cdecl bl_setVolume(BL_STATE* s, int volume) {
	if (!s) return;
	s->desiredVolume.store(volume, std::memory_order_relaxed);
}

extern "C" BL_API int __cdecl bl_getFormat(BL_STATE* s, int* sampleRate, int* channels, int* bitsPerSample) {
	if (!s || !s->formatValid) return 0;
	if (sampleRate) *sampleRate = (int)s->lastFormat.nSamplesPerSec;
	if (channels) *channels = (int)s->lastFormat.nChannels;
	if (bitsPerSample) *bitsPerSample = (int)s->lastFormat.wBitsPerSample;
	return 1;
}

BOOL APIENTRY DllMain(HMODULE, DWORD, LPVOID) {
	return TRUE;
}
