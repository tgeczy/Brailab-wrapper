// brailab_wrapper.h
#pragma once

#include <windows.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifdef BRAILAB_WRAPPER_EXPORTS
	#define BL_API __declspec(dllexport)
#else
	#define BL_API __declspec(dllimport)
#endif

// Stream item types (similar spirit to FVWRAP_ITEM_*).
#define BL_ITEM_NONE  0
#define BL_ITEM_AUDIO 1
#define BL_ITEM_DONE  2
#define BL_ITEM_ERROR 3

typedef struct BL_STATE BL_STATE;

// Create/init wrapper (installs hooks and calls TTS_Init).
// initValue: keep using 1500 like before.
BL_API BL_STATE* __cdecl bl_initW(const wchar_t* ttsDllPath, int initValue);

// Free wrapper and stop worker thread.
BL_API void __cdecl bl_free(BL_STATE* s);

// Stop current speech immediately and clear queued audio.
BL_API void __cdecl bl_stop(BL_STATE* s);

// Start speaking asynchronously.
// noIntonation: 0 => normal (intonation), 1 => no intonation (if available)
// Returns 0 on success, nonzero on failure.
BL_API int __cdecl bl_startSpeakW(BL_STATE* s, const wchar_t* text, int noIntonation);

// Read queued stream items.
// - outType/outValue are set even when returning 0 bytes.
// - For BL_ITEM_AUDIO: returns number of bytes copied into outAudio.
// - For DONE/ERROR: returns 0, outValue may hold error code for ERROR.
// - If no items are available: outType=BL_ITEM_NONE, return 0.
BL_API int __cdecl bl_read(BL_STATE* s, int* outType, int* outValue, uint8_t* outAudio, int outCap);

// Settings passthrough (Brailab DLL uses its own integer ranges)
BL_API int  __cdecl bl_getTempo(BL_STATE* s);
BL_API void __cdecl bl_setTempo(BL_STATE* s, int tempo);

BL_API int  __cdecl bl_getPitch(BL_STATE* s);
BL_API void __cdecl bl_setPitch(BL_STATE* s, int pitch);

BL_API int  __cdecl bl_getVolume(BL_STATE* s);
BL_API void __cdecl bl_setVolume(BL_STATE* s, int volume);

// Last wave format seen in waveOutOpen.
// Returns 1 if known, else 0.
BL_API int __cdecl bl_getFormat(BL_STATE* s, int* sampleRate, int* channels, int* bitsPerSample);

#ifdef __cplusplus
}
#endif
