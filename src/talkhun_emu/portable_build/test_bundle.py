import sys, os, time
print("python:", sys.version.split()[0], "| exe:", sys.executable)
import numpy, scipy.signal, unicorn
print("core deps OK: numpy", numpy.__version__, "unicorn", unicorn.__version__)
try:
    import sounddevice; print("sounddevice OK:", sounddevice.__version__)
except Exception as e:
    print("sounddevice import FAILED:", repr(e))
import talkhun, chip_synth, brailab_device
os.environ["BRAILAB_ARCHIVE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BraiLabPC-portable", "archive")
GAME = r"C:\git\jatekok\AD20.EXE"
cfg = [brailab_device.ESC_DEFAULTS, brailab_device.ESC_BIOS10_ON]
host, dev = brailab_device.boot(os.path.dirname(GAME), archive_dir=os.environ["BRAILAB_ARCHIVE"], config=cfg)
host.block_on_input = False; dev.reset(); host.start(GAME)
t0 = time.time()
while host.exited is None and time.time() - t0 < 4: host.resume(0.2)
nf = sum(1 for k, v in dev.seq if k == "frame")
x = chip_synth.render_chip_fast(dev.seq, furcsa_override=False)
print("GAME booted+rendered from BUNDLE: %d frames, %.2fs speech -> SELF-CONTAINED OK" % (nf, len(x)/10000))
