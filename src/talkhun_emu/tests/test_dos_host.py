# -*- coding: utf-8 -*-
"""DosHost, the DOS that BraiLabPC and make_braiplay run TALKHUN in: what it owes a running program.

  - a setting sent to the resident driver while a program runs leaves the program as it was (#33)
  - a send runs to its end or says it did not (#38)
  - the timer is held while the program has interrupts off, and a handler starts with them off (#39)

Needs Unicorn and TALKHUN.COM (third_party/brailab, or BRAILAB_ARCHIVE); skips without them.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
pytest.importorskip("unicorn")
ARCHIVE = os.environ.get("BRAILAB_ARCHIVE",
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "third_party", "brailab"))
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(ARCHIVE, "TALKHUN.COM")),
                                reason="needs TALKHUN.COM")

import brailab_device                                   # noqa: E402
import dos_host                                         # noqa: E402
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_EFLAGS   # noqa: E402

# inc word [0106h]; jmp 0100h; the counter
COUNT = bytes([0xFF, 0x06, 0x06, 0x01, 0xEB, 0xFA, 0, 0])
# cli; inc word [0107h]; jmp 0101h; the counter: interrupts off for good
COUNT_CLI = bytes([0xFA, 0xFF, 0x06, 0x07, 0x01, 0xEB, 0xFA, 0, 0])


def boot_with(tmp_path, name, code):
    with open(os.path.join(str(tmp_path), name), "wb") as f:
        f.write(code)
    host, dev = brailab_device.boot(str(tmp_path), archive_dir=ARCHIVE)
    host.start(os.path.join(str(tmp_path), name))
    return host, dev


def counter(host, at):
    cs = host.uc.reg_read(UC_X86_REG_CS)
    return int.from_bytes(bytes(host.uc.mem_read(cs * 16 + at, 2)), "little")


def test_a_setting_sent_while_a_program_runs_leaves_it_running(tmp_path):
    """#33: the F12 menu's tempo, pitch and furcsa killed the program: send_com4 left CS:IP at its own stub."""
    host, _ = boot_with(tmp_path, "COUNT.COM", COUNT)
    host.resume(0.05)
    cs = host.uc.reg_read(UC_X86_REG_CS)
    before = counter(host, 0x106)
    assert before > 0
    for setting in (b"\x1bS3", b"\x1bP=", brailab_device.ESC_FURCSA_ON):
        assert host.send_com4(setting) is True
        assert host.uc.reg_read(UC_X86_REG_CS) == cs, "the program's registers came back"
    host.resume(0.05)
    assert host.exited is None
    assert host.uc.reg_read(UC_X86_REG_CS) == cs
    assert counter(host, 0x106) != before, "the program went on counting"


def test_a_long_send_runs_to_its_end_or_says_it_did_not(tmp_path, monkeypatch):
    """#38: two million instructions stopped a 54-byte sentence half way, and send_com4 still said True."""
    host, dev = brailab_device.boot(str(tmp_path), archive_dir=ARCHIVE)
    sentence = "Ez egy ötvennégy bájtos magyar mondat, amit kimondunk.".encode("cp852")
    assert host.send_com4(sentence) is True
    assert any(k == "frame" for k, _ in dev.seq), "TALKHUN spoke it"
    monkeypatch.setattr(dos_host, "SEND_BUDGET", 10_000)
    with pytest.raises(RuntimeError):
        host.send_com4(sentence)
    with pytest.raises(ValueError):
        host.send_com4(b"a" * (dos_host.SEND_MAX + 1))


def dispatches(host, monkeypatch):
    """Each timer dispatch, with the FLAGS the handler starts with."""
    seen = []
    real = host._dispatch_guest

    def spy(intno):
        ok = real(intno)
        if intno == 0x08:
            seen.append(host.uc.reg_read(UC_X86_REG_EFLAGS))
        return ok
    monkeypatch.setattr(host, "_dispatch_guest", spy)
    return seen


def test_the_timer_waits_while_interrupts_are_off(tmp_path, monkeypatch):
    """#39: a program doing cli got every IRQ0 regardless, and the handler was entered with IF still on."""
    host, _ = boot_with(tmp_path, "CLI.COM", COUNT_CLI)
    seen = dispatches(host, monkeypatch)
    host.resume(0.5)                                   # about nine timer ticks
    assert counter(host, 0x107) > 0
    assert seen == [], "no timer interrupt reaches code that said cli"


def test_the_timer_reaches_a_program_with_interrupts_on_and_its_handler_starts_with_them_off(tmp_path, monkeypatch):
    host, _ = boot_with(tmp_path, "COUNT.COM", COUNT)
    seen = dispatches(host, monkeypatch)
    host.resume(0.5)
    assert len(seen) >= 5, "a program starts with interrupts on, as DOS starts it"
    assert all(not f & dos_host.FLAG_IF and not f & dos_host.FLAG_TF for f in seen), [hex(f) for f in seen]
