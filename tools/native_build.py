"""What every native library here is built with, kept in one place: finding the compilers, where the result
goes, and the check that a Windows DLL depends on nothing a clean machine lacks.

Each library's own csrc/build_native.py says what to compile; this says how.

Windows wants w64devkit: set W64DEVKIT and W64DEVKIT_X86 to their bin folders, or have the 64-bit gcc on the
PATH.  The DLLs are linked -static and may import only KERNEL32 and msvcrt, so they load with no VC runtime.
Floating point is kept to one arithmetic everywhere: -ffp-contract=off, and SSE2 doubles on 32-bit instead of
the x87's 80-bit ones.
"""
import os
import platform
import shutil
import subprocess
import sys

C99 = ["-O2", "-std=c99", "-ffp-contract=off", "-Wall", "-Wextra"]
ALLOWED = {"KERNEL32.dll", "msvcrt.dll"}
#: arch: (environment variable naming the toolchain's bin folder, the flags it adds, the DLL's format)
TOOLCHAINS = {"x64": ("W64DEVKIT", [], "pei-x86-64"),
              "x86": ("W64DEVKIT_X86", ["-msse2", "-mfpmath=sse"], "pei-i386")}


def windows_toolchains(only=None, probe="gcc"):
    """(arch, bin folder, environment, extra flags, format) for each Windows toolchain that is here.  `only`
    (x64 or x86) keeps to that one; `probe` is the program looked for on the PATH when the 64-bit one's
    variable is not set."""
    for arch, (key, extra, fmt) in TOOLCHAINS.items():
        if only and arch != only:
            continue
        bindir = os.environ.get(key)
        if not bindir:
            found = shutil.which(probe) if arch == "x64" else None
            if not found:
                print("%s: set %s to build it" % (arch, key))
                continue
            bindir = os.path.dirname(found)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        yield arch, bindir, env, extra, fmt


def out_dir(bin_root, arch=None):
    """<bin_root>/x64, /x86 or /linux-<machine>, made if need be."""
    path = os.path.join(bin_root, arch or "linux-" + platform.machine())
    os.makedirs(path, exist_ok=True)
    return path


def audit(bindir, env, dll, fmt):
    """Stop unless `dll` is of format `fmt` and imports nothing outside ALLOWED; then say what was built."""
    dump = subprocess.run([os.path.join(bindir, "objdump.exe"), "-p", dll], env=env,
                          capture_output=True, text=True, check=True).stdout
    dlls = {ln.split(":", 1)[1].strip() for ln in dump.splitlines() if "DLL Name:" in ln}
    if not dlls <= ALLOWED:
        sys.exit("%s imports %s" % (dll, sorted(dlls - ALLOWED)))
    if fmt not in dump:
        sys.exit("%s is not %s" % (dll, fmt))
    print("%s: %d bytes, imports %s" % (dll, os.path.getsize(dll), sorted(dlls)))


def build_c_library(source, bin_root, name, cflags=C99, only=None):
    """One C file into <bin_root>/<arch>/<name>.dll for both Windows toolchains, or lib<name>.so on Linux."""
    if os.name == "nt":
        for arch, bindir, env, extra, fmt in windows_toolchains(only):
            out = os.path.join(out_dir(bin_root, arch), name + ".dll")
            subprocess.run([os.path.join(bindir, "gcc.exe")] + cflags + extra
                           + ["-shared", "-static", "-static-libgcc", "-s", "-o", out, source],
                           check=True, env=env)
            audit(bindir, env, out, fmt)
    else:
        out = os.path.join(out_dir(bin_root), "lib%s.so" % name)
        subprocess.run([os.environ.get("CC", "cc")] + cflags + ["-shared", "-fPIC", "-o", out, source, "-lm"],
                       check=True)
        print("%s: %d bytes" % (out, os.path.getsize(out)))
