# -*- coding: utf-8 -*-
r"""Play a BraiLab-era DOS program, with the speech coming out of your speakers.

    python braipc.py <program.exe>
    python braipc.py                     (prompts for a path)

Type into the program as you would have in 1991.  F12 opens a BraiLab settings
menu -- tempo, pitch, furcsa -- and the menu speaks itself through the same
synthesiser, so nothing here needs a screen reader to be usable.

Why no accessible_output shim: the speech is not a description of the program,
it IS the program's output.  TALKHUN.COM sits resident watching INT 10h and
speaks whatever gets printed, exactly as it did on real hardware, so there is
nothing to bolt on -- the emulator only has to carry the audio to the speakers
and the keystrokes back in.
"""
import collections
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brailab_device
import synth
import talkhun

try:
    import msvcrt
except ImportError:                                   # pragma: no cover
    msvcrt = None

#: Guest time per slice.  Short enough that a keypress lands promptly, long
#: enough that the emulator is not spending all its time restarting.
SLICE_S = 0.20
#: Speak a batch once this many frames are queued, or once the guest falls
#: quiet -- synthesising every frame on its own would break the filter state
#: mid-word, and waiting for the whole utterance would answer too late.
BATCH_FRAMES = 60
QUIET_SLICES = 2

#: Playback format.  The synthesiser works at 10 kHz like the chip; the card
#: gets 44.1 stereo because that is what plays cleanly everywhere.
OUT_RATE = 44100

#: DOS keyboard: (scancode << 8) | ascii, which is what INT 16h AH=0 returns.
EXTENDED = {
    'H': 0x4800, 'P': 0x5000, 'K': 0x4B00, 'M': 0x4D00,   # arrows
    'G': 0x4700, 'O': 0x4F00, 'I': 0x4900, 'Q': 0x5100,   # home/end/pgup/pgdn
    'R': 0x5200, 'S': 0x5300,                             # insert/delete
    ';': 0x3B00, '<': 0x3C00, '=': 0x3D00, '>': 0x3E00,   # F1-F4
}
SIMPLE = {'\r': 0x1C0D, '\n': 0x1C0D, '\x1b': 0x011B, ' ': 0x3920,
          '\x08': 0x0E08, '\t': 0x0F09}

#: The four base frame durations the FS field can select, fastest last.
TEMPOS = [('lassú', '1'), ('normál', '2'), ('gyors', '3'), ('leggyorsabb', '4')]
#: ESC P takes a character; these are the three the archive shipped.
PITCHES = [('mély', '!'), ('normál', '*'), ('magas', '=')]


class Speaker:
    """Queues rendered audio and feeds the sound card from a background thread."""

    def __init__(self, rate=OUT_RATE):
        import numpy as np
        import sounddevice as sd
        self.np, self.sd, self.rate = np, sd, rate
        self.buf = collections.deque()
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(samplerate=rate, channels=2,
                                      dtype='int16', blocksize=1024,
                                      callback=self._cb)
        self.stream.start()

    def _cb(self, out, frames, t, status):
        np = self.np
        need = frames
        pos = 0
        with self.lock:
            while need and self.buf:
                chunk = self.buf[0]
                take = min(need, len(chunk))
                out[pos:pos + take, 0] = chunk[:take]
                out[pos:pos + take, 1] = chunk[:take]
                pos += take
                need -= take
                if take == len(chunk):
                    self.buf.popleft()
                else:
                    self.buf[0] = chunk[take:]
        if need:
            out[pos:, :] = 0

    def play(self, pcm10k):
        """Take 10 kHz mono int16 from the synthesiser and queue it."""
        if pcm10k is None or not len(pcm10k):
            return
        data = synth.resample(pcm10k, synth.SAMPLE_RATE, self.rate)
        with self.lock:
            self.buf.append(self.np.asarray(data, dtype=self.np.int16))

    @property
    def pending(self):
        with self.lock:
            return sum(len(c) for c in self.buf)

    def drain(self, timeout=20.0):
        end = time.time() + timeout
        while self.pending and time.time() < end:
            time.sleep(0.05)

    def flush(self):
        with self.lock:
            self.buf.clear()

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


class Session:
    """A resident TALKHUN, a guest program, and the plumbing between them."""

    def __init__(self, path, speaker):
        self.path = os.path.abspath(path)
        self.speaker = speaker
        self.tempo = 1                                   # index into TEMPOS
        self.pitch = 1                                   # index into PITCHES
        self.furcsa = False
        cfg = [brailab_device.ESC_DEFAULTS, brailab_device.ESC_BIOS10_ON]
        self.host, self.dev = brailab_device.boot(
            os.path.dirname(self.path), config=cfg)
        self.dev.reset()
        self.seen = 0
        self.quiet = 0
        # A second engine, only for menu prompts.  Speaking them through the
        # guest would write on the game's screen and disturb what the resident
        # driver is tracking; this one is independent and sounds identical.
        self.ui = talkhun.load()

    # -- speech ----------------------------------------------------------
    def say_ui(self, text):
        """Speak an interface prompt, out of band from the guest."""
        try:
            self.speaker.play(synth.render(self.ui.capture(text),
                                           furcsa=self.furcsa))
        except Exception:
            pass

    def pump_speech(self, force=False):
        """Hand any new adapter traffic to the synthesiser."""
        new = self.dev.seq[self.seen:]
        nframes = sum(1 for k, _ in new if k == 'frame')
        if not nframes:
            return
        self.quiet = 0 if nframes else self.quiet + 1
        if not force and nframes < BATCH_FRAMES and self.quiet < QUIET_SLICES:
            return
        self.seen = len(self.dev.seq)
        try:
            self.speaker.play(synth.render(new, furcsa=self.furcsa))
        except Exception:
            pass

    # -- driver control --------------------------------------------------
    def apply(self, seq):
        try:
            self.host.send_com4(seq)
        except Exception:
            pass

    def set_tempo(self, i):
        self.tempo = i % len(TEMPOS)
        self.apply(b'\x1bS' + TEMPOS[self.tempo][1].encode())
        self.say_ui('Tempó: %s.' % TEMPOS[self.tempo][0])

    def set_pitch(self, i):
        self.pitch = i % len(PITCHES)
        self.apply(b'\x1bP' + PITCHES[self.pitch][1].encode())
        self.say_ui('Hangmagasság: %s.' % PITCHES[self.pitch][0])

    def toggle_furcsa(self):
        self.furcsa = not self.furcsa
        self.apply(brailab_device.ESC_FURCSA_ON if self.furcsa
                   else brailab_device.ESC_FURCSA_OFF)
        self.say_ui('Furcsa hang %s.' % ('be' if self.furcsa else 'ki'))

    # -- the settings menu -----------------------------------------------
    def menu(self):
        """A self-voicing BraiLab menu.  Arrows change, Escape leaves."""
        self.speaker.flush()
        items = [
            ('Tempó', lambda d: self.set_tempo(self.tempo + d)),
            ('Hangmagasság', lambda d: self.set_pitch(self.pitch + d)),
            ('Furcsa hang', lambda d: self.toggle_furcsa()),
        ]
        i = 0
        self.say_ui('BraiLab beállítások. %s.' % items[0][0])
        while True:
            k = read_key(block=True)
            if k is None:
                continue
            if k in (K_ESC, 'F12'):
                self.say_ui('Kilépés a beállításokból.')
                return
            if k == K_UP:
                i = (i - 1) % len(items)
                self.say_ui(items[i][0] + '.')
            elif k == K_DOWN:
                i = (i + 1) % len(items)
                self.say_ui(items[i][0] + '.')
            elif k in (K_LEFT, K_RIGHT, K_ENTER):
                items[i][1](-1 if k == K_LEFT else 1)

    # -- main loop --------------------------------------------------------
    def run(self):
        self.host.start(self.path)
        self.say_ui('Indul: %s.' % os.path.basename(self.path))
        # The emulator runs about three times faster than the machine it is
        # imitating, so pace guest time against the wall clock.  Otherwise the
        # program races ahead of the speech describing it, which on real
        # hardware could not happen -- the busy line saw to that.
        wall0, guest0 = time.time(), self.host.vtime
        try:
            while self.host.exited is None:
                ahead = (self.host.vtime - guest0) - (time.time() - wall0)
                if ahead > SLICE_S:
                    time.sleep(min(ahead, 0.25))
                if msvcrt:
                    while msvcrt.kbhit():
                        k = read_key()
                        if k == 'F12':
                            self.menu()
                        elif isinstance(k, int):
                            self.host.keys.append(k)
                try:
                    self.host.resume(SLICE_S)
                except Exception as e:
                    print('\nguest fault: %s' % e)
                    break
                self.pump_speech()
        finally:
            self.pump_speech(force=True)
            self.speaker.drain()


def read_key(block=False):
    """One keystroke as the AX value INT 16h would return.

    Everything stays a plain DOS key except F12, which is ours -- so arrows and
    Escape still reach the guest normally, and the menu recognises them by
    their AX values rather than by being handed a different type.
    """
    if not msvcrt:
        return None
    if not block and not msvcrt.kbhit():
        return None
    ch = msvcrt.getch()
    if ch in (b'\x00', b'\xe0'):
        ext = msvcrt.getch().decode('latin-1')
        if ext == '\x86':
            return 'F12'
        return EXTENDED.get(ext, 0)
    c = ch.decode('cp852', 'replace')
    if c in SIMPLE:
        return SIMPLE[c]
    return ord(c[0]) & 0xFF


#: AX values the menu steers by.
K_ESC, K_UP, K_DOWN, K_LEFT, K_RIGHT = 0x011B, 0x4800, 0x5000, 0x4B00, 0x4D00
K_ENTER = 0x1C0D


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = input('Program path: ').strip('" ')
    if not os.path.exists(path):
        print('not found: %s' % path)
        return 2
    print('BraiLab PC -- %s' % os.path.basename(path))
    print('F12 = settings, Escape in the menu goes back, Ctrl+C quits.')
    speaker = Speaker()
    try:
        Session(path, speaker).run()
    except KeyboardInterrupt:
        pass
    finally:
        speaker.close()
    print('\ndone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
