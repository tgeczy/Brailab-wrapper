"""Build talkhun.dll (or libtalkhun.so on Linux): TALKHUN0's host on MAME's 8086, the
PCF8200 core, and the voice that joins them, into ../_bin/.  Set W64DEVKIT and
W64DEVKIT_X86 to the bin folders, as for pcf8200.

C++17 without exceptions or RTTI for the core; libstdc++ and libgcc are linked in, so
the DLLs import only KERNEL32 and msvcrt.
"""
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "_bin")
CPU = os.path.join(HERE, "cpu")
CXX = ["-O2", "-std=c++17", "-fno-exceptions", "-fno-rtti", "-Wall", "-Wno-sign-compare"]
CC = ["-O2", "-std=c99", "-ffp-contract=off", "-Wall", "-Wextra"]
CHIP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "pcf8200", "csrc")
INC = ["-I" + CPU, "-I" + HERE, "-I" + CHIP]
ALLOWED = {"KERNEL32.dll", "msvcrt.dll"}
TOOLCHAINS = {"x64": ("W64DEVKIT", "pei-x86-64", []),
              "x86": ("W64DEVKIT_X86", "pei-i386", ["-msse2", "-mfpmath=sse"])}


def compile_and_link(gcc, gxx, out, obj_dir, env, link, extra=()):
    os.makedirs(obj_dir, exist_ok=True)
    objs = [os.path.join(obj_dir, "i86_mame.o")]
    subprocess.run([gxx] + CXX + INC + ["-fPIC", "-c", "-o", objs[0],
                                        os.path.join(CPU, "i86_mame.cpp")], check=True, env=env)
    for source in (os.path.join(HERE, "talkhun_host.c"), os.path.join(HERE, "brailab_voice.c"),
                   os.path.join(CHIP, "pcf8200.c")):
        obj = os.path.join(obj_dir, os.path.basename(source)[:-2] + ".o")
        subprocess.run([gcc] + CC + list(extra) + INC + ["-fPIC", "-c", "-o", obj, source],
                       check=True, env=env)
        objs.append(obj)
    subprocess.run([gxx, "-shared", "-o", out] + objs + link, check=True, env=env)


def build_windows():
    for arch, (key, fmt, extra) in TOOLCHAINS.items():
        bindir = os.environ.get(key)
        if not bindir:
            found = shutil.which("g++") if arch == "x64" else None
            if not found:
                print("%s: set %s to build it" % (arch, key))
                continue
            bindir = os.path.dirname(found)
        out_dir = os.path.join(BIN, arch)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "talkhun.dll")
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        compile_and_link(os.path.join(bindir, "gcc.exe"), os.path.join(bindir, "g++.exe"), out,
                         os.path.join(out_dir, "obj"), env,
                         ["-static", "-static-libstdc++", "-static-libgcc", "-s"], extra)
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
    compile_and_link("cc", "c++", os.path.join(out_dir, "libtalkhun.so"),
                     os.path.join(out_dir, "obj"), dict(os.environ), ["-lm"])
    print(os.path.join(out_dir, "libtalkhun.so"))


if __name__ == "__main__":
    build_windows() if os.name == "nt" else build_linux()
