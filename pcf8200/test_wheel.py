# -*- coding: utf-8 -*-
"""Install a wheel in a fresh virtual environment and hear what it does.

    python test_wheel.py dist/pcf8200-<version>-py3-none-<plat>.whl

The package must come from the environment, not this folder.  A platform wheel must
really run in C, and give the PCM of the Python reference inside the same package.
A pure wheel must fall back to that reference on its own.  A different seed must give
different noise, or the comparison proves nothing.
"""
import json
import os
import subprocess
import sys
import tempfile

CHILD = r'''
import hashlib, json, os, sys
import numpy as np
import pcf8200
from pcf8200 import PCF8200, pcf8200_core as core

def pcm(seed):
    chip = PCF8200(voice="male")
    chip.pitch_hz(110)
    for codes in (dict(F1=22, F2=13, F3=4, AM=13, PI=2, FD=2),
                  dict(F1=10, F2=20, F3=6, AM=9, PI=16, FD=2),
                  dict(F1=22, F2=13, F3=4, AM=13, PI=2, FD=2)):
        chip.frame_codes(**codes)
    chip.stop()
    audio = pcf8200.render(*chip.tracks(), seed=seed)
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()

b = pcm(1)
print(json.dumps({"where": os.path.dirname(pcf8200.__file__), "version": pcf8200.__version__,
                  "core": type(core.make_core(5)).__name__, "samples": len(b) // 2,
                  "peak": max(abs(int(x)) for x in np.frombuffer(b, "<i2")),
                  "hash": hashlib.sha256(b).hexdigest(),
                  "other_seed": hashlib.sha256(pcm(2)).hexdigest()}))
'''


def run(python, backend, cwd):
    env = {k: v for k, v in os.environ.items() if k not in ("PCF8200_BACKEND", "PYTHONPATH")}
    if backend:
        env["PCF8200_BACKEND"] = backend
    out = subprocess.run([python, "-c", CHILD], cwd=cwd, env=env, check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    wheel = os.path.abspath(sys.argv[1])
    pure = wheel.endswith("-none-any.whl")
    with tempfile.TemporaryDirectory(prefix="pcf8200wheel") as tmp:
        env = os.path.join(tmp, "env")
        subprocess.run([sys.executable, "-m", "venv", env], check=True)
        python = os.path.join(env, "Scripts", "python.exe") if os.name == "nt" \
            else os.path.join(env, "bin", "python")
        subprocess.run([python, "-m", "pip", "install", "-q", wheel], check=True)

        auto = run(python, None, tmp)
        reference = run(python, "python", tmp)
        print(json.dumps(auto, indent=1))
        assert auto["where"].startswith(env), "imported from %s" % auto["where"]
        assert auto["samples"] > 1000 and auto["peak"] > 1000, "silence"
        assert auto["hash"] != auto["other_seed"], "the seed changes nothing"
        assert reference["core"] == "Core"
        assert auto["core"] == ("Core" if pure else "NativeCore"), auto["core"]
        assert auto["hash"] == reference["hash"], "C and the reference differ"
    print("%s: %s, PCM equal to the reference" % (os.path.basename(wheel), auto["core"]))


if __name__ == "__main__":
    main()
