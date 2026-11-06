"""Build the C core into ../_bin/: pcf8200.dll for 64- and 32-bit Windows, or
libpcf8200.so on Linux.

Windows wants w64devkit: set W64DEVKIT and W64DEVKIT_X86 to their bin folders, or
have the 64-bit gcc on the PATH.  -static: the DLLs import only KERNEL32 and msvcrt,
so they load with no VC runtime.  Floating point is kept to the reference's
arithmetic: -ffp-contract=off, and SSE2 doubles on 32-bit instead of the x87's
80-bit ones.
"""
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "_bin")
SOURCE = os.path.join(HERE, "pcf8200.c")
CFLAGS = ["-O2", "-std=c99", "-ffp-contract=off", "-Wall", "-Wextra"]
ALLOWED = {"KERNEL32.dll", "msvcrt.dll"}
TOOLCHAINS = {"x64": ("W64DEVKIT", [], "pei-x86-64"),
              "x86": ("W64DEVKIT_X86", ["-msse2", "-mfpmath=sse"], "pei-i386")}


def build_windows():
    for arch, (key, extra, fmt) in TOOLCHAINS.items():
        bindir = os.environ.get(key)
        if not bindir:
            found = shutil.which("gcc") if arch == "x64" else None
            if not found:
                print("%s: set %s to build it" % (arch, key))
                continue
            bindir = os.path.dirname(found)
        out_dir = os.path.join(BIN, arch)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "pcf8200.dll")
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        subprocess.run([os.path.join(bindir, "gcc.exe")] + CFLAGS + extra
                       + ["-shared", "-static", "-static-libgcc", "-s", "-o", out, SOURCE],
                       check=True, env=env)
        dump = subprocess.run([os.path.join(bindir, "objdump.exe"), "-p", out], env=env,
                              capture_output=True, text=True, check=True).stdout
        dlls = {ln.split(":", 1)[1].strip() for ln in dump.splitlines() if "DLL Name:" in ln}
        if not dlls <= ALLOWED:
            sys.exit("%s imports %s" % (out, sorted(dlls - ALLOWED)))
        if fmt not in dump:
            sys.exit("%s is not %s" % (out, fmt))
        print("%s: %d bytes, imports %s" % (out, os.path.getsize(out), sorted(dlls)))


def build_linux():
    out_dir = os.path.join(BIN, "linux-" + platform.machine())
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "libpcf8200.so")
    subprocess.run([os.environ.get("CC", "cc")] + CFLAGS
                   + ["-shared", "-fPIC", "-o", out, SOURCE, "-lm"], check=True)
    print("%s: %d bytes" % (out, os.path.getsize(out)))


if __name__ == "__main__":
    build_windows() if os.name == "nt" else build_linux()
