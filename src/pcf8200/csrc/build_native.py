"""Build the C core into ../_bin/: pcf8200.dll for 64- and 32-bit Windows, or
libpcf8200.so on Linux.  An argument, x64 or x86, builds just that one.

How it is built (the compilers, the flags that keep the arithmetic the reference's,
the check on what a DLL imports) is tools/native_build.py's, shared with the
repository's other libraries.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, os.pardir, os.pardir, "tools"))
import native_build                                         # noqa: E402

if __name__ == "__main__":
    native_build.build_c_library(os.path.join(HERE, "pcf8200.c"), os.path.join(os.path.dirname(HERE), "_bin"),
                                 "pcf8200", only=(sys.argv[1:2] or [None])[0])
