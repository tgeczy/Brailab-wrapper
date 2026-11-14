#!/bin/sh
# Package the Linux release for this machine's architecture: the speech-dispatcher module, TALKHUN0.COM, the
# installer and the licences.
#
#   ./build_linux.sh && tools/package_linux.sh <version> [release tag]
#
# The package is the BraiLab PC voices.  The BraiLab TTS voice is an optional binary plug-in that is not built
# from this repository and is not an input here: install.sh fetches it, when the user wants it, from the release
# named by the tag (default v<version>), which this script writes into the package.
# Output: build/brailab-<version>-linux-<arch>.tar.gz
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:?usage: tools/package_linux.sh <version> [release tag]}"
TAG="${2:-v$VERSION}"
ARCH="$(uname -m)"
NAME="brailab-$VERSION-linux-$ARCH"
STAGE="$ROOT/build/package/$NAME"
SD="$ROOT/src/platforms/speechd"

for f in "$ROOT/build/linux/sd_brailab" "$ROOT/third_party/brailab/TALKHUN0.COM"; do
    [ -f "$f" ] || { echo "missing: $f"; exit 1; }
done
rm -rf "$STAGE"
mkdir -p "$STAGE/bin" "$STAGE/share/brailab/speech-dispatcher" "$STAGE/licenses"
cp "$ROOT/build/linux/sd_brailab" "$STAGE/bin/"
cp "$ROOT/third_party/brailab/TALKHUN0.COM" "$STAGE/share/brailab/"
printf '%s\n' "$TAG" > "$STAGE/share/brailab/release-tag"
cp "$SD/brailab.conf" "$STAGE/share/brailab/speech-dispatcher/"
cp "$SD/install.sh" "$SD/uninstall.sh" "$STAGE/"
cp "$SD/README-linux.md" "$STAGE/README.md"
cp "$ROOT/LICENSE" "$STAGE/LICENSE"
cp "$ROOT/NOTICE.md" "$STAGE/licenses/NOTICE.md"
cp "$ROOT/src/talkhun_emu/csrc/cpu/mame_i86/LICENSE-BSD-3-Clause.txt" "$STAGE/licenses/MAME-8086-core-BSD-3-Clause.txt"
chmod 755 "$STAGE/install.sh" "$STAGE/uninstall.sh" "$STAGE/bin/sd_brailab"
(cd "$ROOT/build/package" && tar -czf "$ROOT/build/$NAME.tar.gz" "$NAME")
echo "packaged build/$NAME.tar.gz (the BraiLab TTS voice is fetched from release $TAG)"
