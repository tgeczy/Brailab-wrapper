# -*- coding: utf-8 -*-
"""Build a self-playing BraiLab PC recording: BRAIPLAY.EXE with speech data on its end.

    python make_braiplay.py SCRIPT.py OUT.EXE

SCRIPT.py defines PROGRAM, a list of steps:
    ('say', text)            text for TALKHUN; str is encoded for it, bytes go as they are
    ('set', b'\\x1bS4...')    escape sequences (tempo, pitch, furcsa...), as HUN.BAT sent to COM4
    ('pause', milliseconds)

The 2000 TALKHUN.COM runs here on an emulated 8086 and speaks each step to a model of the box;
what it sends to the chip is recorded as whole I2C transactions and packed after BRAIPLAY.EXE.
On the DOS machine the result needs nothing else: no TALKHUN, no settings.

The finished file is then run in the same emulator, and the transactions it sends are compared
with the recording.  It is written only if they are the same.

Needs Open Watcom in C:\\WATCOM (see build.sh) and third_party/brailab/TALKHUN.COM.
"""
import os
import runpy
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'talkhun_emu'))
from brailab_device import BraiLabDevice, STATUS_BUSY, STATUS_READY     # noqa: E402
from dos_host import DosHost, DEFAULT_CPU_HZ                            # noqa: E402

TALKHUN = os.path.join(ROOT, 'third_party', 'brailab', 'TALKHUN.COM')
MAGIC = b'BRAIREC1'
MAX_FRAMES = 3000
#: Recording TALKHUN: the emulated machine runs in slices, and a step is over once nothing has
#: been sent to the box for QUIET_SECONDS of its time.  The box model never makes TALKHUN wait,
#: so what it sends does not depend on these numbers; only whether it has finished does.
CAPTURE_CPU_HZ = DEFAULT_CPU_HZ
SLICE_SECONDS = 0.25
QUIET_SECONDS = 4.0
STEP_SECONDS = 600

# TALKHUN's own character set is CWI-2: code page 437 with the two double-acute letters where
# 437 has o and u circumflex.  437 has no capital A, I, O, U acute or double acute, and TALKHUN
# spells an unknown byte out as a code, so those capitals are sent as their small letters.
_FOLD = {'ő': 'ô', 'ű': 'û', 'Ő': 'ô', 'Ű': 'û', 'Á': 'á', 'Í': 'í', 'Ó': 'ó', 'Ú': 'ú'}


def encode(text):
    return ''.join(_FOLD.get(c, c) for c in text).encode('cp437')


class Box(BraiLabDevice):
    """The box as TALKHUN's code expects it: busy while idle (so the first poll of an utterance
    times out and the start sequence follows), asking for bytes once started, idle after STOP."""

    def __init__(self):
        super().__init__(None)
        self.running = False
        self.tx = []

    def status(self):
        return STATUS_READY if self.running else STATUS_BUSY

    def _finish(self):
        if not self._cur[1:]:
            return
        if self._cur[0] != 0x20:
            raise RuntimeError('address byte %02x' % self._cur[0])
        body = bytes(self._cur[1:])
        self.tx.append(body)
        self.running = not (len(body) == 2 and body[0] == 0 and body[1] & 0x20)


def new_host(workdir, cpu_hz=DEFAULT_CPU_HZ):
    box = Box()
    host = DosHost(workdir, on_lpt=box.on_out, lpt_status=box.status, cpu_hz=cpu_hz)
    box.host = host
    return host, box


def run_on(host, seconds):
    """Let the resident guest carry on from where it is, for at least `seconds` of its time.

    Ends just after a timer tick has been dispatched, so never inside the resident driver."""
    from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP
    uc = host.uc
    keep, host.exited = host.exited, None
    try:
        host._pump(uc.reg_read(UC_X86_REG_CS) * 16 + uc.reg_read(UC_X86_REG_IP),
                   2_000_000_000, host.vtime + seconds, 'capture')
    finally:
        host.exited = keep


def send(host, data):
    """Hand bytes to TALKHUN through INT 14h, as `copy file com4` did, and let it finish.

    DosHost.send_com4 does the same with a budget of two million instructions, which is plenty
    for a line of settings.  But TALKHUN speaks a long text from INSIDE this call, and the
    budget then runs out in the middle of a frame: the call is abandoned, and TALKHUN is left
    half way through an utterance for good.  Here the call runs to its end."""
    import dos_host as dh
    from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_IP
    data = data.replace(b'\0', b'')
    if not data:
        return
    if len(data) > 0x800:
        raise SystemExit('one step of %d bytes is too long: split the text' % len(data))
    uc = host.uc
    uc.mem_write(dh.BIOS_SEG * 16 + dh.OFF_CFGBUF, data + b'\0')
    uc.reg_write(UC_X86_REG_CS, dh.BIOS_SEG)
    uc.reg_write(UC_X86_REG_SS, dh.BIOS_SEG)
    uc.reg_write(UC_X86_REG_SP, dh.BIOS_STACK)
    uc.reg_write(UC_X86_REG_IP, dh.OFF_CFGSEND)
    host._no_irq = True
    try:
        uc.emu_start(dh.BIOS_SEG * 16 + dh.OFF_CFGSEND, dh.BIOS_SEG * 16 + dh.OFF_CFGDONE, count=2_000_000_000)
    finally:
        host._no_irq = False
    if uc.reg_read(UC_X86_REG_IP) != dh.OFF_CFGDONE:
        raise SystemExit('TALKHUN did not come back from taking %r' % (data[:40],))


def capture(program, workdir):
    """[('U', volume, pitch, command, stopped, [frames]) | ('P', ms)] for the program."""
    host, box = new_host(workdir, cpu_hz=CAPTURE_CPU_HZ)
    if host.run(TALKHUN, args='1') != 'tsr':
        raise SystemExit('TALKHUN.COM did not go resident')
    host.idle(0.5)
    del box.tx[:]
    records, start = [], (0x70, 0x2e, 0x81)
    for step in program:
        kind, value = step
        if kind == 'pause':
            if box.running:
                # TALKHUN is holding an utterance open, waiting for more text; the chip would
                # starve during the pause.  End the sentence, or change a setting, first.
                raise SystemExit('a pause while TALKHUN is still in the middle of an utterance')
            records.append(('P', int(value)))
            continue
        data = value if isinstance(value, bytes) else encode(value)
        if kind == 'say':
            data += b'\r\n'
        elif kind != 'set':
            raise SystemExit('unknown step %r' % (kind,))
        n0 = len(box.tx)
        send(host, data)
        # What TALKHUN has not said by now it says from its timer handler, a whole clause from
        # inside one call of it, and the emulated machine must not be cut off in the middle of
        # that either.  idle() starts the guest afresh in the idle loop: right once, here, with
        # the INT 14h call over.  After that run_on() carries on from wherever the machine is,
        # and stops only where a timer tick has just been handed to the guest, which never
        # happens inside TALKHUN's own code.
        host.idle(0.02)
        seen, quiet = -1, 0
        for _ in range(int(STEP_SECONDS / SLICE_SECONDS)):
            run_on(host, SLICE_SECONDS)
            quiet = quiet + 1 if len(box.tx) == seen else 0
            seen = len(box.tx)
            if quiet * SLICE_SECONDS >= QUIET_SECONDS:
                break
        else:
            raise SystemExit('TALKHUN was still sending after %d seconds: %r' % (STEP_SECONDS, value))
        # The chip may still be running here: with line ends ignored (ESC C1) TALKHUN keeps the
        # last sentence open until more text arrives.  The next step carries it on.
        tx, i = box.tx[n0:], 0
        while i < len(tx):
            if len(tx[i]) == 1:
                if not (i + 2 < len(tx) and len(tx[i + 1]) == 1 and len(tx[i + 2]) == 2 and tx[i + 2][0] == 0):
                    raise SystemExit('odd start sequence in %r' % (value,))
                start = (tx[i][0], tx[i + 1][0], tx[i + 2][1])
                i += 3
            frames = []
            while i < len(tx) and len(tx[i]) == 5:
                frames.append(tx[i])
                i += 1
            stopped = i < len(tx) and len(tx[i]) == 2 and tx[i][0] == 0 and bool(tx[i][1] & 0x20)
            if stopped:
                i += 1
            elif not frames:
                raise SystemExit('unexpected bytes %s in %r' % (tx[i].hex(), value))
            if len(frames) > MAX_FRAMES:
                raise SystemExit('one unit of %d frames in %r: split the text' % (len(frames), value))
            records.append(('U',) + start + (stopped, frames))
    if box.running:
        raise SystemExit('the program ends with TALKHUN still in the middle of an utterance')
    return records


def pack(records):
    out = bytearray()
    for r in records:
        if r[0] == 'P':
            out += b'P' + struct.pack('<H', min(r[1], 65535))
        else:
            _, vol, pitch, cmd, stopped, frames = r
            out += b'U' + bytes([vol, pitch, cmd, 1 if stopped else 0]) + struct.pack('<H', len(frames))
            out += b''.join(frames)
    out += b'E'
    return bytes(out) + MAGIC + struct.pack('<I', len(out))


def expected(records):
    """The transactions BRAIPLAY must send for these records, the chip starting idle."""
    tx, running = [], False
    for r in records:
        if r[0] != 'U':
            continue
        _, vol, pitch, cmd, stopped, frames = r
        if not running:                     # as TALKHUN: only an idle chip gets a start sequence
            tx += [bytes([vol]), bytes([pitch]), bytes([0, cmd])]
        tx += list(frames)
        if stopped:
            tx.append(bytes([0, 0xA0]))
        running = not stopped
    return tx


def build_stub():
    exe = os.path.join(HERE, 'braiplay.exe')
    env = dict(os.environ, WATCOM=r'C:\WATCOM', INCLUDE=r'C:\WATCOM\h',
               PATH=r'C:\WATCOM\binnt64;' + os.environ['PATH'])
    subprocess.run([r'C:\WATCOM\binnt64\wcl.exe', '-q', '-bt=dos', '-ms', '-0', '-os',
                    '-fe=braiplay.exe', 'braiplay.c'], cwd=HERE, env=env, check=True)
    with open(exe, 'rb') as f:
        return f.read()


def verify(exe_path, records, workdir):
    """Run the finished file on the emulated machine and compare what reaches the box."""
    # A slow machine: the pauses and the idle polls are waits on the clock, and a slower clock
    # rate means fewer instructions to emulate while they pass.  What is sent does not change.
    host, box = new_host(workdir, cpu_hz=1_000_000.0)
    result = host.run(exe_path, max_insns=4_000_000_000, max_vtime=36000.0)
    printed = b''.join(o if isinstance(o, bytes) else str(o).encode() for o in host.output).decode('cp852', 'replace')
    printed += ' [ended: %s, exit code %s]' % (result, host.exit_code)
    want = expected(records)
    if box.tx != want:
        n = next((i for i, (a, b) in enumerate(zip(box.tx, want)) if a != b), min(len(box.tx), len(want)))
        raise SystemExit('BRAIPLAY sent %d transactions, the recording has %d; first difference at %d:\n'
                         '  sent     %s\n  recorded %s\n%s'
                         % (len(box.tx), len(want), n,
                            box.tx[n].hex() if n < len(box.tx) else '(nothing)',
                            want[n].hex() if n < len(want) else '(nothing)',
                            printed[-400:]))
    return printed


def summary(records):
    units = [r for r in records if r[0] == 'U']
    frames = sum(len(r[5]) for r in units)
    furcsa = sum(1 for r in units if r[3] & 0x10)
    pause = sum(r[1] for r in records if r[0] == 'P') / 1000.0
    return units, frames, furcsa, pause


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    program = runpy.run_path(sys.argv[1])['PROGRAM']
    out = os.path.abspath(sys.argv[2])
    work = os.path.join(HERE, '_braiplay_work')
    os.makedirs(work, exist_ok=True)
    records = capture(program, work)
    data = build_stub() + pack(records)
    name = os.path.basename(out).upper()
    staged = os.path.join(work, name)
    with open(staged, 'wb') as f:
        f.write(data)
    printed = verify(staged, records, work)
    with open(out, 'wb') as f:
        f.write(data)
    units, frames, furcsa, pause = summary(records)
    print('%s: %d bytes, %d units (%d furcsa), %d frames, %.1f s of pauses' % (
        out, len(data), len(units), furcsa, frames, pause))
    print('verified on the emulated machine: every transaction matches the recording')
    print('the program printed:', printed.strip().replace('\r', '').replace('\n', ' | '))


if __name__ == '__main__':
    main()
