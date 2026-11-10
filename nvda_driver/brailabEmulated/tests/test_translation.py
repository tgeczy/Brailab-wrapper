# -*- coding: utf-8 -*-
"""The emulated add-on in English and Hungarian.

The driver calls addonHandler.initTranslation(), as NVDA add-ons do.  The fake
below does what NVDA's own does (addonHandler/__init__.py: getTranslationsInstance
and initTranslation): gettext.translation("nvda", <add-on>/locale, [NVDA's
language], fallback=True), installed as `_` in the calling module.
"""
import gettext
import importlib.util
import os
import re
import sys
import types

import pytest

import conftest

pytestmark = pytest.mark.skipif(not conftest.STAGED,
                                reason="needs TALKHUN0.COM and the built talkhun.dll")

SRC = conftest.ADDON_SRC
PO = os.path.join(SRC, "locale", "hu", "LC_MESSAGES", "nvda.po")
STAGED_MO = os.path.join(conftest.STAGE, "locale", "hu", "LC_MESSAGES", "nvda.mo")

HUNGARIAN = {
    "Brailab PC (emulated, PCF8200)": "Brailab PC (emulált, PCF8200)",
    "Brailab PC (emulated, C test)": "Brailab PC (emulált, C teszt)",
    "&Furcsa (weird voice)": "&Furcsa hang",
    "&Use intonation": "Hanglejtés &használata",
}


def _load_with_language(lang):
    """A second copy of the staged driver, loaded while NVDA's language is `lang`."""
    def initTranslation():
        catalog = gettext.translation("nvda", localedir=os.path.join(conftest.STAGE, "locale"),
                                      languages=[lang], fallback=True)
        sys._getframe(1).f_globals["_"] = catalog.gettext

    had = sys.modules.get("addonHandler")
    fake = types.ModuleType("addonHandler")
    fake.initTranslation = initTranslation
    sys.modules["addonHandler"] = fake
    try:
        import synthDrivers  # noqa: F401  (the package conftest staged)
        name = "synthDrivers.brailabEmulated_%s" % lang
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(conftest.STAGE, "synthDrivers", "brailabEmulated.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            del sys.modules[name]
        return module
    finally:
        if had is None:
            del sys.modules["addonHandler"]
        else:
            sys.modules["addonHandler"] = had


def _labels(module):
    return {s.id: s.displayName for s in module.SynthDriver.supportedSettings
            if s.id in ("furcsa", "useIntonation")}


def test_every_string_in_the_driver_has_a_hungarian_translation():
    with open(os.path.join(SRC, "synthDrivers", "brailabEmulated.py"), encoding="utf-8") as f:
        used = set(re.findall(r'\b_\("([^"]+)"\)', f.read()))
    # the test build renames the description; its string is translated as well
    assert used | {"Brailab PC (emulated, C test)"} == set(HUNGARIAN)
    sys.path.insert(0, os.path.dirname(SRC))
    import po2mo
    assert dict(p for p in po2mo.parse_po(PO) if p[0]) == HUNGARIAN, "update the .po and this test together"


def test_the_staged_add_on_carries_a_catalog_gettext_can_read():
    with open(STAGED_MO, "rb") as f:
        catalog = gettext.GNUTranslations(f)
    for english, hungarian in HUNGARIAN.items():
        assert catalog.gettext(english) == hungarian


def test_hungarian_nvda_shows_hungarian():
    module = _load_with_language("hu")
    assert module.SynthDriver.description == "Brailab PC (emulált, PCF8200)"
    assert _labels(module) == {"furcsa": "&Furcsa hang", "useIntonation": "Hanglejtés &használata"}


def test_another_language_shows_english():
    module = _load_with_language("de")
    assert module.SynthDriver.description == "Brailab PC (emulated, PCF8200)"
    assert _labels(module) == {"furcsa": "&Furcsa (weird voice)", "useIntonation": "&Use intonation"}


def test_without_addonHandler_it_still_loads_in_english():
    """How the other tests load it: no add-on registry at all."""
    from synthDrivers import brailabEmulated
    assert _labels(brailabEmulated) == {"furcsa": "&Furcsa (weird voice)", "useIntonation": "&Use intonation"}


def test_the_hungarian_manifest_overrides_only_what_nvda_translates():
    with open(os.path.join(conftest.STAGE, "locale", "hu", "manifest.ini"), encoding="utf-8") as f:
        keys = re.findall(r"(?m)^(\w+)\s*=", f.read())
    # NVDA takes summary, description and changelog from a translated manifest, nothing else.
    assert keys == ["summary", "description"]


def test_the_test_build_is_hungarian_too(tmp_path):
    """build.py --test renames the add-on; a Hungarian NVDA must still get Hungarian."""
    sys.path.insert(0, SRC)
    import build
    stage = str(tmp_path / "stage")
    manifest = build.read(os.path.join(SRC, "manifest.ini"))
    driver = build.read(os.path.join(SRC, "synthDrivers", "brailabEmulated.py")).replace(
        '"Brailab PC (emulated, PCF8200)"', '"Brailab PC (emulated, C test)"')
    build.lay_out(stage, "brailabEmulatedC", build.ENGINE + "_test", manifest, driver)
    hu = build.read(os.path.join(stage, "locale", "hu", "manifest.ini"))
    assert 'summary = "BraiLab PC (emulált, C teszt)"' in hu
    staged = build.read(os.path.join(stage, "synthDrivers", "brailabEmulatedC.py"))
    assert '_("Brailab PC (emulated, C test)")' in staged
    with open(os.path.join(stage, "locale", "hu", "LC_MESSAGES", "nvda.mo"), "rb") as f:
        assert gettext.GNUTranslations(f).gettext("Brailab PC (emulated, C test)") == "Brailab PC (emulált, C teszt)"
