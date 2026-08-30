# -*- coding: utf-8 -*-
"""The PCF8200 wire format: frames, control writes, and frame timing.

These pin the chip's own command protocol, the part a caller drives directly.
Where a test exists because something was once wrong, it says so.
"""
import numpy as np
import pytest

from pcf8200 import PCF8200, protocol as P, tables as T


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def test_encode_decode_round_trip():
    codes = dict(F1=22, F2=13, F3=4, F4=5, F5=1,
                 B1=3, B2=6, B3=2, B4=1, B5=3, AM=13, PI=2, FD=1)
    frame = P.encode_frame(**codes)
    assert len(frame) == 5
    got = P.decode_frame(frame)
    for k, v in codes.items():
        assert got[k] == v, "%s did not survive the round trip" % k


def test_fd_spans_two_bytes():
    """FD's two bits live in bit 7 of byte 2 and bit 7 of byte 3.

    A split field is the easiest one to encode into the wrong byte, and it
    controls frame duration -- so getting it wrong changes the rhythm of every
    utterance rather than failing outright.
    """
    for fd in range(4):
        f = P.decode_frame(P.encode_frame(FD=fd))
        assert f['FD'] == fd
    assert P.encode_frame(FD=2)[2] & 0x80
    assert P.encode_frame(FD=1)[3] & 0x80


def test_field_range_is_checked():
    with pytest.raises(ValueError):
        P.encode_frame(F3=8)             # F3 is three bits


def test_pi_16_means_noise():
    """PI code 16 selects noise excitation rather than a pitch increment."""
    assert P.frame_params(P.decode_frame(P.encode_frame(PI=P.PI_NOISE)))['noise']
    assert not P.frame_params(P.decode_frame(P.encode_frame(PI=2)))['noise']


# ---------------------------------------------------------------------------
# Control writes
# ---------------------------------------------------------------------------

def test_control_byte_round_trip():
    for stop in (False, True):
        for female in (False, True):
            for fs in range(4):
                d = P.decode_control(P.control_byte(stop, female, fs))
                assert (d['stop'], d['female'], d['fs']) == (stop, female, fs)


def test_ciber_start_command_decodes_as_male_fs1():
    """0x81 is what the Ciber232P actually sends to start an utterance.

    Captured from the real firmware: `00 81` -- not a stop, male tables, FS=1.
    """
    d = P.decode_control(bytes([0x00, 0x81]))
    assert d['is_control'] and not d['stop'] and not d['female']
    assert d['fs'] == 1
    assert d['frame_ms'] == 8.8


# ---------------------------------------------------------------------------
# Frame timing -- the FS regression
# ---------------------------------------------------------------------------

def _frames(chip, n=10, **codes):
    for _ in range(n):
        chip.frame_codes(**codes)
    return chip


@pytest.mark.parametrize("fs,frame_ms", [(0, 12.8), (1, 8.8), (2, 10.4), (3, 17.6)])
def test_control_fs_sets_the_frame_duration(fs, frame_ms):
    """FS1/FS0 in the control write must actually time the frames.

    `tracks()` used to hardcode the 12.8 ms standard frame and ignore FS
    entirely, so the Ciber232P's FS=1 stream rendered 12.8/8.8 = 1.4545x too
    slow. It was only caught by rendering a stream captured from real firmware
    and comparing it against a known-good reference.
    """
    chip = PCF8200(voice="male")
    chip.pitch(40)
    chip.control(fs=fs)
    _frames(chip, 10, F1=22, F2=13, F3=4, AM=13, PI=2, FD=0)
    audio = chip.render()
    expected = round(frame_ms * 0.001 * 10000) * 10
    assert len(audio) == expected


def test_fs_defaults_to_the_12_8ms_standard_frame():
    """A stream that never sends a control write keeps the old behaviour.

    The FS fix must not move existing callers.
    """
    chip = PCF8200(voice="male")
    chip.pitch(40)
    _frames(chip, 10, F1=22, F2=13, F3=4, AM=13, PI=2, FD=0)
    assert len(chip.render()) == 128 * 10


def test_fd_multiplies_the_standard_frame():
    lengths = []
    for fd in range(4):
        chip = PCF8200(voice="male")
        chip.pitch(40)
        _frames(chip, 4, F1=22, F2=13, F3=4, AM=13, PI=2, FD=fd)
        lengths.append(len(chip.render()))
    assert lengths == [128 * 4 * m for m in P.FD_MULT]


def test_stop_ends_the_stream():
    chip = PCF8200(voice="male")
    chip.pitch(40)
    _frames(chip, 4, F1=22, F2=13, F3=4, AM=13, PI=2, FD=0)
    n_before = len(chip.render())
    chip.stop()
    _frames(chip, 4, F1=22, F2=13, F3=4, AM=13, PI=2, FD=0)
    assert len(chip.render()) == n_before, "frames after STOP must not sound"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_render_is_deterministic():
    """Two identical streams must produce identical audio, sample for sample.

    Everything downstream -- comparing an emulator capture against a reference
    render -- depends on this being exactly reproducible.
    """
    def build():
        chip = PCF8200(voice="male")
        chip.pitch(40)
        _frames(chip, 8, F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)
        return chip.render()
    assert np.array_equal(build(), build())


def test_a_vowel_has_energy_and_silence_does_not():
    chip = PCF8200(voice="male")
    chip.pitch(40)
    _frames(chip, 8, F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)
    assert np.abs(chip.render()).max() > 0.01

    quiet = PCF8200(voice="male")
    quiet.pitch(40)
    _frames(quiet, 8, F1=22, F2=13, F3=4, AM=0, PI=2, FD=1)
    assert np.abs(quiet.render()).max() < 0.01


def test_female_tables_use_four_formants():
    chip = PCF8200(voice="female")
    fc, bw, amp, p, voiced = (PCF8200(voice="female")
                              .pitch(40)
                              .frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
                              .frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
                              .tracks())
    assert len(fc) == 4, "the female table is four-formant"
    assert chip.female


def test_pitch_hz_maps_through_the_table():
    chip = PCF8200(voice="male")
    chip.pitch_hz(100)
    expected = int(round(100 / T.PITCH_HZ_PER_UNIT))
    assert chip._seq[-1] == ('pitch', expected)


def test_custom_lowpass_still_has_the_formants():
    """A non-default cutoff must filter the cascade, not the excitation.

    The custom path used to be handed `exc` -- the raw excitation -- because
    `xl = exc.tolist()` copies, leaving `exc` pristine while the cascade wrote
    into the list.  Every formant was discarded and the caller got a lowpassed
    buzz.  The default cutoff was fine, so nothing caught it.

    Skipped without scipy, which CI deliberately does not install: a non-default
    cutoff is the one path in the library that needs it, and keeping the rest
    pure-numpy is what lets the whole thing be vendored into an NVDA add-on.
    """
    import pytest
    pytest.importorskip("scipy")
    import numpy as np
    from pcf8200.chip import render, LOWPASS_HZ
    chip = PCF8200(voice="male").pitch_hz(110)
    for _ in range(24):
        chip.frame_codes(F1=22, F2=13, F3=4, AM=13, PI=2, FD=1)
    fc, bw, amp, p, voiced = chip.tracks()

    default = render(fc, bw, amp, p, voiced, lowpass=LOWPASS_HZ)
    custom = render(fc, bw, amp, p, voiced, lowpass=3000.0)

    n = min(len(default), len(custom))
    corr = np.corrcoef(default[:n], custom[:n])[0, 1]
    assert corr > 0.9, (
        "a nearby cutoff must give nearly the same speech, got corr=%.3f "
        "-- the cascade is being thrown away again" % corr)


def test_mf_is_read_off_the_wire_not_off_the_object():
    """M/F must come from the control write, like FS already does.

    decode_control returns 'female' alongside 'fs'; tracks() consumed the one
    and ignored the other, applying the object's *final* voice to every frame.
    A stream that set the female bit itself would decode its frames against the
    male table.
    """
    chip = PCF8200(voice="male")            # constructed male...
    chip.control(female=True)               # ...but the stream says female
    chip.pitch(40)
    for _ in range(2):
        chip.frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
    fc, _bw, _amp, _p, _v = chip.tracks()
    assert len(fc) == 4, "the wire asked for the four-formant table"


def test_mf_change_after_frames_is_refused():
    """Switching tables mid-utterance changes how many tracks exist.

    It cannot be represented in one decode, so it is an error rather than a
    silent mis-render of everything before the switch.
    """
    import pytest
    chip = PCF8200(voice="male").pitch(40)
    chip.frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
    chip.frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
    chip.control(female=True)               # too late: frames already emitted
    chip.frame_codes(F1=10, F2=10, F3=4, AM=13, PI=2, FD=1)
    with pytest.raises(ValueError, match="mid-stream"):
        chip.tracks()
