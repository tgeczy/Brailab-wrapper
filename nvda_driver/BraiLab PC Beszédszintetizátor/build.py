#!/usr/bin/env python3
"""Package the Brailab NVDA addon as a .nvda-addon file (ZIP archive)."""

import os
import sys
import zipfile

if sys.version_info < (3, 0):
	raise Exception("Python 3 required")

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
SYNTH_DIR = os.path.join(ADDON_DIR, "synthDrivers")
OUTPUT_NAME = "brailab.nvda-addon"
OUTPUT_PATH = os.path.join(ADDON_DIR, OUTPUT_NAME)

# Files to include in the addon
ADDON_FILES = {
	# Root addon files
	"manifest.ini": os.path.join(ADDON_DIR, "manifest.ini"),

	# SynthDriver Python files
	"synthDrivers/brailab.py": os.path.join(SYNTH_DIR, "brailab.py"),
	"synthDrivers/_brailab.py": os.path.join(SYNTH_DIR, "_brailab.py"),

	# 32-bit wrapper DLL
	"synthDrivers/brailab_wrapper.dll": os.path.join(SYNTH_DIR, "brailab_wrapper.dll"),

	# Brailab engine files
	"synthDrivers/Brailab/TTS.dll": os.path.join(SYNTH_DIR, "Brailab", "TTS.dll"),
	"synthDrivers/Brailab/BINADATA.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINADATA.BIN"),
	"synthDrivers/Brailab/BINAHANK.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINAHANK.BIN"),
}


def main():
	missing = []
	for arc_name, src_path in ADDON_FILES.items():
		if not os.path.exists(src_path):
			missing.append((arc_name, src_path))

	if missing:
		print("WARNING: Missing files:")
		for arc_name, src_path in missing:
			print(f"  {arc_name} -> {src_path}")
		print()

	# Only require the Python files and manifest to exist
	required = ["manifest.ini", "synthDrivers/brailab.py", "synthDrivers/_brailab.py"]
	for r in required:
		if r in [m[0] for m in missing]:
			print(f"ERROR: Required file missing: {r}")
			sys.exit(1)

	print(f"Creating {OUTPUT_NAME}...")
	with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
		for arc_name, src_path in ADDON_FILES.items():
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
