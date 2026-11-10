# -*- coding: utf-8 -*-
"""The add-on speaks English and Hungarian: gettext catalogs under locale/.

The driver reads its catalog itself (see _loadTranslation in brailab.py), since
on 64-bit NVDA it runs in the bridge host, where addonHandler cannot find it.
"""
import gettext
import importlib.util
import os
import re
import sys
import types

import pytest

from test_pitch_path import driverModule  # noqa: F401  (a fixture)

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
PO = os.path.join(ADDON, "locale", "hu", "LC_MESSAGES", "nvda.po")
MO = os.path.join(ADDON, "locale", "hu", "LC_MESSAGES", "nvda.mo")

HUNGARIAN = {
    "Hungarian": "magyar",
    "&Use intonation": "Hanglejtés &használata",
    "&Gentler comma intonation": "S&zelídebb hanglejtés vesszőnél",
}


def _build():
    spec = importlib.util.spec_from_file_location("brailab_addon_build", os.path.join(ADDON, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _withLanguage(brailab, lang):
    """What _loadTranslation gives when NVDA's language is `lang`."""
    had = sys.modules.get("languageHandler")
    lh = types.ModuleType("languageHandler")
    lh.getLanguage = lambda: lang
    sys.modules["languageHandler"] = lh
    try:
        return brailab._loadTranslation()
    finally:
        if had is None:
            del sys.modules["languageHandler"]
        else:
            sys.modules["languageHandler"] = had


def test_every_string_in_the_driver_has_a_hungarian_translation():
    with open(os.path.join(ADDON, "synthDrivers", "brailab.py"), encoding="utf-8") as f:
        used = set(re.findall(r'\b_\("([^"]+)"\)', f.read()))
    assert used == set(HUNGARIAN), "update the .po and this test together"
    assert dict(p for p in _build().parse_po(PO) if p[0]) == HUNGARIAN


def test_the_committed_mo_is_what_the_po_compiles_to(tmp_path):
    fresh = tmp_path / "nvda.mo"
    _build().compile_mo(PO, str(fresh))
    with open(MO, "rb") as f:
        assert f.read() == fresh.read_bytes(), "run build.py after editing the .po"


def test_python_gettext_reads_the_catalog():
    with open(MO, "rb") as f:
        catalog = gettext.GNUTranslations(f)
    for english, hungarian in HUNGARIAN.items():
        assert catalog.gettext(english) == hungarian


@pytest.mark.parametrize("lang", ["hu", "hu_HU"])
def test_hungarian_nvda_gets_hungarian(driverModule, lang):
    tr = _withLanguage(driverModule[0], lang)
    assert tr("&Gentler comma intonation") == "S&zelídebb hanglejtés vesszőnél"


@pytest.mark.parametrize("lang", ["en", "de", "", None])
def test_any_other_language_gets_english(driverModule, lang):
    tr = _withLanguage(driverModule[0], lang)
    assert tr("&Gentler comma intonation") == "&Gentler comma intonation"


def test_without_languageHandler_the_driver_still_loads_in_english(driverModule):
    assert "languageHandler" not in sys.modules
    assert driverModule[0]._loadTranslation()("&Use intonation") == "&Use intonation"


def test_the_manifests_are_english_with_a_hungarian_override():
    def read(path):
        # NVDA reads manifests with configobj; the keys used here are plain key = value.
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return {k: v.strip().strip('"') for k, v in re.findall(r'(?m)^(\w+)\s*=\s*(.+)$', text)}
    base = read(os.path.join(ADDON, "manifest.ini"))
    hu = read(os.path.join(ADDON, "locale", "hu", "manifest.ini"))
    assert base["name"] == "BraiLab PC Beszédszintetizátor", "the add-on's identity must not change"
    assert "Hungarian speech synthesizer" in base["summary"]
    assert set(hu) == {"summary", "description"}
    assert "beszédszintetizátor" in hu["summary"]
