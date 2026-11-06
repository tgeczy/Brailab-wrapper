# -*- coding: utf-8 -*-
"""Build a pcf8200 wheel from the library csrc/build_native.py built.

    python build_wheel.py --plat win_amd64        (_bin/x64/pcf8200.dll)
    python build_wheel.py --plat win32            (_bin/x86/pcf8200.dll)
    python build_wheel.py --plat linux            (_bin/linux-<machine>/libpcf8200.so)
    python build_wheel.py --plat any              (no library: runs on the Python reference)

Writes dist/pcf8200-<version>-py3-none-<plat>.whl.  The package loads its library with
ctypes, so one wheel serves every Python 3 on its platform.  `--plat linux` tags the
wheel manylinux with the newest glibc symbol the library really uses, so build it on
an old system.

Standard library only: a wheel is a zip with METADATA, WHEEL and RECORD.  The wheel
holds this project's code alone, under MIT: nothing of TALKHUN, nothing of MAME.
"""
import argparse
import base64
import hashlib
import os
import platform
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ["__init__.py", "chip.py", "pcf8200_core.py", "pcf8200_native.py", "device.py",
           "protocol.py", "tables.py", "voice.py", "phonemes.py"]
WINDOWS = {"win_amd64": "x64", "win32": "x86"}


def project():
    """(version, summary, dependency, Python floor) from pyproject.toml."""
    text = open(os.path.join(HERE, "pyproject.toml"), encoding="utf-8").read()
    version = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
    summary = re.search(r'^description\s*=\s*"([^"]+)"', text, re.M).group(1)
    needs = re.search(r'^dependencies\s*=\s*\["([^"]+)"\]', text, re.M).group(1)
    python = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M).group(1)
    return version, summary, needs, python


def glibc_floor(path):
    """The newest GLIBC_x.y symbol version the library imports."""
    dump = subprocess.run(["objdump", "-T", path], capture_output=True, text=True,
                          check=True).stdout
    found = {tuple(int(n) for n in m) for m in re.findall(r"GLIBC_(\d+)\.(\d+)", dump)}
    if not found:
        sys.exit("no glibc symbols in %s" % path)
    return max(found)


def library(plat):
    """(path, name in the wheel, final platform tag)."""
    if plat == "any":
        return None, None, "any"
    if plat in WINDOWS:
        rel = "_bin/%s/pcf8200.dll" % WINDOWS[plat]
        tag = plat
    elif plat == "linux":
        machine = platform.machine()
        rel = "_bin/linux-%s/libpcf8200.so" % machine
        tag = None
    else:
        sys.exit("unknown platform %s" % plat)
    path = os.path.join(HERE, *rel.split("/"))
    if not os.path.exists(path):
        sys.exit("%s isn't built: run csrc/build_native.py" % rel)
    if tag is None:
        tag = "manylinux_%d_%d_%s" % (glibc_floor(path) + (machine,))
    return path, "pcf8200/" + rel, tag


def record_line(name, data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return "%s,sha256=%s,%d" % (name, digest, len(data))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plat", required=True, help="win_amd64, win32, linux or any")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    a = ap.parse_args()

    version, summary, needs, python = project()
    lib, lib_name, tag = library(a.plat)
    files = [("pcf8200/" + m, open(os.path.join(HERE, m), "rb").read()) for m in MODULES]
    if lib:
        files.append((lib_name, open(lib, "rb").read()))

    info = "pcf8200-%s.dist-info" % version
    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    metadata = ("Metadata-Version: 2.1\n"
                "Name: pcf8200\n"
                "Version: %s\n"
                "Summary: %s\n"
                "Home-page: https://github.com/tgeczy/Brailab-wrapper\n"
                "License: MIT\n"
                "Requires-Python: %s\n"
                "Requires-Dist: %s\n"
                "Classifier: License :: OSI Approved :: MIT License\n"
                "Classifier: Topic :: Multimedia :: Sound/Audio :: Speech\n"
                "Description-Content-Type: text/markdown\n"
                "\n" % (version, summary, python, needs)) + readme
    wheel = ("Wheel-Version: 1.0\n"
             "Generator: pcf8200 build_wheel.py\n"
             "Root-Is-Purelib: %s\n"
             "Tag: py3-none-%s\n" % ("true" if lib is None else "false", tag))
    files += [(info + "/METADATA", metadata.encode("utf-8")),
              (info + "/WHEEL", wheel.encode("utf-8")),
              (info + "/LICENSE", open(os.path.join(HERE, "LICENSE"), "rb").read())]
    record = "\n".join(record_line(n, d) for n, d in files) + "\n%s/RECORD,,\n" % info

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "pcf8200-%s-py3-none-%s.whl" % (version, tag))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files + [(info + "/RECORD", record.encode("utf-8"))]:
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o755 if name == lib_name else 0o644) << 16
            z.writestr(entry, data)
    print("built %s: %d files, %d KiB" % (os.path.basename(path), len(files),
                                          os.path.getsize(path) // 1024))
    return path


if __name__ == "__main__":
    main()
