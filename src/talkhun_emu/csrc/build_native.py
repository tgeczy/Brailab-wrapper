"""Build talkhun.dll (or libtalkhun.so on Linux): TALKHUN0's host on MAME's 8086, the
PCF8200 core, and the voice that joins them, into ../_bin/.  Set W64DEVKIT and
W64DEVKIT_X86 to the bin folders, as for pcf8200.

C++17 without exceptions or RTTI for the core; libstdc++ and libgcc are linked in, so
the DLLs import only KERNEL32 and msvcrt.  The compilers, the C flags and that check
are tools/native_build.py's, shared with the repository's other libraries.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, os.pardir, os.pardir, "tools"))
import native_build                                         # noqa: E402

BIN = os.path.join(os.path.dirname(HERE), "_bin")
CPU = os.path.join(HERE, "cpu")
CXX = ["-O2", "-std=c++17", "-fno-exceptions", "-fno-rtti", "-Wall", "-Wno-sign-compare"]
CHIP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "pcf8200", "csrc")
INC = ["-I" + CPU, "-I" + HERE, "-I" + CHIP]
C_SOURCES = [os.path.join(HERE, "talkhun_host.c"), os.path.join(HERE, "brailab_voice.c"),
             os.path.join(CHIP, "pcf8200.c")]


def compile_and_link(gcc, gxx, out, obj_dir, env, link, extra=()):
    os.makedirs(obj_dir, exist_ok=True)
    objs = [os.path.join(obj_dir, "i86_mame.o")]
    subprocess.run([gxx] + CXX + INC + ["-fPIC", "-c", "-o", objs[0],
                                        os.path.join(CPU, "i86_mame.cpp")], check=True, env=env)
    for source in C_SOURCES:
        obj = os.path.join(obj_dir, os.path.basename(source)[:-2] + ".o")
        subprocess.run([gcc] + native_build.C99 + list(extra) + INC + ["-fPIC", "-c", "-o", obj, source],
                       check=True, env=env)
        objs.append(obj)
    subprocess.run([gxx, "-shared", "-o", out] + objs + link, check=True, env=env)


def build_windows():
    for arch, bindir, env, extra, fmt in native_build.windows_toolchains(probe="g++"):
        out_dir = native_build.out_dir(BIN, arch)
        out = os.path.join(out_dir, "talkhun.dll")
        compile_and_link(os.path.join(bindir, "gcc.exe"), os.path.join(bindir, "g++.exe"), out,
                         os.path.join(out_dir, "obj"), env,
                         ["-static", "-static-libstdc++", "-static-libgcc", "-s"], extra)
        native_build.audit(bindir, env, out, fmt)


def build_linux():
    out_dir = native_build.out_dir(BIN)
    compile_and_link("cc", "c++", os.path.join(out_dir, "libtalkhun.so"),
                     os.path.join(out_dir, "obj"), dict(os.environ), ["-lm"])
    print(os.path.join(out_dir, "libtalkhun.so"))


if __name__ == "__main__":
    build_windows() if os.name == "nt" else build_linux()
