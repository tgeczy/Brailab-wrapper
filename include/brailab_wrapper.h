// brailab_wrapper.h (patched for composite utterances + index markers)
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

// Stream item types produced by bl_read().
#define BL_ITEM_NONE  0
#define BL_ITEM_AUDIO 1
#define BL_ITEM_DONE  2
#define BL_ITEM_ERROR 3
// New: index marker emitted inside a composite utterance stream.
#define BL_ITEM_INDEX 4

typedef struct BL_STATE BL_STATE;

// Initialize wrapper. Returns a state pointer or NULL on failure.
// - ttsDllPath: absolute or relative path to the Brailab speech DLL.
// - initValue: wrapper/engine-specific init parameter (kept for backward compatibility).
BL_API BL_STATE* __cdecl bl_initW(const wchar_t* ttsDllPath, int initValue);

// Free wrapper state.
BL_API void __cdecl bl_free(BL_STATE* s);

// Stop the current speech stream and clear pending output.
BL_API void __cdecl bl_stop(BL_STATE* s);

// Legacy API: speak one chunk (one wrapper "utterance").
// - noIntonation: engine-specific flag (kept as-is).
BL_API int __cdecl bl_startSpeakW(BL_STATE* s, const wchar_t* text, int noIntonation);

// New composite utterance API (FlexVoice-style):
// Build a single wrapper utterance made of multiple text chunks, with index markers.
// Typical flow:
//   bl_beginUtterance(s, noIntonation);
//   bl_addTextUtteranceW(s, L"...");
//   bl_addIndexUtterance(s, 12);
//   bl_addTextUtteranceW(s, L"...");
//   bl_commitUtterance(s);
BL_API int __cdecl bl_beginUtterance(BL_STATE* s, int noIntonation);
BL_API int __cdecl bl_addTextUtteranceW(BL_STATE* s, const wchar_t* text);
BL_API int __cdecl bl_addIndexUtterance(BL_STATE* s, int index);
BL_API int __cdecl bl_commitUtterance(BL_STATE* s);

// Read next item from the wrapper output queue.
//
// Outputs:
// - *outType receives one of BL_ITEM_*.
// - *outValue meaning depends on *outType:
//     * BL_ITEM_AUDIO: number of bytes copied into outAudio.
//     * BL_ITEM_INDEX: the index value.
//     * BL_ITEM_DONE: 0.
//     * BL_ITEM_ERROR: error code (wrapper-defined).
// - outAudio: buffer to receive audio bytes for BL_ITEM_AUDIO.
// - outCap: capacity of outAudio in bytes.
//
// Return value:
// - If an item was read: returns 1 (or >0).
// - If no items are available: sets *outType=BL_ITEM_NONE and returns 0.
BL_API int __cdecl bl_read(BL_STATE* s, int* outType, int* outValue, uint8_t* outAudio, int outCap);

// Voice controls.
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
