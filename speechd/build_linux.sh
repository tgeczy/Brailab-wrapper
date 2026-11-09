#!/bin/sh
# Build sd_brailab, the speech-dispatcher module: one program, no Python, nothing to install beside it but
# TALKHUN0.COM.  Also builds talkhun_emu's library, which the tests drive directly.
#
#   ./build_linux.sh [out folder]        default: build/linux in the repository
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=${1:-$ROOT/build/linux}
CC=${CC:-cc}
CXX=${CXX:-c++}
CFLAGS="-O2 -std=c99 -ffp-contract=off -Wall -Wextra -D_GNU_SOURCE"
INC="-I$ROOT/talkhun_emu/csrc -I$ROOT/talkhun_emu/csrc/cpu -I$ROOT/pcf8200/csrc"
mkdir -p "$OUT/obj"
$CXX -O2 -std=c++17 -fno-exceptions -fno-rtti -Wall -Wno-sign-compare $INC \
    -c -o "$OUT/obj/i86_mame.o" "$ROOT/talkhun_emu/csrc/cpu/i86_mame.cpp"
for f in talkhun_emu/csrc/talkhun_host.c talkhun_emu/csrc/brailab_voice.c pcf8200/csrc/pcf8200.c \
         speechd/sd_brailab.c; do
    $CC $CFLAGS $INC -c -o "$OUT/obj/$(basename "$f" .c).o" "$ROOT/$f"
done
$CXX -o "$OUT/sd_brailab" "$OUT/obj/i86_mame.o" "$OUT/obj/talkhun_host.o" "$OUT/obj/brailab_voice.o" \
    "$OUT/obj/pcf8200.o" "$OUT/obj/sd_brailab.o" -static-libstdc++ -static-libgcc -lm
python3 "$ROOT/talkhun_emu/csrc/build_native.py"
echo "built $OUT/sd_brailab"
