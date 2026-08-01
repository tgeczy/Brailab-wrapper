# -*- coding: utf-8 -*-
r"""Run a DOS program with a BraiLab on the printer port and record what it said.

    python play_game.py ..\jatekok_x\JATEKOK#\JATEKOK\MNMESEK\MNMESEK.EXE out.wav

Nothing in the corpus asks to be spoken.  The games just print, and TALKHUN.COM
sits resident watching INT 10h go past; the speech is a side effect of the text
appearing.  So this loads the driver, runs the program on top of it, decodes the
I2C the driver bit-bangs at the parallel port, and renders the frames.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace')

import brailab_device
import synth

#: Enough Enters to walk past the title screens, where the speech actually is.
DEFAULT_KEYS = [0x1C0D] * 40


def render(seq, out, **kw):
    pcm = synth.render(seq, **kw)
    synth.write_wav(out, pcm)
    return pcm


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if not args:
        print(__doc__)
        return 1
    path = args[0]
    out = args[1] if len(args) > 1 else 'game.wav'
    vtime = 60.0
    for f in flags:
        if f.startswith('--seconds='):
            vtime = float(f.split('=')[1])

    cfg = [brailab_device.ESC_DEFAULTS, brailab_device.ESC_BIOS10_ON]
    if '--furcsa' in flags:
        cfg.append(brailab_device.ESC_FURCSA_ON)
    host, dev = brailab_device.boot(os.path.dirname(os.path.abspath(path)),
                                    config=cfg)
    host.keys = list(DEFAULT_KEYS)
    try:
        res = host.run(path, max_insns=20_000_000, max_vtime=vtime)
    except Exception as e:                  # a fault still leaves real speech
        res = 'fault: %s' % e
    # let whatever is still queued finish rather than cutting a word in half
    try:
        host.idle(4.0)
    except Exception:
        pass

    print('%s -> %r after %.1fs of guest time' % (os.path.basename(path),
                                                  res, host.vtime))
    print('   %d frames, %d control writes, %d pitch marks'
          % (len(dev.frames), len(dev.controls), len(dev.pitches)))
    for line in host.screen.text().splitlines():
        if line.strip():
            print('   |' + line.rstrip())
    if not dev.seq:
        print('   nothing was spoken')
        return 2
    pcm = render(dev.seq, out)
    print('   -> %s  (%.2f s of audio)' % (out, len(pcm) / synth.SAMPLE_RATE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
