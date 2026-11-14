#!/bin/sh
# Install the BraiLab voices for speech-dispatcher (Orca, spd-say).  Run from the unpacked package:
#
#   sudo ./install.sh                  add the voices; your default synthesizer stays as it is
#   sudo ./install.sh --default        and make it the default
#   sudo ./install.sh --with-tts       also fetch and install the BraiLab TTS voice, without asking
#   sudo ./install.sh --without-tts    never ask, never fetch
#   sudo ./install.sh --tts-file F     install the BraiLab TTS voice from a file you already have
#   PREFIX=/opt/brailab sudo -E ./install.sh
#
# The package holds the BraiLab PC voices ("BraiLab PC", "BraiLab PC furcsa").  The third voice, "BraiLab TTS", is
# an optional binary plug-in of about 100 KB, a separate download from the same release this package came from.
# Run at a terminal with neither option, the installer asks; with no terminal it does not fetch.  Whatever
# happens to the download, the BraiLab PC voices are installed first and stay.  Run it again any time to add
# the voice later.
#
# speech-dispatcher finds the module by itself: with no AddModule line in speechd.conf it loads every module in
# its modules folder, and one AddModule line turns that off for all the others.  So speechd.conf is left alone,
# except: a config that already lists its modules (autodiscovery off, as Raspberry Pi OS ships it) gets a line for
# this one too, or it would never load; and --default sets DefaultModule.  ./uninstall.sh undoes it all.
#
# BRAILAB_TTS_BASE names another place to fetch the voice from: a web address, or a folder on this machine (a USB
# stick, say) holding the file and its .sha256.  For tests, BRAILAB_SPD_MODULES and BRAILAB_SPD_CONF point the
# installer at other folders (test_install.sh).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
DATA="$PREFIX/share/brailab"
PLUGIN_LIB=libbrailab_tts.so
MARK='# --- the BraiLab voices (brailab install.sh) ---'

MAKE_DEFAULT=0
TTS=ask
TTS_FILE=
while [ $# -gt 0 ]; do
    case "$1" in
        --default) MAKE_DEFAULT=1 ;;
        --with-tts) TTS=yes ;;
        --without-tts) TTS=no ;;
        --tts-file) TTS=file; TTS_FILE="$2"; shift ;;
        *) echo "unknown option: $1"; exit 2 ;;
    esac
    shift
done

MODBIN="${BRAILAB_SPD_MODULES:-}"
if [ -z "$MODBIN" ]; then             # Debian/Ubuntu, multiarch, Fedora/Arch
    for d in /usr/lib/speech-dispatcher-modules /usr/lib/*/speech-dispatcher-modules \
             /usr/libexec/speech-dispatcher-modules; do
        [ -d "$d" ] && { MODBIN="$d"; break; }
    done
    MODBIN="${MODBIN:-/usr/lib/speech-dispatcher-modules}"
fi
USER_HOME="$HOME"
[ -n "$SUDO_USER" ] && USER_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
if [ -n "$BRAILAB_SPD_CONF" ]; then
    CONF="$BRAILAB_SPD_CONF"
    MODCONF="$(dirname "$CONF")/modules"
elif [ -f "$USER_HOME/.config/speech-dispatcher/speechd.conf" ]; then
    CONF="$USER_HOME/.config/speech-dispatcher/speechd.conf"
    MODCONF="$USER_HOME/.config/speech-dispatcher/modules"
elif [ -f /etc/speech-dispatcher/speechd.conf ]; then
    CONF=/etc/speech-dispatcher/speechd.conf
    MODCONF=/etc/speech-dispatcher/modules
else
    echo "speech-dispatcher's speechd.conf was not found (is speech-dispatcher installed?)"
    exit 1
fi
[ -d "$MODBIN" ] || { echo "$MODBIN not found: where does your speech-dispatcher keep its modules?"; exit 1; }

# ---- the BraiLab PC voices: everything in the package -------------------------------------------------------------
echo "Installing the BraiLab voices"
mkdir -p "$DATA" "$MODCONF"
[ -f "$HERE/share/brailab/TALKHUN0.COM" ] || { echo "the package has no share/brailab/TALKHUN0.COM"; exit 1; }
for f in "$HERE"/share/brailab/*; do                          # the files; the speech-dispatcher folder is not data
    [ -f "$f" ] && cp "$f" "$DATA/"
done
if [ -d "$HERE/licenses" ]; then
    mkdir -p "$DATA/licenses"
    cp "$HERE"/licenses/* "$DATA/licenses/"
fi
cp "$HERE/bin/sd_brailab" "$MODBIN/sd_brailab"
chmod 755 "$MODBIN/sd_brailab"
{
    cat "$HERE/share/brailab/speech-dispatcher/brailab.conf"
    echo "BrailabDataDir \"$DATA\""
} > "$MODCONF/brailab.conf"
echo "  module:   $MODBIN/sd_brailab"
echo "  settings: $MODCONF/brailab.conf"
echo "  data:     $DATA"

if grep -q -e '^[[:space:]]*AddModule[[:space:]]*"brailab"' -e "^$MARK\$" "$CONF"; then   # an earlier run's lines
    sed -i -e "\\|^$MARK\$|d" -e '/^[[:space:]]*AddModule[[:space:]]*"brailab"/d' "$CONF"
fi
if grep -q '^[[:space:]]*AddModule[[:space:]]' "$CONF"; then
    # the config lists its modules itself (autodiscovery is off): this one must be listed too, or it never loads
    [ -n "$(tail -c1 "$CONF")" ] && echo >> "$CONF"
    printf '%s\nAddModule "brailab" "sd_brailab" "brailab.conf"\n' "$MARK" >> "$CONF"
    echo "  $CONF lists its modules itself: added this one to the list"
else
    echo "  speech-dispatcher finds the module by itself ($CONF unchanged)"
fi
if [ $MAKE_DEFAULT -eq 1 ]; then
    if ! grep -q '^DefaultModule brailab$' "$CONF"; then
        if grep -q '^DefaultModule' "$CONF"; then
            sed -i 's/^DefaultModule/# (before brailab) DefaultModule/' "$CONF"
        fi
        echo "DefaultModule brailab" >> "$CONF"
    fi
    echo "  made the default synthesizer"
fi
if [ -n "$SUDO_USER" ] && [ "$CONF" != "/etc/speech-dispatcher/speechd.conf" ]; then
    chown "$SUDO_USER" "$CONF" "$MODCONF/brailab.conf"
fi

# ---- the BraiLab TTS voice: the optional plug-in ------------------------------------------------------------------
# From a file, or fetched from the release this package was made for (share/brailab/release-tag), never from
# "the latest release": this repository's releases are of several kinds, and the latest need not have it.
install_tts() {     # install_tts ARCHIVE: unpack, check it is what it says, copy into the data folder
    work="$(mktemp -d)"
    if ! tar -xzf "$1" -C "$work" 2>/dev/null; then
        echo "  BraiLab TTS: $1 is not a package of the voice; left out"
        rm -rf "$work"
        return 1
    fi
    dir="$(dirname "$(find "$work" -name "$PLUGIN_LIB" | head -n 1)")"
    if [ ! -f "$dir/$PLUGIN_LIB" ]; then
        echo "  BraiLab TTS: no $PLUGIN_LIB in $1; left out"
        rm -rf "$work"
        return 1
    fi
    for f in "$dir"/*; do
        [ -f "$f" ] && cp "$f" "$DATA/"
    done
    chmod 644 "$DATA/$PLUGIN_LIB"
    rm -rf "$work"
    echo "  BraiLab TTS: installed in $DATA"
}

fetch() {           # fetch URL FILE: a folder on this machine is copied from; else whichever of curl and wget is here
    case "$1" in
        file://*) cp "${1#file://}" "$2" 2>/dev/null; return $? ;;
        /*) cp "$1" "$2" 2>/dev/null; return $? ;;
    esac
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 15 -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -T 15 -O "$2" "$1"
    else
        echo "  BraiLab TTS: neither curl nor wget is installed"
        return 1
    fi
}

fetch_tts() {
    arch="$(uname -m)"
    case "$arch" in arm64) arch=aarch64 ;; amd64) arch=x86_64 ;; esac
    name="brailab-tts-plugin-linux-$arch.tar.gz"
    base="${BRAILAB_TTS_BASE:-}"
    if [ -z "$base" ]; then
        tag="$(cat "$HERE/share/brailab/release-tag" 2>/dev/null || true)"
        if [ -z "$tag" ]; then
            echo "  BraiLab TTS: this package does not say which release it belongs to; use --tts-file"
            return 1
        fi
        base="https://github.com/tgeczy/Brailab-wrapper/releases/download/$tag"
    fi
    work="$(mktemp -d)"
    echo "  BraiLab TTS: fetching $base/$name"
    if ! fetch "$base/$name" "$work/$name" || ! fetch "$base/$name.sha256" "$work/$name.sha256"; then
        echo "  BraiLab TTS: the download did not work (no network, or no build for $arch); left out"
        rm -rf "$work"
        return 1
    fi
    want="$(cut -d' ' -f1 "$work/$name.sha256")"
    got="$(sha256sum "$work/$name" | cut -d' ' -f1)"
    if [ -z "$want" ] || [ "$want" != "$got" ]; then
        echo "  BraiLab TTS: the download does not match its checksum; left out"
        rm -rf "$work"
        return 1
    fi
    install_tts "$work/$name"
    ret=$?
    rm -rf "$work"
    return $ret
}

if [ -f "$DATA/$PLUGIN_LIB" ] && [ "$TTS" = ask ]; then
    echo "  BraiLab TTS: already installed (kept)"
    TTS=no
fi
if [ "$TTS" = ask ]; then
    if [ -t 0 ]; then
        printf 'Also install the BraiLab TTS voice (a download of about 100 KB)? [y/N] '
        read -r answer || answer=
        case "$answer" in y|Y|yes|i|I|igen) TTS=yes ;; *) TTS=no ;; esac
    else
        TTS=no
    fi
fi
case "$TTS" in
    file) install_tts "$TTS_FILE" || true ;;
    yes) fetch_tts || true ;;
esac
[ -f "$DATA/$PLUGIN_LIB" ] || echo "  BraiLab TTS: not installed (add it later with: sudo ./install.sh --with-tts)"

cat <<EOF

Done.  Restart speech-dispatcher so it sees the voices (Orca reconnects by itself):
    killall speech-dispatcher
Try it:
    spd-say -o brailab "Jó napot kívánok"
    spd-say -o brailab -L          (the voices)
In Orca: Preferences, Speech, Speech synthesizer: brailab, then the voice.
The settings are explained in $MODCONF/brailab.conf; your own copy of any line in
~/.config/brailab/sd_brailab.conf wins over it.
EOF
