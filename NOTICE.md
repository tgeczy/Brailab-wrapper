# Notice: the BraiLab PC software in this repository and its releases

[English](#english) · [Magyarul](#magyarul)

---

## English

The code written for this project is under the MIT License (see `LICENSE`). The
files described below are **not** this project's work, and the MIT License does
not apply to them. Their copyright remains with their authors.

### TALKHUN, in `third_party/brailab/`

| File | Bytes | SHA-256 | What it is |
|---|---|---|---|
| `TALKHUN.COM` | 64,941 | `01ff78039a9e595857fe205c4f2b44e4dc12636a3c61b2622e294c1d024708cf` | The BraiLab PC screen reader and speech program for DOS, version 4 (the file of 20 June 2000), unmodified |
| `TALKHUN0.COM` | 45,301 | `f31442ad78d795c8d691775d53d8716375256dabda8bc26094290a80b9bb6fe1` | Version 2 of the same program, from 1991, unmodified |
| `TALKHUNS.COM` | 64,941 | `516a38c199166e788643636b24b0f8264cc9ee3327f5ce3be1fc9183bf744a24` | **A modified copy** of `TALKHUN.COM`, see below |

Each original file carries its authors' own notice:

- `TALKHUN.COM`: "BraiLab PC (c) 4. Vaspöri Teréz és Arató András munkája."
- `TALKHUN0.COM`: "BraiLab PC (c) 2. Vaspöri Teréz és Arató András munkája."

That is: BraiLab PC, the work of Vaspöri Teréz and Arató András. **The copyright
belongs to them.**

`TALKHUNS.COM` is made from `TALKHUN.COM` by `dos_speaker/patch_talkhun.py`,
which changes 11 bytes in three places, so that the signals TALKHUN sends to the
printer port go to this project's BRAISPK program instead of the BraiLab adapter.
BRAISPK then speaks them through the PC speaker or a sound card. The speech
rules, pronunciation and intonation are untouched. It is clearly marked as
modified, and the original is kept beside it.

### The software BraiLab (TTS.dll): only in release packages

`TTS.dll`, `BINADATA.BIN` and `BINAHANK.BIN` are **not** in this repository.
They are included only in this project's release packages, such as the NVDA
add-on, as the original authors' unmodified files:

| File | Bytes | SHA-256 |
|---|---|---|
| `TTS.dll` | 69,632 | `b8c9d50c65c1453a64f9ce14882d9d6ce9dd41969b4867c5b87126fe0beb08e8` |
| `BINADATA.BIN` | 61,984 | `a0e25f5ded6b9a339e08d5b4d3da4e99a58cf6872391a08c022e4f5a6a0a3171` |
| `BINAHANK.BIN` | 4,358 | `8f36ba9c609e49109d0a97775cb16ab02d3be642c136db25a5711ac7f54d8551` |

They are the work of the original authors of the BraiLab software, and their
copyright remains with those authors and their institutions. Their source code is
**not** distributed by this project. Where this project offers the voice of
TTS.dll on other platforms (for example Linux), it is produced from the same
speech data and rules, so that it speaks the same frames as TTS.dll on Windows;
those builds are likewise distributed in binary form only.

### Permissions

- **2009 and 2010.** Permission to use the software BraiLab with NVDA, as
  described publicly on nvda.hu in November 2010:
  <https://www.nvda.hu/2010/11/04/tts-allapotjelentes/>
- **August 2026.** Arató András and Vaspöri Teréz agreed to the BraiLab PC disk
  material being archived on the Internet Archive:
  <https://archive.org/details/brailab-pc-archive>
- **7 November 2026, 15:53 CET.** Géczy Tamás asked Arató András and Vaspöri
  Teréz in writing whether this project may, free of charge, for blind users and
  always under their names, with nothing sold:
  1. distribute the software BraiLab (`TTS.dll`, `BINADATA.BIN`, `BINAHANK.BIN`)
     as a Windows SAPI voice and on Linux;
  2. include `TALKHUN.COM` and `TALKHUN0.COM`, under their names, in this
     open-source repository and in free Linux and SAPI packages;
  3. distribute the modified TALKHUN, clearly marked as modified, beside the
     original;
  4. use the source code of TTS.dll, if it could be obtained.
- **8 November 2026, 10:05 CET.** Arató András answered yes to all of these in
  writing.

The correspondence is private and is not reproduced here; only its dates and
the questions asked are given.

### If you hold rights to any of this

If you are a rights holder, including an institution where this software was
developed, such as BME-TT or any other, and you disagree with this notice or
would like to see the details of the permission, please open an issue at
<https://github.com/tgeczy/Brailab-wrapper/issues>, or, if you would rather not
raise it in public, write to Géczy Tamás at the e-mail address on his GitHub
profile, <https://github.com/tgeczy>. We will answer promptly, and remove anything
you ask us to.

---

## Magyarul

A projekthez írt kód MIT-licenc alatt áll (lásd: `LICENSE`). Az alább felsorolt
fájlok **nem** a projekt munkái, és az MIT-licenc nem vonatkozik rájuk. A szerzői
jog a szerzőiké marad.

### A TALKHUN, a `third_party/brailab/` mappában

| Fájl | Bájt | SHA-256 | Mi ez |
|---|---|---|---|
| `TALKHUN.COM` | 64 941 | `01ff78039a9e595857fe205c4f2b44e4dc12636a3c61b2622e294c1d024708cf` | A BraiLab PC DOS-os képernyőolvasó és beszélőprogramja, 4. változat (a 2000. június 20-i fájl), változtatás nélkül |
| `TALKHUN0.COM` | 45 301 | `f31442ad78d795c8d691775d53d8716375256dabda8bc26094290a80b9bb6fe1` | Ugyanennek a programnak a 2. változata, 1991-ből, változtatás nélkül |
| `TALKHUNS.COM` | 64 941 | `516a38c199166e788643636b24b0f8264cc9ee3327f5ce3be1fc9183bf744a24` | A `TALKHUN.COM` **módosított másolata**, lásd lent |

Az eredeti fájlok mindegyikében ott áll a szerzők saját közleménye:

- `TALKHUN.COM`: „BraiLab PC (c) 4. Vaspöri Teréz és Arató András munkája.”
- `TALKHUN0.COM`: „BraiLab PC (c) 2. Vaspöri Teréz és Arató András munkája.”

**A szerzői jog őket illeti.**

A `TALKHUNS.COM` a `TALKHUN.COM`-ból készül a `dos_speaker/patch_talkhun.py`
programmal, amely három helyen összesen 11 bájtot változtat meg: így a TALKHUN
a nyomtatóportra küldött jeleit nem a BraiLab adapternek, hanem a projekt BRAISPK
programjának küldi, amely a PC hangszóróján vagy hangkártyán szólaltatja meg
őket. A beszéd szabályaihoz, a kiejtéshez és a hanglejtéshez nem nyúl.
Egyértelműen módosítottként van jelölve, és az eredeti mellette megtalálható.

### A szoftveres BraiLab (TTS.dll): csak a kiadási csomagokban

A `TTS.dll`, a `BINADATA.BIN` és a `BINAHANK.BIN` **nincs** ebben a tárolóban.
Csak a projekt kiadási csomagjaiban szerepelnek (például az NVDA-bővítményben),
az eredeti szerzők változatlan fájljaiként:

| Fájl | Bájt | SHA-256 |
|---|---|---|
| `TTS.dll` | 69 632 | `b8c9d50c65c1453a64f9ce14882d9d6ce9dd41969b4867c5b87126fe0beb08e8` |
| `BINADATA.BIN` | 61 984 | `a0e25f5ded6b9a339e08d5b4d3da4e99a58cf6872391a08c022e4f5a6a0a3171` |
| `BINAHANK.BIN` | 4 358 | `8f36ba9c609e49109d0a97775cb16ab02d3be642c136db25a5711ac7f54d8551` |

Ezek a szoftveres BraiLab eredeti szerzőinek munkái, a szerzői jog őket és
intézményeiket illeti. A forráskódjukat a projekt **nem** terjeszti. Ahol a
projekt a TTS.dll hangját más platformon (például Linuxon) is elérhetővé teszi,
azt ugyanabból a beszédadatból és ugyanazokkal a szabályokkal állítja elő, így
ugyanazokat a kereteket mondja ki, mint a windowsos TTS.dll; ezeket a
változatokat is csak lefordított formában terjesztjük.

### Engedélyek

- **2009 és 2010.** Engedély a szoftveres BraiLab NVDA-val való használatára,
  ahogyan az nvda.hu 2010. novemberi bejegyzése nyilvánosan leírja:
  <https://www.nvda.hu/2010/11/04/tts-allapotjelentes/>
- **2026. augusztus.** Arató András és Vaspöri Teréz hozzájárult, hogy a
  BraiLab PC lemezanyaga az Internet Archive-ra kerüljön:
  <https://archive.org/details/brailab-pc-archive>
- **2026. november 7., 15:53 (közép-európai idő).** Géczy Tamás írásban
  megkérdezte Arató Andrást és Vaspöri Terézt, hogy a projekt ingyenesen, a vak
  felhasználók számára, mindenhol az ő nevükkel és bármiféle értékesítés nélkül:
  1. terjesztheti-e a szoftveres BraiLabot (`TTS.dll`, `BINADATA.BIN`,
     `BINAHANK.BIN`) windowsos SAPI-hangként és Linuxon;
  2. bekerülhet-e a `TALKHUN.COM` és a `TALKHUN0.COM` az ő nevükkel ebbe a
     nyílt forrású tárolóba, valamint az ingyenes linuxos és SAPI-s csomagokba;
  3. terjesztheti-e a módosított TALKHUN-t, egyértelműen módosítottként
     jelölve, az eredeti mellett;
  4. felhasználhatja-e a TTS.dll forráskódját, ha az előkerül.
- **2026. november 8., 10:05 (közép-európai idő).** Arató András írásban
  mindegyik kérdésre igennel válaszolt.

A levelezés magánjellegű, ezért itt nem közöljük; csak a dátumokat és a feltett
kérdéseket adjuk meg.

### Ha Önt jogok illetik

Ha Ön jogtulajdonos, ideértve azt az intézményt is, ahol ez a szoftver készült,
például a BME-TT vagy bármely más intézmény, és nem ért egyet ezzel a
közleménnyel, vagy szeretné látni az engedély részleteit, kérjük, nyisson egy
bejelentést (issue-t): <https://github.com/tgeczy/Brailab-wrapper/issues>, vagy
ha nem szeretné nyilvánosan felvetni, írjon Géczy Tamásnak a GitHub-profilján
megadott e-mail-címre: <https://github.com/tgeczy>. Gyorsan válaszolunk, és amit
kér, eltávolítjuk.
