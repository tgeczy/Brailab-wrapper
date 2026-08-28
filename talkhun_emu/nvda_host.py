# -*- coding: utf-8 -*-
"""Streaming engine host for the emulated BraiLab NVDA driver.

NVDA's Python has no numpy/scipy/unicorn, so the driver spawns this as a
subprocess (a Python that does).  It loads the 1991 TALKHUN engine once, then
per line of stdin renders one utterance through chip_synth (the 10 kHz PCF8200
core) and writes it back as raw 16-bit PCM.

Protocol
--------
stdin : one UTF-8 JSON object per line, e.g.
        {"text": "szia", "furcsa": false, "time_scale": 0.63}
stdout: per utterance, 4-byte little-endian length N, then N bytes of
        signed-16-bit-LE mono PCM at 10 kHz.  N may be 0 (nothing to speak).
stderr: a single "READY\n" once the engine has booted; then diagnostics.
"""
import io
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Binary stdout: on Windows the console handle would otherwise translate
# \n -> \r\n and corrupt the PCM stream.
if os.name == 'nt':
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)

import numpy as np
from talkhun import load
import chip_synth

ESC = '\x1b'
OUT_SCALE = 20000.0     # float render -> int16; tuned so speech peaks near full scale
_stdout = sys.stdout.buffer
_stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')


def _write(pcm_bytes):
    _stdout.write(struct.pack('<I', len(pcm_bytes)))
    _stdout.write(pcm_bytes)
    _stdout.flush()


def main():
    try:
        eng = load()
    except Exception as e:
        sys.stderr.write('LOAD-FAILED %r\n' % (e,))
        sys.stderr.flush()
        return
    sys.stderr.write('READY\n')
    sys.stderr.flush()

    for line in _stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except Exception:
            _write(b'')
            continue
        text = cmd.get('text', '') or ''
        furcsa = bool(cmd.get('furcsa', False))
        ts = float(cmd.get('time_scale', 0.63))
        flat = bool(cmd.get('flat_pitch', False))
        try:
            eng.feed(ESC + ('F1' if furcsa else 'F0'))   # set/clear the weird voice
            seq = eng.capture(text)
            x = chip_synth.render_chip_fast(seq, time_scale=ts, flat_pitch=flat)
            if len(x):
                # Short raised-cosine fade in/out so the utterance doesn't start
                # or end on a non-zero sample -- that DAC step is the onset "pop".
                nf = min(len(x) // 2, 40)                 # 4 ms at 10 kHz
                if nf > 1:
                    w = np.sin(np.linspace(0.0, np.pi / 2.0, nf)) ** 2
                    x = x.copy()
                    x[:nf] *= w
                    x[-nf:] *= w[::-1]
                pcm = np.clip(x * OUT_SCALE, -32767, 32767).astype('<i2').tobytes()
            else:
                pcm = b''
        except Exception as e:
            sys.stderr.write('RENDER-ERROR %r\n' % (e,))
            sys.stderr.flush()
            pcm = b''
        _write(pcm)


if __name__ == '__main__':
    main()
