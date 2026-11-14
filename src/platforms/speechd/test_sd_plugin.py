"""sd_brailab's optional voice plug-in, tested with a stand-in (test_tts_stub.c) whose samples say what it was
given.  Needs no TALKHUN0.COM and no real plug-in, so it runs anywhere the module builds:

  alone    with only a plug-in in the data folder the module loads, and "BraiLab TTS" is its one voice
  speak    the text reaches the plug-in as UTF-8 with SSML taken off, in blocks, at the plug-in's sample rate
  set      SSIP rate to the ten tempos (0 is the voice's own, 4), pitch to the three pitches, volume as a gain
           here, the plug-in's own volume left alone
  stop     STOP after a block ends the message with 703, PAUSE with 704; the next message is whole
  replies  every reply line is the one speech-dispatcher's own modules give (0.11.0 to 0.12.1): voices, also
           asked for with a language as 0.12 does, AUDIO, LOGLEVEL, SET
  lines    DEBUG ON and OFF are answered; a command that merely holds the word STOP does not stop the message;
           an unknown command and QUIT are answered
  absent   no plug-in, another interface version, a file that is no plug-in, missing data: no third voice, and
           the reason in the module's greeting when a file was there
  conf     BrailabTtsPlugin names a plug-in somewhere else
  three    (with a TALKHUN0.COM folder as the fourth argument) all three voices, switching between them

    python3 test_sd_plugin.py <sd_brailab> <stub .so> <stub of another version .so> [folder with TALKHUN0.COM]
"""
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sd_protocol import Module                              # noqa: E402

MODULE, STUB, STUB_OTHER = sys.argv[1], sys.argv[2], sys.argv[3]
TALKHUN = sys.argv[4] if len(sys.argv) > 4 else None
failures = []


def check(label, ok, detail=""):
    print("%-8s %s %s" % (label, "ok" if ok else "FAIL", detail))
    if not ok:
        failures.append(label)


def to100(ssip):
    return max(0, min(100, (ssip + 100) // 2))


def stub(text, rate=0, pitch=0, volume=100):
    """What the module must send for `text`: the stand-in's samples for the settings the module should hand it,
    turned by the module's gain."""
    r, p = to100(rate), to100(pitch)
    tempo = (r * 9 + 49) // 100
    pit = -1 if p <= 25 else 1 if p >= 75 else 0
    gain = 0.25 + to100(volume) / 100.0
    out = []
    for b in text.encode("utf-8"):
        v = b * 64 + tempo * 4 + (pit + 1)
        for i in range(80):
            x = max(-32767.0, min(32767.0, (-v if i & 1 else v) * gain))
            out.append(int(x + 0.5) if x >= 0 else -int(-x + 0.5))
    return struct.pack("<%dh" % len(out), *out)


def folder(plugin=STUB, data=True, talkhun=False, name="libbrailab_tts.so"):
    d = tempfile.mkdtemp(prefix="sdplugin")
    if plugin:
        shutil.copy(plugin, os.path.join(d, name))
    if data:
        with open(os.path.join(d, "binadata.bin"), "wb") as f:
            f.write(b"stand-in")
    if talkhun:
        shutil.copy(os.path.join(TALKHUN, "TALKHUN0.COM"), d)
    return d


def same(label, got, want):
    check(label, got == want and len(want) > 1000, "%d samples" % (len(want) // 2)
          if got == want else "got %d, want %d samples" % (len(got) // 2, len(want) // 2))


TTS = b"200-BraiLab TTS\thu\tMALE3"
LISTED = b"200 OK VOICE LIST SENT"
TEXT = "Jó napot kívánok, árvíztűrő tükörfúrógép."

m = Module(MODULE, folder())
check("alone", m.init[-1] == b"299 OK LOADED SUCCESSFULLY" and any(b"plug-in is loaded" in l for l in m.init),
      b" | ".join(m.init).decode())
check("voices", m.voices() == [TTS, LISTED])
check("voices12", m.voices("hu") == [TTS, LISTED] and m.voices("hu-HU none") == [TTS, LISTED]
      and m.voices("en") == [b"304 CANT LIST VOICES"] and m.voices("hun") == [b"304 CANT LIST VOICES"],
      "LIST VOICES with a language, as speech-dispatcher 0.12 sends it")
check("audio", m.block("AUDIO", "audio_output_method=server") == (b"207 OK RECEIVING AUDIO SETTINGS", b"203 OK AUDIO INITIALIZED"))
check("loglevel", m.block("LOGLEVEL", "log_level=3") == (b"207 OK RECEIVING LOGLEVEL SETTINGS", b"203 OK LOGLEVEL SET"))
pcm, end = m.speak(TEXT)
same("speak", pcm, stub(TEXT))
check("end", end == b"702 END" and m.rate == 10000, "%s at %s Hz" % (end.decode(), m.rate))
pcm, end = m.speak("<speak>Egy &amp; <mark name=\"x\"/>kettő &lt;három&gt;</speak>")
same("ssml", pcm, stub("Egy & kettő <három>"))
long_text = "Hosszabb szöveg, több blokkra. " * 12
same("blocks", m.speak(long_text)[0], stub(long_text))
for rate, tempo in ((-100, 0), (-80, 1), (0, 4), (12, 5), (100, 9)):
    m.set(rate=rate)
    pcm = m.speak(TEXT)[0]
    same("rate%d" % rate, pcm, stub(TEXT, rate=rate))
    check("tempo%d" % tempo, struct.unpack("<h", pcm[:2])[0] == int((ord("J") * 64 + tempo * 4 + 1) * 1.25 + 0.5))
m.set(rate=0)
for pitch in (-100, -50, -48, 0, 48, 50, 100):
    m.set(pitch=pitch)
    same("pitch%d" % pitch, m.speak(TEXT)[0], stub(TEXT, pitch=pitch))
m.set(pitch=0)
for volume in (-100, -40, 0, 60, 100):
    m.set(volume=volume)
    same("vol%d" % volume, m.speak(TEXT)[0], stub(TEXT, volume=volume))
m.set(volume=100)
stop_text = "Ezt a hosszú üzenetet megállítjuk, mielőtt a végére érne. " * 40
pcm, end = m.speak(stop_text, stop_after=1)
check("stop", end == b"703 STOP" and 0 < len(pcm) < len(stub(stop_text)), "%s after %d of %d samples"
      % (end.decode(), len(pcm) // 2, len(stub(stop_text)) // 2))
same("after", m.speak(TEXT)[0], stub(TEXT))
pcm, end = m.speak(stop_text, stop_after=1, stop_with="PAUSE")
check("pause", end == b"704 PAUSE" and 0 < len(pcm) < len(stub(stop_text)), "%s after %d of %d samples"
      % (end.decode(), len(pcm) // 2, len(stub(stop_text)) // 2))
same("p_after", m.speak(TEXT)[0], stub(TEXT))
check("debug", m.command("DEBUG ON /tmp/sd_brailab.log") == b"200 OK DEBUGGING ON"
      and m.command("DEBUG OFF") == b"200 OK DEBUGGING OFF" and m.command("DEBUG") == b"302 ERROR BAD SYNTAX")
# a command that only holds the words, arriving while the module speaks: the message is said to the end
pcm, end = m.speak(long_text, stop_after=1, stop_with="DEBUG ON /tmp/STOP-PAUSE-CANCEL.log")
same("dbg_mid", pcm, stub(long_text))
check("dbg_end", end == b"702 END" and m.line() == b"200 OK DEBUGGING ON", end.decode())
check("unknown", m.command("NO SUCH COMMAND") == b"300 ERR UNKNOWN COMMAND")
same("char", m.speak("b" * 20, cmd="CHAR")[0], stub("b" * 20))
same("key", m.speak("shift_a" * 4, cmd="KEY")[0], stub("shift a" * 4))
pcm, end = m.speak("")
check("empty", pcm == b"" and end == b"702 END")
m.set(synthesis_voice="BraiLab PC")                     # a voice this module hasn't got: no change
same("novoice", m.speak(TEXT)[0], stub(TEXT))
check("quit", m.quit() == b"210 OK QUIT" and m.p.returncode == 0)

for label, d, want in (("absent", folder(plugin=None), None),
                       ("version", folder(plugin=STUB_OTHER), b"version"),
                       ("notlib", folder(plugin=__file__), b"BraiLab TTS"),
                       ("nodata", folder(data=False), b"did not open")):
    m = Module(MODULE, d)
    why = b" | ".join(m.init)
    ok = m.init[-1] == b"399 ERR CANT INIT MODULE" and (want is None and b"BraiLab TTS" not in why
                                                         or want is not None and want in why)
    check(label, ok, why.decode(errors="replace")[:150])
    m.p.wait(10)

elsewhere = folder(name="another_name.so")
m = Module(MODULE, folder(plugin=None), conf='BrailabTtsPlugin "%s"\n' % os.path.join(elsewhere, "another_name.so"))
check("conf", m.init[-1] == b"299 OK LOADED SUCCESSFULLY" and m.voices() == [TTS, LISTED])
same("confsay", m.speak(TEXT)[0], stub(TEXT))
m.quit()

if TALKHUN:
    PC, FURCSA = b"200-BraiLab PC\thu\tMALE1", b"200-BraiLab PC furcsa\thu\tMALE2"
    m = Module(MODULE, folder(talkhun=True))
    check("three", m.voices() == [PC, FURCSA, TTS, LISTED])
    first, end = m.speak(TEXT)                          # the default voice is still the BraiLab PC
    check("default", first != stub(TEXT) and len(first) > 20000 and m.rate == 10000)
    m.set(synthesis_voice="BraiLab TTS")
    same("switch", m.speak(TEXT)[0], stub(TEXT))
    m.set(synthesis_voice="BraiLab PC furcsa")
    furcsa = m.speak(TEXT)[0]
    check("furcsa", furcsa != first and furcsa != stub(TEXT) and len(furcsa) > 20000)
    m.set(synthesis_voice="BraiLab PC")
    check("back", m.speak(TEXT)[0] == first, "the first voice says it as it did before")
    m.quit()
    m = Module(MODULE, folder(plugin=STUB_OTHER, talkhun=True))
    check("refused", m.init[-1] == b"299 OK LOADED SUCCESSFULLY" and m.voices() == [PC, FURCSA, LISTED]
          and any(b"not offered" in l and b"version" in l for l in m.init), b" | ".join(m.init).decode()[:160])
    m.quit()

print("FAILED: " + ", ".join(failures) if failures else "all passed")
sys.exit(1 if failures else 0)
