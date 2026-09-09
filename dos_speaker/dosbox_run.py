# -*- coding: utf-8 -*-
"""Run the BRAISPK + TALKHUNS chain under DOSBox-X headlessly and capture what
the speaker says.

    python dosbox_run.py [--chip] [--cycles N] [--out DIR] "sentence" ["sentence" ...]

Each sentence is spoken by SAY.EXE /F under DX-CAPTURE, so one WAV per
sentence lands in DIR/cap.  Counters from BRAISPK /S are printed after each.
Never pass -silent to DOSBox-X: it mutes the mixer, and the capture is all
zeros.
"""
import argparse, glob, os, shutil, subprocess, sys, time, wave

HERE = os.path.dirname(os.path.abspath(__file__))
DOSBOX = r"C:\DOSBox-X\dosbox-x.exe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chip", action="store_true", help="BRAISPK /C: chip frame timing (FS bits)")
    ap.add_argument("--cycles", type=int, default=20000)
    ap.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."), "braispk_run"))
    ap.add_argument("--keep", action="store_true", help="do not unload at the end (debug)")
    ap.add_argument("--args", default="", help="extra BRAISPK switches, e.g. /V7")
    ap.add_argument("--test", action="store_true", help="also capture SAY /T: beep, speech, beep")
    ap.add_argument("text", nargs="*")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    run, cap = os.path.join(out, "run"), os.path.join(out, "cap")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(run); os.makedirs(cap)
    for f in ("braispk.exe", "say.exe", "TALKHUNS.COM"):
        shutil.copy(os.path.join(HERE, f), run)
    lines = ["@echo off", 'mount c "%s"' % run, "c:",
             "braispk %s %s > log_braispk.txt" % ("/C" if a.chip else "", a.args),
             "talkhuns 1 > log_talkhun.txt", "say /C > log_say.txt", "braispk /S > stat0.txt"]
    if a.test:
        lines += ["DX-CAPTURE /A /-V SAY.EXE /T", "braispk /S > stat_t.txt"]
    for i, txt in enumerate(a.text, 1):
        with open(os.path.join(run, "T%d.TXT" % i), "wb") as f:
            f.write((txt + "\r\n").encode("cp852"))
        lines += ["DX-CAPTURE /A /-V SAY.EXE /F T%d.TXT" % i, "braispk /S > stat%d.txt" % i]
    if not a.keep:
        lines.append("braispk /U > log_unload.txt")
    lines.append("exit")
    conf = "\n".join(["[sdl]", "autolock=false", "[dosbox]", "captures=" + cap, "startbanner=false",
                      "fastbioslogo=true", "quit warning=false", "show recorded filename=false",
                      "[cpu]", "core=normal", "cycles=%d" % a.cycles, "[mixer]", "rate=48000",
                      "[speaker]", "pcspeaker=true", "[autoexec]"] + lines) + "\n"
    confp = os.path.join(out, "run.conf")
    with open(confp, "w", newline="\n") as f:
        f.write(conf)

    t = time.time()
    try:
        p = subprocess.run([DOSBOX, "-conf", confp, "-fastlaunch", "-nomenu"], timeout=60 + 20 * len(a.text),
                           capture_output=True, text=True)
        with open(os.path.join(out, "dosbox.log"), "w") as f:
            f.write(p.stdout + p.stderr)
        print("dosbox exit %d after %.1fs" % (p.returncode, time.time() - t))
    except subprocess.TimeoutExpired:
        os.system("taskkill /F /IM dosbox-x.exe >nul 2>&1")
        print("TIMEOUT after %.1fs (hung)" % (time.time() - t))

    for f in sorted(os.listdir(run)):
        if f.lower().endswith(".txt") and not f.lower().startswith("t"):
            with open(os.path.join(run, f), "rb") as fh:
                print("== %s: %s" % (f, fh.read().decode("cp852", "replace").strip()))
    wavs = sorted(glob.glob(os.path.join(cap, "*.wav")))
    for f in wavs:
        w = wave.open(f)
        r, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        data = w.readframes(n)
        import array
        s = array.array("h", data)
        if ch == 2:
            s = array.array("h", [(s[i] + s[i + 1]) // 2 for i in range(0, len(s), 2)])
        peak = max((abs(x) for x in s), default=0)
        rms = (sum(x * x for x in s) / max(1, len(s))) ** 0.5
        print("%s  %.1fs  rms %.0f  peak %d" % (os.path.basename(f), n / r, rms, peak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
