# -*- coding: utf-8 -*-
"""Speak text through the emulated 1991 talker and write a WAV.

    python speak.py "mama." out.wav
    python speak.py "Ez a BraiLab." out.wav --furcsa
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace')

import synth
from talkhun import load

ESC = '\x1b'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    text = args[0] if args else "mama."
    out = args[1] if len(args) > 1 else "out.wav"

    t = load()
    if '--furcsa' in flags:
        t.feed(ESC + 'F1')
    kw = {}
    for fl in flags:
        if fl.startswith('--speed='):
            t.feed(ESC + 'S' + fl.split('=')[1])
        if fl.startswith('--pitch='):
            t.feed(ESC + 'P' + chr(int(fl.split('=')[1])))
        if fl.startswith('--female-scale='):
            # How far up the female table shifts F1-F4. The real values are
            # lost, so this is the knob to calibrate furcsa by ear.
            kw['female_scale'] = float(fl.split('=')[1])
        if fl.startswith('--tilt='):
            # Source rolloff in Hz; "none" disables it. Lower = darker voice.
            v = fl.split('=')[1]
            kw['source_tilt'] = None if v == 'none' else float(v)
        if fl.startswith('--formants='):
            kw['nformants_override'] = int(fl.split('=')[1])
        if fl.startswith('--offset='):
            # Codec-to-table index offset: 1 = the old cross-dataset
            # calibration, 0 = codes index the MEA-8000 tables directly.
            kw['codec_offset'] = int(fl.split('=')[1])
        if fl == '--flat-pitch':
            kw['flat_pitch'] = True
        if fl.startswith('--ampl-compress='):
            kw['ampl_compress'] = float(fl.split('=')[1])
        if fl.startswith('--bw='):
            kw['bw_scale'] = float(fl.split('=')[1])
        if fl.startswith('--noise-gain='):
            # Fricative level relative to the voiced source.
            kw['noise_gain'] = float(fl.split('=')[1])

    seq = t.capture(text)
    frames = [v for k, v in seq if k == 'frame']
    pcm = synth.render(seq, **kw)
    synth.write_wav(out, pcm)
    print("%r -> %d frames -> %s (%.2f s, synthesized at %d Hz, written at %d Hz)"
          % (text, len(frames), out, len(pcm) / synth.SAMPLE_RATE,
             synth.SAMPLE_RATE, synth.OUT_RATE))


if __name__ == '__main__':
    main()
