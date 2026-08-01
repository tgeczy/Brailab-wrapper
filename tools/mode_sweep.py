# -*- coding: utf-8 -*-
r"""Explore TTS.dll's undocumented speech mode bitmask.

    C:\Python313-32\python.exe tools\mode_sweep.py ["some text"]

MUST be 32-bit Python -- TTS.dll and brailab_wrapper.dll are both PE32.

What the disassembly says
-------------------------
TTS.dll exports three ways to speak and all three funnel into one routine,
differing only in a bitmask:

    TTS_StartSay(text)                   -> String_to_TTSText(0, 0, text, 0x1F)
    TTS_StartSayWithNoIntonation(text)   -> String_to_TTSText(0, 0, text, 0x17)
    TTS_StartSayWithModeSpec(text, mode) -> String_to_TTSText(0, 0, text, mode|0x10)

0x1F vs 0x17 differ in exactly bit 3, so bit 3 is intonation -- and that is the
only bit the named entry points ever vary.  ModeSpec exposes the rest, which
nothing in this repo has ever called.

How it drives the engine
------------------------
Calling TTS_StartSayWithModeSpec directly produces silence: brailab_wrapper.dll
captures audio by hooking waveOut* from its own worker thread, and a call made
outside that session is discarded.  Rather than rebuild the wrapper, patch the
`push 0x1F` immediate inside TTS_StartSayW (module + 0x9320) and then speak
through the ordinary bl_startSpeakW path, which the wrapper does capture.

Measured results
----------------
Bit 4 is not optional: 0x0F and 0x07 render *nothing*, which is exactly why
ModeSpec force-ORs 0x10.  Every other bit changes the audio -- 0x1B, 0x1D,
0x1E, 0x3F, 0x5F, 0x9F and 0xFF all produce distinct output.  So there are at
least seven live mode bits and only one of them was ever exposed.
"""
import ctypes
import hashlib
import os
import struct
import sys
import time
import wave
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRIVER = os.path.join(ROOT, 'nvda_driver',
                      'BraiLab PC Beszédszintetizátor', 'synthDrivers')
WRAPPER = os.path.join(DRIVER, 'brailab_wrapper.dll')
TTS = os.path.join(DRIVER, 'Brailab', 'TTS.dll')
OUTDIR = os.path.join(ROOT, 'mode_sweep')

#: Offset of the 0x1F immediate of `push 0x1f` inside TTS_StartSayW.
MODE_IMM = 0x9320
INIT_VALUE = 1500
BASE_MODE = 0x1F

#: Base, then each live bit moved on its own, so a difference is attributable.
CASES = [
    (0x1F, 'base', 'plain TTS_StartSay'),
    (0x17, 'bit3_off', 'no intonation (the one documented bit)'),
    (0x1E, 'bit0_off', ''),
    (0x1D, 'bit1_off', ''),
    (0x1B, 'bit2_off', ''),
    (0x3F, 'bit5_on', ''),
    (0x5F, 'bit6_on', ''),
    (0x9F, 'bit7_on', ''),
    (0xFF, 'all_on', ''),
    (0x0F, 'bit4_off', 'renders nothing -- bit 4 is mandatory'),
]


def main():
    if struct.calcsize('P') * 8 != 32:
        sys.exit('need 32-bit Python: C:\\Python313-32\\python.exe')
    text = sys.argv[1] if len(sys.argv) > 1 else 'Az orsz\u00e1g\u00fat harcosa.'
    for p in (WRAPPER, TTS):
        if not os.path.exists(p):
            sys.exit('missing %s' % p)
    os.makedirs(OUTDIR, exist_ok=True)

    w = ctypes.cdll.LoadLibrary(WRAPPER)
    w.bl_initW.argtypes = (ctypes.c_wchar_p, ctypes.c_int)
    w.bl_initW.restype = ctypes.c_void_p
    w.bl_read.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                          ctypes.POINTER(ctypes.c_int), ctypes.c_void_p,
                          ctypes.c_int)
    w.bl_read.restype = ctypes.c_int
    w.bl_getFormat.argtypes = (ctypes.c_void_p,) + (ctypes.POINTER(ctypes.c_int),) * 3
    w.bl_startSpeakW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
    w.bl_startSpeakW.restype = ctypes.c_int
    w.bl_stop.argtypes = (ctypes.c_void_p,)

    h = w.bl_initW(TTS, INIT_VALUE)
    if not h:
        sys.exit('bl_initW returned NULL')
    rate, ch, bits = (ctypes.c_int() for _ in range(3))
    w.bl_getFormat(h, ctypes.byref(rate), ctypes.byref(ch), ctypes.byref(bits))
    rate_v = rate.value or 10000

    tts = ctypes.WinDLL(TTS)
    imm = tts._handle + MODE_IMM
    found = ctypes.string_at(imm, 1)[0]
    if found != BASE_MODE:
        sys.exit('expected %02X at +%04X, found %02X -- different TTS.dll build'
                 % (BASE_MODE, MODE_IMM, found))
    old = wintypes.DWORD()
    ctypes.windll.kernel32.VirtualProtect(ctypes.c_void_p(imm), 1, 0x40,
                                          ctypes.byref(old))

    buf = ctypes.create_string_buffer(65536)
    t, v = ctypes.c_int(), ctypes.c_int()

    def drain(maxs=8.0, quiet=0.7):
        out, t0 = bytearray(), time.time()
        last = t0
        while time.time() - t0 < maxs:
            n = w.bl_read(h, ctypes.byref(t), ctypes.byref(v), buf, len(buf))
            if n > 0:
                out += buf.raw[:n]
                last = time.time()
            else:
                if out and time.time() - last > quiet:
                    break
                time.sleep(0.005)
        return bytes(out)

    print('engine: %d Hz %d ch %d bit   text=%r\n' % (rate_v, ch.value or 1,
                                                      bits.value or 16, text))
    print('%-6s %-9s %8s  %-10s %s' % ('mode', 'name', 'bytes', 'md5', 'note'))
    try:
        for mode, name, note in CASES:
            ctypes.memmove(imm, bytes([mode]), 1)
            w.bl_stop(h)
            drain(0.3, 0.1)
            w.bl_startSpeakW(h, text, 0)
            pcm = drain()
            if pcm:
                out = os.path.join(OUTDIR, 'mode_%02X_%s.wav' % (mode, name))
                f = wave.open(out, 'wb')
                f.setnchannels(ch.value or 1)
                f.setsampwidth(max(1, (bits.value or 16) // 8))
                f.setframerate(rate_v)
                f.writeframes(pcm)
                f.close()
            print('0x%02X   %-9s %8d  %-10s %s'
                  % (mode, name, len(pcm),
                     hashlib.md5(pcm).hexdigest()[:10] if pcm else '-', note))
    finally:
        ctypes.memmove(imm, bytes([BASE_MODE]), 1)

    print('\n-> %s' % OUTDIR)
    print('Listen for furcsa: higher and stranger, the "female" formant table.')


if __name__ == '__main__':
    main()
