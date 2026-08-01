# -*- coding: utf-8 -*-
"""
A virtual BraiLab adapter on the DOS host's printer port.

This is the piece that makes the JATEKOK programs speak: run TALKHUN.COM inside
the guest as a TSR exactly as a 1991 machine did, let the game call INT 14h, and
decode the bit-bang TALKHUN sends to the parallel port into PCF-8200 frames.

Two things it must do, and the second is the one people forget:

  1. decode speech frames -- same protocol talkhun.py already proves out
  2. **hold the BUSY line while those frames would still be playing**

Without (2) the games race. On real hardware the ready poll at 0x1dc4 blocked
the CPU until the adapter finished speaking, so the *speech* paced the program.
Remove the device and text scrolls past far faster than anyone could listen.
"""

import os

from pcf8200 import decode_control, decode_frame, FD_MULT, FS_TAB

LPT_DATA = 0x378
LPT_STATUS = 0x379
LPT_CTRL = 0x37A

#: What the ready poll at 0x5308 tests.  Bit 4 set means the adapter is still
#: speaking, so keep waiting; bit 5 must stay set the whole time, because the
#: poll reads bit 5 low as a hardware fault and gives up.  Reporting busy as
#: 0x10 rather than 0x30 therefore looks like a broken adapter: the driver
#: sends one frame, decides nothing is listening, and goes quiet.
STATUS_BUSY = 0x30          # bits 4 and 5 set -> "speaking, wait"
STATUS_READY = 0x20         # bit 4 clear, bit 5 still healthy

#: Wall-clock a frame represents, before the FS/FD multipliers.
FRAME_MS = 12.8

#: Control sequences the driver is configured with.  On a real machine these
#: arrived as `copy BIOS10BE com4` lines in HUN.BAT; the names are Hungarian,
#: "be" on and "ki" off.  ESC A <hex> sets the mask at [0xaf44] deciding which
#: INT 10h text calls get spoken, and it starts at zero -- so a driver loaded
#: without this is resident, hooked, and mute.
ESC_BIOS10_ON = b'\x1bAF'       # BIOS10BE
ESC_BIOS10_OFF = b'\x1bA0'      # BIOS10KI
ESC_FURCSA_ON = b'\x1bF1'       # FURCSABE
ESC_FURCSA_OFF = b'\x1bF0'      # FURCSAKI
ESC_ECHO_OFF = b'\x1bT0'        # ECHOKI -- no key echo in a headless run
#: DEFAULT: normal pitch, speed 6, no furcsa, and the driver's own defaults.
ESC_DEFAULTS = b'\x1bP*\x1bS6\x1bF0\x1bR0\x1bC1\x1bE1\x1bK1'


class BraiLabDevice:
    """Decodes TALKHUN's 2-wire bit-bang and models the adapter's timing."""

    def __init__(self, host=None):
        self.host = host                # DosHost, for virtual time
        self.bits = []
        self.bytes_out = []
        self._clock = 0
        self._data = 0
        self._active = False
        self.frames = []                # completed 5-byte speech frames
        self.controls = []
        self.pitches = []
        self.seq = []                   # ordered ('pitch'|'ctrl'|'frame', ...)
        self.utterances = []            # [(pitch, [frames], ctrl)] per unit
        self._singles = 0
        self._busy_until = 0.0
        self._armed = True              # busy for the first poll of an utterance
        self._cur = []

    # -- virtual time ------------------------------------------------------
    @property
    def now(self):
        return self.host.vtime if self.host else 0.0

    # -- the wire ----------------------------------------------------------
    def on_out(self, port, value):
        """Called for every OUT to the printer port.

        The adapter speaks I2C over two printer pins -- which is exactly what
        you would expect, since the PCF-8200 is a Philips part and I2C is a
        Philips bus.  The driver's bit primitive drives (data, clock low),
        (data, clock high), (data, clock low); framing is the standard pair of
        conditions, data falling while the clock is held high to START and data
        rising while it is held high to STOP.

        Getting this wrong is not subtle but it is quiet: without START the bit
        stream never resynchronises, and the traffic decodes into a steady
        supply of plausible-looking nonsense.
        """
        if port != LPT_DATA:
            return
        data = value & 1
        clock = (value >> 1) & 1
        if clock and self._clock:               # clock held high: framing
            if self._data and not data:
                self._start()
            elif data and not self._data:
                self._stop()
        elif clock and not self._clock:         # rising edge: sample a bit
            self.bits.append(data)
            if len(self.bits) == 9:             # 8 bits MSB first, then ACK
                b = 0
                for bit in self.bits[:8]:
                    b = (b << 1) | bit
                del self.bits[:]
                self.bytes_out.append(b)
                self._cur.append(b)
        self._clock = clock
        self._data = data

    def _start(self):
        self.bits = []
        self._cur = []
        self._active = True

    def _stop(self):
        """Classify a completed transaction by its length, as the engine does."""
        self.bits = []
        body, self._cur, self._active = self._cur[1:], [], False
        if not body:
            return
        if len(body) == 5:
            self.frames.append(body)
            self.seq.append(('frame', body))
            self._speak(body)
        elif len(body) == 2:
            self.controls.append(body)
            self.seq.append(('ctrl', body))
        elif len(body) == 1:
            # a start sequence sends the settings nibble, then the pitch
            if self._singles % 2:
                self.pitches.append(body[0])
                self.seq.append(('pitch', body[0]))
                self.rearm()
            self._singles += 1

    def _speak(self, frame):
        """Charge the adapter for the time this frame will take to say."""
        d = decode_frame(frame)
        ms = FRAME_MS * FD_MULT[d['FD']]
        base = max(self.now, self._busy_until)
        self._busy_until = base + ms / 1000.0

    # -- the handshake -----------------------------------------------------
    def status(self):
        """What the guest reads from the printer status port.

        Busy while queued speech would still be sounding; that is what paces
        the program.  The first poll of an utterance also reports busy, which
        is what lets the start control write (carrying furcsa and tempo) go
        out at all -- see talkhun.py for why that polarity is not uniform.
        """
        if self.now < self._busy_until:
            return STATUS_BUSY
        if self._armed:
            self._armed = False
            return STATUS_BUSY
        return STATUS_READY

    def rearm(self):
        self._armed = True


def boot(games_dir, archive_dir=None, talkhun='TALKHUN.COM', cpu_hz=None,
         lpt='1', config=(ESC_DEFAULTS, ESC_BIOS10_ON)):
    """Bring up a DOS host with TALKHUN resident and a BraiLab on LPT1.

    Returns (host, device).  The TSR is loaded exactly as DOS would: run it
    until its AX=3100 call, leave its memory in place, and let the next program
    load above it.

    The default is TALKHUN.COM (v4), not TALKHUN0.COM, and the difference is
    the whole point.  TALKHUN0 is only the speech driver: it hooks INT 14h and
    waits to be called, and almost nothing in the corpus ever calls it.  v4 is
    a screen reader -- it hooks 08h, 09h, 10h, 14h and 2Fh, and its INT 10h
    handler speaks the BIOS text-output calls as they go past.  That is how
    these games talked; they were never written to know about speech at all.
    """
    from dos_host import DosHost, DEFAULT_CPU_HZ

    if archive_dir is None:
        archive_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'BRAILAB-archive')

    dev = BraiLabDevice()
    host = DosHost(games_dir,
                   on_lpt=lambda p, v: dev.on_out(p, v),
                   lpt_status=dev.status,
                   cpu_hz=cpu_hz or DEFAULT_CPU_HZ)
    dev.host = host

    # "talkhun 1" is how HUN.BAT loaded it: the argument is the printer port
    # number, and "talkhun 1,378" spells the address out.  With no argument at
    # all the driver installs but never binds to a port.
    res = host.run(os.path.join(archive_dir, talkhun), args=lpt)
    if res != 'tsr':
        raise RuntimeError('%s did not go resident (got %r)' % (talkhun, res))

    dev.frames.clear()          # drop the driver's own init frame
    dev.utterances.clear()
    for seq in config:
        host.send_com4(seq)
    return host, dev
