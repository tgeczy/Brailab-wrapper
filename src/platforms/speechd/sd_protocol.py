"""The server's side of speech-dispatcher's module protocol, for the tests: starts sd_brailab, talks to it on its
stdin and stdout, and decodes the 705 AUDIO blocks."""
import os
import subprocess
import tempfile


class Module:
    def __init__(self, module, datadir, conf=None, user_conf=None):
        self.home = tempfile.mkdtemp(prefix="sdbrailab")
        args = [module]
        if conf is not None:
            path = os.path.join(self.home, "brailab.conf")
            with open(path, "w") as f:
                f.write(conf)
            args.append(path)
        if user_conf is not None:
            os.makedirs(os.path.join(self.home, ".config", "brailab"))
            with open(os.path.join(self.home, ".config", "brailab", "sd_brailab.conf"), "w") as f:
                f.write(user_conf)
        env = dict(os.environ, HOME=self.home)
        env.pop("XDG_CONFIG_HOME", None)
        env.pop("BRAILAB_DATADIR", None)
        if datadir is not None:
            env["BRAILAB_DATADIR"] = datadir
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        self.rate = None
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
            if s.startswith(b"705-sample_rate="):
                self.rate = int(s.split(b"=")[1])
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

    def voices(self):
        self.send("LIST VOICES")
        out = []
        while True:
            s = self.line()
            out.append(s)
            if not s.startswith(b"200-"):
                return out

    def quit(self):
        self.send("QUIT")
        self.p.wait(10)
