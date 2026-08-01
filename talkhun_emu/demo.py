# -*- coding: utf-8 -*-
"""Speak text through the emulated 1991 talker and dump the frames.

    python demo.py "mama."
    python demo.py "szia." --furcsa
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace')

import pcf8200
from talkhun import Talkhun, load

ESC = '\x1b'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    text = args[0] if args else "mama."

    t = load()
    print("banner: %s" % (t.banners[0] if t.banners else "(none)"))
    print("INT 14h handler at %04x:%04x\n" % t.int14)

    if '--furcsa' in flags:
        # The real ESC layer, driven exactly as FURCSABE did in 1991.
        t.feed(ESC + 'F1')
        print("furcsa ON via ESC F1\n")

    frames, ctrls = t.synthesize(text)
    print(pcf8200.describe(frames, ctrls))


if __name__ == '__main__':
    main()
