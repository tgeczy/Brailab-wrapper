#!/bin/sh
# The installer against scratch folders: install.sh and uninstall.sh on a package made by tools/package_linux.sh
# from the real module, with speechd.conf as each kind of system has it, and the optional voice in every way it
# can arrive.  The "voice" here is the tests' stand-in plug-in (test_tts_stub.c), fetched from a folder.
#   - a stock config (no active AddModule: autodiscovery on) is left byte for byte as it was;
#   - a config that lists its modules itself gets this one listed too, once, however often the installer runs;
#   - --default sets DefaultModule, and uninstall.sh gives back each config exactly as it was;
#   - with no terminal and no option nothing is fetched; --without-tts likewise;
#   - --with-tts fetches (from a folder, and over HTTP from a server on this machine), checks the checksum and
#     installs, and the module then has the third voice;
#   - a wrong checksum, a file that is no package, and a place that does not answer leave the voice out and the
#     BraiLab PC voices installed and working; --tts-file installs from a file.
#
#   sh src/platforms/speechd/test_install.sh [build folder]        default: build/linux
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
BUILD="$(cd "${1:-$ROOT/build/linux}" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAIL=0
ok()   { printf 'ok   %-40s %s\n' "$1" "$2"; }
fail() { printf 'FAIL %-40s %s\n' "$1" "$2"; FAIL=1; }

# the package, as a user gets it (the packaging script writes into build/, so work on a copy of the tree's needs)
mkdir -p "$T/tree/build/linux" "$T/tree/tools" "$T/tree/src/platforms" "$T/tree/third_party" "$T/tree/src/talkhun_emu/csrc/cpu"
cp "$BUILD/sd_brailab" "$T/tree/build/linux/"
cp "$ROOT/tools/package_linux.sh" "$T/tree/tools/"
cp -r "$ROOT/src/platforms/speechd" "$T/tree/src/platforms/"
cp -r "$ROOT/third_party/brailab" "$T/tree/third_party/"
cp -r "$ROOT/src/talkhun_emu/csrc/cpu/mame_i86" "$T/tree/src/talkhun_emu/csrc/cpu/"
cp "$ROOT/LICENSE" "$ROOT/NOTICE.md" "$T/tree/"
if ! sh "$T/tree/tools/package_linux.sh" 9.9.9 v-test > "$T/package.log" 2>&1; then
    fail "package" "$(tail -3 "$T/package.log" | tr '\n' ' ')"; echo "install: FAILED"; exit 1
fi
mkdir "$T/unpacked" && tar -xzf "$T/tree/build/brailab-9.9.9-linux-$(uname -m).tar.gz" -C "$T/unpacked"
PKG="$T/unpacked/brailab-9.9.9-linux-$(uname -m)"
if [ -x "$PKG/install.sh" ] && [ -x "$PKG/bin/sd_brailab" ] && [ "$(cat "$PKG/share/brailab/release-tag")" = v-test ] \
        && [ ! -e "$PKG/share/brailab/libbrailab_tts.so" ]; then
    ok "package" "module, TALKHUN0.COM, installer, release tag; no plug-in inside"
else fail "package" "$(ls -R "$PKG" | tr '\n' ' ')"; fi

# a "release" to fetch from: the stand-in plug-in packaged as the real one is, with its checksum
ARCH="$(uname -m)"
REL="$T/release"
mkdir -p "$REL" "$T/plug/brailab-tts-plugin"
cp "$BUILD/test/libbrailab_tts.so" "$T/plug/brailab-tts-plugin/"
printf 'stand-in' > "$T/plug/brailab-tts-plugin/binadata.bin"
printf 'stand-in' > "$T/plug/brailab-tts-plugin/binahank.bin"
(cd "$T/plug" && tar -czf "$REL/brailab-tts-plugin-linux-$ARCH.tar.gz" brailab-tts-plugin)
(cd "$REL" && sha256sum "brailab-tts-plugin-linux-$ARCH.tar.gz" > "brailab-tts-plugin-linux-$ARCH.tar.gz.sha256")
mkdir "$T/release-badsum" && cp "$REL"/* "$T/release-badsum/"
printf '%064d  x\n' 0 > "$T/release-badsum/brailab-tts-plugin-linux-$ARCH.tar.gz.sha256"

STOCK='# speechd.conf, as a distribution ships it
DefaultModule espeak-ng
#AddModule "espeak-ng"    "sd_espeak-ng" "espeak-ng.conf"
DefaultLanguage en
'
LISTED='# speechd.conf that lists its modules (autodiscovery off)
DefaultModule espeak-ng
AddModule "espeak-ng"    "sd_espeak-ng" "espeak-ng.conf"
'

fresh() {   # fresh CASE CONF-TEXT: a new system with that speechd.conf
    D="$T/$1"
    rm -rf "$D"
    mkdir -p "$D/etc" "$D/modules" "$D/prefix"
    printf '%s' "$2" > "$D/etc/speechd.conf"
    cp "$D/etc/speechd.conf" "$D/before.conf"
}
install() { # install [BASE] [args]: install.sh on the current system, with no terminal
    base="$1"; shift
    ( cd "$PKG" && PREFIX="$D/prefix" BRAILAB_SPD_MODULES="$D/modules" BRAILAB_SPD_CONF="$D/etc/speechd.conf" \
        BRAILAB_TTS_BASE="$base" sh ./install.sh "$@" ) > "$D/install.log" 2>&1 < /dev/null
}
uninstall() {
    ( cd "$PKG" && PREFIX="$D/prefix" BRAILAB_SPD_MODULES="$D/modules" BRAILAB_SPD_CONF="$D/etc/speechd.conf" \
        sh ./uninstall.sh ) > "$D/uninstall.log" 2>&1
}
voices() {  # the voices the installed module offers, on one line
    printf 'INIT\nLIST VOICES\nQUIT\n' | HOME="$D" "$D/modules/sd_brailab" "$D/etc/modules/brailab.conf" 2>/dev/null \
        | grep '^200-' | cut -f1 | sed 's/^200-//' | tr '\n' ',' | sed 's/,$//'
}
active() { grep -c '^[[:space:]]*AddModule[[:space:]]*"brailab"' "$D/etc/speechd.conf"; }
unset BRAILAB_DATADIR 2>/dev/null || true

# 1. stock, no terminal, no option: speechd.conf untouched, two voices, nothing fetched
fresh stock "$STOCK"
install "file://$REL"
if cmp -s "$D/before.conf" "$D/etc/speechd.conf"; then ok "stock config unchanged" "autodiscovery stays on"
else fail "stock config unchanged" "$(diff "$D/before.conf" "$D/etc/speechd.conf" | tr '\n' ' ')"; fi
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa" ] && [ ! -e "$D/prefix/share/brailab/libbrailab_tts.so" ]; then
    ok "no terminal: nothing fetched" "$(voices)"
else fail "no terminal: nothing fetched" "$(voices) | $(tail -3 "$D/install.log" | tr '\n' ' ')"; fi

# 2. --with-tts on top of that: fetched, checked, the third voice is there; the first two as before
install "file://$REL" --with-tts
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa,BraiLab TTS" ]; then ok "--with-tts" "$(voices)"
else fail "--with-tts" "$(voices) | $(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi
install "file://$T/nowhere"                      # run again with no option: the voice is kept, nothing fetched
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa,BraiLab TTS" ] && grep -q 'already installed' "$D/install.log"; then
    ok "installed voice kept on reinstall" "no fetch"
else fail "installed voice kept on reinstall" "$(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi
uninstall
if cmp -s "$D/before.conf" "$D/etc/speechd.conf" && [ ! -e "$D/modules/sd_brailab" ] && [ ! -e "$D/prefix/share/brailab" ] \
        && [ ! -e "$D/etc/modules/brailab.conf" ]; then
    ok "uninstall (stock)" "config as before; module, settings and data gone"
else fail "uninstall (stock)" "$(ls "$D/modules" "$D/prefix/share" 2>&1 | tr '\n' ' ')"; fi

# 2b. the same over HTTP, from a server on this machine: the way a real install fetches it
fresh http "$STOCK"
PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
( cd "$REL" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 ) > "$T/http.log" 2>&1 &
SERVER=$!
for i in 1 2 3 4 5 6 7 8 9 10; do
    python3 -c "import socket; socket.create_connection(('127.0.0.1', $PORT), 1)" 2>/dev/null && break
    sleep 0.3
done
install "http://127.0.0.1:$PORT" --with-tts
kill $SERVER 2>/dev/null
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa,BraiLab TTS" ]; then ok "--with-tts over HTTP" "$(voices)"
else fail "--with-tts over HTTP" "$(voices) | $(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi

# 3. the download going wrong, three ways: the voice is left out, the installer succeeds, two voices work
for c in "badsum:file://$T/release-badsum:checksum" "nowhere:file://$T/nowhere:did not work" "refused:http://127.0.0.1:9:did not work"; do
    name="${c%%:*}"; rest="${c#*:}"; base="${rest%:*}"; say="${rest##*:}"
    fresh "$name" "$STOCK"
    if install "$base" --with-tts && grep -q "$say" "$D/install.log" && [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa" ]; then
        ok "failed download: $name" "left out; the BraiLab PC voices installed"
    else fail "failed download: $name" "$(voices) | $(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi
done

# 4. --without-tts never fetches; --tts-file installs from a file; a file that is no package is refused
fresh without "$STOCK"
install "file://$REL" --without-tts
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa" ]; then ok "--without-tts" "$(voices)"
else fail "--without-tts" "$(voices)"; fi
install "file://$T/nowhere" --tts-file "$REL/brailab-tts-plugin-linux-$ARCH.tar.gz"
if [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa,BraiLab TTS" ]; then ok "--tts-file" "$(voices)"
else fail "--tts-file" "$(voices) | $(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi
fresh notpackage "$STOCK"
if install "file://$T/nowhere" --tts-file "$PKG/install.sh" && [ "$(voices)" = "BraiLab PC,BraiLab PC furcsa" ]; then
    ok "--tts-file with another file" "refused; two voices"
else fail "--tts-file with another file" "$(voices) | $(grep 'TTS' "$D/install.log" | tr '\n' ' ')"; fi

# 5. a config that lists its modules: this one listed too, once, the others untouched
fresh listed "$LISTED"
install "file://$REL"
install "file://$REL"
if [ "$(active)" = 1 ] && grep -q '^AddModule "espeak-ng"' "$D/etc/speechd.conf"; then
    ok "listed config: this module listed too" "once, after two installs; espeak-ng kept"
else fail "listed config: this module listed too" "$(tr '\n' '|' < "$D/etc/speechd.conf")"; fi
uninstall
if cmp -s "$D/before.conf" "$D/etc/speechd.conf"; then ok "uninstall (listed)" "config as before"
else fail "uninstall (listed)" "$(diff "$D/before.conf" "$D/etc/speechd.conf" | tr '\n' ' ')"; fi

# 6. --default on a stock config, twice: DefaultModule once, no AddModule; uninstall restores the old default
fresh default "$STOCK"
install "file://$REL" --default
install "file://$REL" --default
if [ "$(grep -c '^DefaultModule brailab$' "$D/etc/speechd.conf")" = 1 ] && [ "$(active)" = 0 ] \
        && [ "$(grep -c '^# (before brailab) DefaultModule espeak-ng' "$D/etc/speechd.conf")" = 1 ]; then
    ok "--default" "DefaultModule brailab once, no AddModule"
else fail "--default" "$(tr '\n' '|' < "$D/etc/speechd.conf")"; fi
uninstall
if cmp -s "$D/before.conf" "$D/etc/speechd.conf"; then ok "uninstall (--default)" "the old default back"
else fail "uninstall (--default)" "$(diff "$D/before.conf" "$D/etc/speechd.conf" | tr '\n' ' ')"; fi

if [ $FAIL = 0 ]; then echo "install: all passed"; else echo "install: FAILED"; exit 1; fi
