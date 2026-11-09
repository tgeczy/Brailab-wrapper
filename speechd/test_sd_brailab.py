"""sd_brailab against speech-dispatcher's module protocol, every message's audio checked byte for byte.

The harness plays the server: it starts the module, speaks the protocol on its stdin and stdout, and decodes the
705 AUDIO blocks.  The reference is brailab_voice.py on the library the NVDA add-on uses, given what the NVDA
driver would give it, so the module must be the add-on's voice:

  init     INIT loads, LIST VOICES has both voices, in Hungarian
  speak    messages whole, including every Hungarian letter, typographic punctuation (UTF-8 to CWI-2 in C,
           against Python's codec) and a lone capital
  set      rate, pitch and volume from SET (SSIP -100..100 to the driver's 0..100)
  furcsa   SET synthesis_voice picks the weird voice, and back
  stop     STOP after two blocks ends the message with 703, and the next message is whole and clean
  char     CHAR and KEY (shift_a is said as "shift a")
  conf     BrailabIntonation 0 in the module's file, and this user's file winning over it

    python3 test_sd_brailab.py <sd_brailab> <folder with TALKHUN0.COM>
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "talkhun_emu"))
import brailab_voice                                        # noqa: E402

MODULE, DATA = sys.argv[1], sys.argv[2]
with open(os.path.join(DATA, "TALKHUN0.COM"), "rb") as f:
    REF = brailab_voice.Voice(f.read())
failures = []


def to100(ssip):
    return max(0, min(100, (ssip + 100) // 2))


def reference(text, rate=0, pitch=0, volume=100, furcsa=False, intonation=True):
    r, p, v = to100(rate), to100(pitch), to100(volume)
    return b"".join(REF.stream(text, pitch=2.0 ** ((p - 50.0) / 100.0), time_scale=0.9 - 0.55 * (r / 100.0),
                               furcsa=furcsa, intonation=intonation, gain=0.25 + v / 100.0))


class Module:
    def __init__(self, conf=None, user_conf=None):
        self.home = tempfile.mkdtemp(prefix="sdbrailab")
        args = [MODULE]
        if conf is not None:
            path = os.path.join(self.home, "brailab.conf")
            with open(path, "w") as f:
                f.write(conf)
            args.append(path)
        if user_conf is not None:
            os.makedirs(os.path.join(self.home, ".config", "brailab"))
            with open(os.path.join(self.home, ".config", "brailab", "sd_brailab.conf"), "w") as f:
                f.write(user_conf)
        env = dict(os.environ, HOME=self.home, BRAILAB_DATADIR=DATA)
        env.pop("XDG_CONFIG_HOME", None)
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        self.send("INIT")
        lines = []
        while True:
            lines.append(self.line())
            if not lines[-1].startswith(b"299-") and not lines[-1].startswith(b"399-"):
                break
        self.init = lines

    def send(self, *lines):
        self.p.stdin.write(b"".join(l.encode("utf-8") + b"\n" for l in lines))
        self.p.stdin.flush()

    def line(self):
        return self.p.stdout.readline().rstrip(b"\n")

    def audio_block(self, first):
        s, n = first, None
        while not s.startswith(b"705-AUDIO"):
            if s.startswith(b"705-num_samples="):
                n = int(s.split(b"=")[1])
            assert s.startswith(b"705-"), s
            s = self.line()
        data = s[len(b"705-AUDIO") + 1:] + b"\n"
        while not data.endswith(b"\n705 AUDIO\n"):
            data += self.p.stdout.readline()
        raw, out, i = data[:-len(b"\n705 AUDIO\n")], bytearray(), 0
        while i < len(raw):
            if raw[i] == 0x7D:
                out.append(raw[i + 1] ^ 0x20)
                i += 2
            else:
                out.append(raw[i])
                i += 1
        assert len(out) == 2 * n, (len(out), n)
        return bytes(out)

    def speak(self, text, cmd="SPEAK", stop_after=None):
        self.send(cmd)
        assert self.line() == b"202 OK RECEIVING MESSAGE"
        self.send(*[("." + l if l.startswith(".") else l) for l in text.split("\n")], ".")
        assert self.line() == b"200 OK SPEAKING"
        assert self.line() == b"701 BEGIN"
        pcm, blocks = bytearray(), 0
        while True:
            s = self.line()
            if s.startswith(b"705-"):
                pcm += self.audio_block(s)
                blocks += 1
                if blocks == stop_after:
                    self.send("STOP")
            else:
                return bytes(pcm), s

    def set(self, **kw):
        self.send("SET", *["%s=%s" % (k, v) for k, v in kw.items()], ".")
        assert self.line() == b"202 OK RECEIVING MESSAGE"
        assert self.line() == b"203 OK SETTINGS RECEIVED"

    def quit(self):
        self.send("QUIT")
        self.p.wait(10)


def check(label, ok, detail=""):
    print("%-8s %s %s" % (label, "ok" if ok else "FAIL", detail))
    if not ok:
        failures.append(label)


def same(label, got, want):
    check(label, got == want and len(want) > 1000, "%d samples" % (len(want) // 2)
          if got == want else "got %d, want %d samples" % (len(got) // 2, len(want) // 2))


TEXTS = ["Jó napot kívánok.", "árvíztűrő tükörfúrógép, ÁRVÍZTŰRŐ TÜKÖRFÚRÓGÉP!",
         "Ez – mondta – „idézet”… tovább.", "A", "1234, 56. Mennyi az idő? Fél öt."]

m = Module()
check("init", m.init[-1] == b"299 OK LOADED SUCCESSFULLY", m.init[-1].decode())
m.send("LIST VOICES")
voices = []
while True:
    s = m.line()
    voices.append(s)
    if not s.startswith(b"200-"):
        break
check("voices", voices == [b"200-BraiLab PC\thu\tMALE1", b"200-BraiLab PC furcsa\thu\tMALE2",
                           b"249 OK VOICES LISTED"], repr(voices))
for i, text in enumerate(TEXTS):
    pcm, end = m.speak(text)
    same("speak%d" % i, pcm, reference(text))
    check("end%d" % i, end == b"702 END", end.decode())
m.set(rate=40, pitch=-30, volume=20)
same("set", m.speak(TEXTS[0])[0], reference(TEXTS[0], rate=40, pitch=-30, volume=20))
m.set(rate=0, pitch=0, volume=100, synthesis_voice="BraiLab PC furcsa")
same("furcsa", m.speak(TEXTS[0])[0], reference(TEXTS[0], furcsa=True))
m.set(synthesis_voice="BraiLab PC")
same("back", m.speak(TEXTS[0])[0], reference(TEXTS[0]))
long_text = " ".join(["Egy hosszabb mondat, amely sokáig tart, és közben megállítjuk."] * 4)
pcm, end = m.speak(long_text, stop_after=2)
check("stop", end == b"703 STOP" and len(pcm) < len(reference(long_text)), end.decode())
same("after", m.speak(TEXTS[0])[0], reference(TEXTS[0]))
same("char", m.speak("b", cmd="CHAR")[0], reference("b"))
same("key", m.speak("shift_a", cmd="KEY")[0], reference("shift a"))
m.quit()

m = Module(conf='BrailabIntonation 0\n')
same("conf", m.speak(TEXTS[0])[0], reference(TEXTS[0], intonation=False))
check("conf_on", reference(TEXTS[0], intonation=False) != reference(TEXTS[0]), "the setting changes the sound")
m.quit()
m = Module(conf='BrailabIntonation 0\n', user_conf='BrailabIntonation 1\n')
same("user", m.speak(TEXTS[0])[0], reference(TEXTS[0]))
m.quit()

m = Module()
os.environ["BRAILAB_DATADIR"] = "/nonexistent"
bad = subprocess.Popen([MODULE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                       env=dict(os.environ, BRAILAB_DATADIR="/nonexistent"))
out = bad.communicate(b"INIT\n", timeout=10)[0]
check("nodata", out.rstrip().endswith(b"399 ERR CANT INIT MODULE"), out.decode().splitlines()[0])
m.quit()

print("FAILED: " + ", ".join(failures) if failures else "all passed")
sys.exit(1 if failures else 0)
