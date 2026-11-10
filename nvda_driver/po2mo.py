# -*- coding: utf-8 -*-
"""Compile gettext .po files to .mo, as `msgfmt -o nvda.mo nvda.po` would.

Both NVDA add-ons' build scripts use this, so neither needs GNU gettext.  It
handles what our catalogs contain: plain msgid/msgstr pairs, no plurals and no
contexts.
"""
import os
import re
import struct


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


def mo_bytes(pairs):
    """The .mo file for these (msgid, msgstr) pairs."""
    # An untranslated entry must be left out, or gettext would return "".
    pairs = sorted((p for p in pairs if p[1]), key=lambda p: p[0].encode("utf-8"))
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
    return bytes(out)


def compile_mo(po_path, mo_path):
    """Write mo_path from po_path; returns the number of translated entries, header included."""
    pairs = parse_po(po_path)
    with open(mo_path, "wb") as f:
        f.write(mo_bytes(pairs))
    return len([p for p in pairs if p[1]])


def compile_locales(locale_dir):
    """Compile every <language>/LC_MESSAGES/nvda.po under locale_dir.

    Returns {path relative to the add-on, with forward slashes: file path} for
    everything a package should carry: each .mo, its .po, and translated manifests.
    """
    files = {}
    if not os.path.isdir(locale_dir):
        return files
    for lang in sorted(os.listdir(locale_dir)):
        lang_dir = os.path.join(locale_dir, lang)
        po = os.path.join(lang_dir, "LC_MESSAGES", "nvda.po")
        mo = os.path.join(lang_dir, "LC_MESSAGES", "nvda.mo")
        if os.path.isfile(po):
            compile_mo(po, mo)
            files["locale/%s/LC_MESSAGES/nvda.mo" % lang] = mo
            files["locale/%s/LC_MESSAGES/nvda.po" % lang] = po
        manifest = os.path.join(lang_dir, "manifest.ini")
        if os.path.isfile(manifest):
            files["locale/%s/manifest.ini" % lang] = manifest
    return files
