#!/bin/sh
# Remove what install.sh added: the module, its settings, the data folder (the BraiLab TTS voice with it), and the
# module's lines in speechd.conf (a DefaultModule install.sh commented out is restored).  Your own settings file,
# ~/.config/brailab/sd_brailab.conf, is yours and stays.
#
#   sudo ./uninstall.sh            (PREFIX as at install time)
set -e
PREFIX="${PREFIX:-/usr/local}"
USER_HOME="$HOME"
[ -n "$SUDO_USER" ] && USER_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
for CONF in ${BRAILAB_SPD_CONF:-"$USER_HOME/.config/speech-dispatcher/speechd.conf" /etc/speech-dispatcher/speechd.conf}; do
    [ -f "$CONF" ] || continue
    if grep -q 'brailab' "$CONF"; then
        sed -i -e '/^# --- the BraiLab voices (brailab install.sh) ---$/d' \
               -e '/^[[:space:]]*AddModule[[:space:]]*"brailab"/d' -e '/^DefaultModule brailab$/d' \
               -e 's/^# (before brailab) DefaultModule/DefaultModule/' "$CONF"
        echo "cleaned $CONF"
    fi
    rm -f "$(dirname "$CONF")/modules/brailab.conf"
done
for d in ${BRAILAB_SPD_MODULES:-/usr/lib/speech-dispatcher-modules /usr/lib/*/speech-dispatcher-modules \
         /usr/libexec/speech-dispatcher-modules}; do
    rm -f "$d/sd_brailab"
done
rm -rf "$PREFIX/share/brailab"
echo "Removed.  Restart speech-dispatcher: killall speech-dispatcher"
