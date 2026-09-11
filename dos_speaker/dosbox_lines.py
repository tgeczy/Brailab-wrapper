# -*- coding: utf-8 -*-
"""Ad-hoc DOSBox-X run with custom autoexec lines, on the emulated SB Pro, speaker off.

    python dosbox_lines.py OUTDIR [--t "sentence"]... [--file NAME "text"]... [--args "/J5"] "line" "line" ...

BRAISPK /B <args>, TALKHUNS 1 and SAY /C run first; then your lines; then BRAISPK /S.
--t writes T1.TXT, T2.TXT ... (CP852); --file NAME "text" writes any other file.
Captures: DX-CAPTURE /A /-V <program> in a line lands a WAV in OUTDIR/cap.
"""
import array, glob, os, shutil, subprocess, sys, time, wave

HERE = os.path.dirname(os.path.abspath(__file__))
DOSBOX = r"C:\DOSBox-X\dosbox-x.exe"
args = sys.argv[1:]
out = os.path.abspath(args.pop(0))
texts, files, lines, extra = [], [], [], ""
while args:
    a = args.pop(0)
    if a == "--t": texts.append(args.pop(0))
    elif a == "--file": files.append((args.pop(0), args.pop(0)))
    elif a == "--bin": files.append((args.pop(0), bytes.fromhex(args.pop(0))))   # a raw .COM etc.
    elif a == "--args": extra = args.pop(0)
    else: lines.append(a)
run, cap = os.path.join(out, "run"), os.path.join(out, "cap")
shutil.rmtree(out, ignore_errors=True); os.makedirs(run); os.makedirs(cap)
for f in ("braispk.exe", "say.exe", "TALKHUNS.COM"):
    shutil.copy(os.path.join(HERE, f), run)
for i, t in enumerate(texts, 1):
    open(os.path.join(run, "T%d.TXT" % i), "wb").write((t + "\r\n").encode("cp852"))
for name, t in files:
    open(os.path.join(run, name), "wb").write(t if isinstance(t, bytes) else (t + "\r\n").encode("cp852"))
auto = ["@echo off", 'mount c "%s"' % run, "c:", "braispk /B %s > log_braispk.txt" % extra,
        "talkhuns 1 > log_talkhun.txt", "say /C > log_say.txt"] + lines + ["braispk /S > stat_end.txt", "exit"]
conf = "\n".join(["[sdl]", "autolock=false", "[dosbox]", "captures=" + cap, "startbanner=false",
                  "fastbioslogo=true", "quit warning=false", "show recorded filename=false",
                  "[cpu]", "core=normal", "cycles=20000", "[mixer]", "rate=48000",
                  "[sblaster]", "sbtype=sbpro2", "sbbase=220", "irq=5", "dma=1", "hdma=5", "oplmode=auto",
                  "[speaker]", "pcspeaker=false", "[autoexec]"] + auto) + "\n"
confp = os.path.join(out, "run.conf"); open(confp, "w", newline="\n").write(conf)
t = time.time()
try:
    subprocess.run([DOSBOX, "-conf", confp, "-fastlaunch", "-nomenu"], timeout=120, capture_output=True, text=True)
    print("dosbox done after %.1fs" % (time.time() - t))
except subprocess.TimeoutExpired:
    os.system("taskkill /F /IM dosbox-x.exe >nul 2>&1"); print("TIMEOUT")
for f in sorted(os.listdir(run)):
    if f.lower().endswith(".txt") and not f.lower().startswith("t"):
        print("== %s: %s" % (f, open(os.path.join(run, f), "rb").read().decode("cp852", "replace").strip()))
for f in sorted(glob.glob(os.path.join(cap, "*.wav"))):
    w = wave.open(f); r, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    s = array.array("h", w.readframes(n))
    if ch == 2: s = array.array("h", [(s[i] + s[i + 1]) // 2 for i in range(0, len(s), 2)])
    step = r // 2
    rows = ["%4.0f" % ((sum(x * x for x in s[i:i + step]) / max(1, len(s[i:i + step]))) ** 0.5) for i in range(0, len(s), step)]
    print("%s %.1fs peak %d rms/0.5s: %s" % (os.path.basename(f), n / r, max((abs(x) for x in s), default=0), " ".join(rows)))
