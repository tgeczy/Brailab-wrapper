# -*- coding: utf-8 -*-
r"""Freeze the emulator into a single Windows executable.

    python build_exe.py            -> dist\BraiLabPC.exe

Console application on purpose.  Keyboard input goes through msvcrt and the
program's own screen is the console, so a windowed build would have nowhere to
type and nothing to show.

TALKHUN.COM is deliberately NOT bundled.  It is the BraiLab authors' work, not
ours to redistribute; the emulator looks for it via the BRAILAB_ARCHIVE
environment variable and says so when it cannot find it.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'BraiLabPC'
ENTRY = os.path.join(HERE, 'braipc.py')

#: PyInstaller finds unicorn's payload and sounddevice's PortAudio DLL only if
#: told; both are loaded at runtime rather than imported normally.
COLLECT = ['unicorn', 'sounddevice', '_sounddevice_data']
HIDDEN = ['scipy.signal', 'scipy.special', 'numpy',
          'brailab_device', 'pcf8200', 'synth', 'talkhun']


def main():
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
            '--console', '--name', NAME,
            '--distpath', os.path.join(HERE, 'dist'),
            '--workpath', os.path.join(HERE, 'build'),
            '--specpath', HERE,
            '--paths', HERE]
    for m in COLLECT:
        args += ['--collect-all', m]
    for m in HIDDEN:
        args += ['--hidden-import', m]
    # nothing here uses matplotlib or IPython; excluding them saves ~40 MB
    for m in ('matplotlib', 'IPython', 'tcl', 'pytest', 'PIL', 'pandas'):
        args += ['--exclude-module', m]
    args.append(ENTRY)

    print('building %s.exe ...' % NAME)
    rc = subprocess.call(args)
    if rc != 0:
        return rc
    out = os.path.join(HERE, 'dist', NAME + '.exe')
    if os.path.exists(out):
        print('\n-> %s  (%.1f MB)' % (out, os.path.getsize(out) / 1e6))
    return 0


if __name__ == '__main__':
    sys.exit(main())
