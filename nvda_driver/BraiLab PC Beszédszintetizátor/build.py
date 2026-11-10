#!/usr/bin/env python3
"""Package the Brailab NVDA addon as a .nvda-addon file (ZIP archive).

Also compiles every locale/<language>/LC_MESSAGES/nvda.po to nvda.mo, the form
gettext reads, so no GNU gettext tools are needed.  Run it after editing a .po.
"""

import os
import re
import struct
import sys
import zipfile

if sys.version_info < (3, 0):
	raise Exception("Python 3 required")

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
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

	# 32-bit wrapper DLL
	"synthDrivers/brailab_wrapper.dll": os.path.join(SYNTH_DIR, "brailab_wrapper.dll"),

	# Brailab engine files
	"synthDrivers/Brailab/TTS.dll": os.path.join(SYNTH_DIR, "Brailab", "TTS.dll"),
	"synthDrivers/Brailab/BINADATA.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINADATA.BIN"),
	"synthDrivers/Brailab/BINAHANK.BIN": os.path.join(SYNTH_DIR, "Brailab", "BINAHANK.BIN"),
}


# --- .po -> .mo, as `msgfmt -o nvda.mo nvda.po` would ---

def _unescape(s):
	s = s.replace("\\\\", "\x00BS\x00")
	s = s.replace("\\n", "\n")
	s = s.replace("\\t", "\t")
	s = s.replace('\\"', '"')
	return s.replace("\x00BS\x00", "\\")


def parse_po(path):
	"""[(msgid, msgstr), ...], the header entry (empty msgid) included."""
	with open(path, "r", encoding="utf-8") as f:
		content = f.read()
	pairs = []
	for block in re.split(r"\n\n+", content):
		ids, strs, cur = [], [], None
		for line in block.strip().split("\n"):
			line = line.strip()
			if line.startswith("#"):
				continue
			if line.startswith("msgid "):
				cur, value = "id", line[6:].strip()
			elif line.startswith("msgstr "):
				cur, value = "str", line[7:].strip()
			else:
				value = line
			if cur and value.startswith('"') and value.endswith('"'):
				(ids if cur == "id" else strs).append(value[1:-1])
		if ids or strs:
			pairs.append((_unescape("".join(ids)), _unescape("".join(strs))))
	return pairs


def compile_mo(po_path, mo_path):
	"""Write mo_path from po_path; returns the number of entries."""
	# An untranslated entry must be left out, or gettext would return "".
	pairs = [p for p in parse_po(po_path) if p[1]]
	pairs.sort(key=lambda p: p[0].encode("utf-8"))
	n = len(pairs)
	originals = [p[0].encode("utf-8") for p in pairs]
	translations = [p[1].encode("utf-8") for p in pairs]
	header = 28
	offset = header + n * 16
	table = []
	for group in (originals, translations):
		for s in group:
			table.append((len(s), offset))
			offset += len(s) + 1
	out = bytearray(struct.pack("<7I", 0x950412DE, 0, n, header, header + n * 8, 0, 0))
	for length, where in table:
		out += struct.pack("<II", length, where)
	for s in originals + translations:
		out += s + b"\x00"
	with open(mo_path, "wb") as f:
		f.write(bytes(out))
	return n


def compile_locales():
	"""Compile every nvda.po; return {archive name: path} of all locale files."""
	files = {}
	if not os.path.isdir(LOCALE_DIR):
		return files
	for lang in sorted(os.listdir(LOCALE_DIR)):
		lang_dir = os.path.join(LOCALE_DIR, lang)
		po = os.path.join(lang_dir, "LC_MESSAGES", "nvda.po")
		mo = os.path.join(lang_dir, "LC_MESSAGES", "nvda.mo")
		if os.path.isfile(po):
			n = compile_mo(po, mo)
			print(f"  locale {lang}: {n} entries -> nvda.mo")
			files[f"locale/{lang}/LC_MESSAGES/nvda.mo"] = mo
			files[f"locale/{lang}/LC_MESSAGES/nvda.po"] = po
		manifest = os.path.join(lang_dir, "manifest.ini")
		if os.path.isfile(manifest):
			files[f"locale/{lang}/manifest.ini"] = manifest
	return files


def main():
	print("Compiling translations...")
	files = dict(ADDON_FILES)
	files.update(compile_locales())

	missing = []
	for arc_name, src_path in files.items():
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
