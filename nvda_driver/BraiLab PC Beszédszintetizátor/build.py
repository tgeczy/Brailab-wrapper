#!/usr/bin/env python3
"""Package the Brailab NVDA addon as a .nvda-addon file (ZIP archive).

Also compiles every locale/<language>/LC_MESSAGES/nvda.po to nvda.mo, the form
gettext reads, so no GNU gettext tools are needed.  Run it after editing a .po.
"""

import os
import sys
import zipfile

if sys.version_info < (3, 0):
	raise Exception("Python 3 required")

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ADDON_DIR))
from po2mo import compile_locales, compile_mo, parse_po  # noqa: E402,F401  (the tests use these too)

SYNTH_DIR = os.path.join(ADDON_DIR, "synthDrivers")
LOCALE_DIR = os.path.join(ADDON_DIR, "locale")
OUTPUT_NAME = "brailab.nvda-addon"
OUTPUT_PATH = os.path.join(ADDON_DIR, OUTPUT_NAME)

# Files to include in the addon
ADDON_FILES = {
	# Root addon files
	"manifest.ini": os.path.join(ADDON_DIR, "manifest.ini"),

	# SynthDriver Python files
	"synthDrivers/brailab.py": os.path.join(SYNTH_DIR, "brailab.py"),
	"synthDrivers/_brailab.py": os.path.join(SYNTH_DIR, "_brailab.py"),
	# the first feed, and indexes with no audio behind them (shared with the emulated driver)
	"synthDrivers/brailab_feed.py": os.path.join(os.path.dirname(ADDON_DIR), "brailab_feed.py"),

	# 32-bit wrapper DLL
	"synthDrivers/brailab_wrapper.dll": os.path.join(SYNTH_DIR, "brailab_wrapper.dll"),

	# Brailab engine files
	"synthDrivers/Brailab/TTS.dll": os.path.join(SYNTH_DIR, "Brailab", "TTS.dll"),
	"synthDrivers/Brailab/BINADATA.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINADATA.BIN"),
	"synthDrivers/Brailab/BINAHANK.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINAHANK.BIN"),
}


def main():
	print("Compiling translations...")
	files = dict(ADDON_FILES)
	files.update(compile_locales(LOCALE_DIR))

	missing = []
	for arc_name, src_path in files.items():
		if not os.path.exists(src_path):
			missing.append((arc_name, src_path))

	if missing:
		print("WARNING: Missing files:")
		for arc_name, src_path in missing:
			print(f"  {arc_name} -> {src_path}")
		print()

	# Every file is required: an add-on without the wrapper, TTS.dll or one of its
	# two data files loads and then says nothing (#6), so none is built.
	if missing:
		print("ERROR: not building an add-on that cannot speak; the files above are missing")
		sys.exit(1)

	print(f"Creating {OUTPUT_NAME}...")
	with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
		for arc_name, src_path in files.items():
			if os.path.exists(src_path):
				zf.write(src_path, arc_name)
				size = os.path.getsize(src_path)
				print(f"  + {arc_name} ({size:,} bytes)")
			else:
				print(f"  - {arc_name} (SKIPPED - not found)")

	print(f"\nCreated {OUTPUT_PATH}")
	print(f"Size: {os.path.getsize(OUTPUT_PATH):,} bytes")


if __name__ == "__main__":
	main()
