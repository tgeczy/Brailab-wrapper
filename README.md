# Brailab-wrapper

[English](#english) · [Magyarul](#magyarul)

---

## English

The Hungarian BraiLab PC speech synthesizer, for today's computers.

This project provides a small native wrapper around the classic **BraiLab PC**
TTS engine so it can be used cleanly from **NVDA** via **nvwave**, and an
emulator of the BraiLab PC itself.

Why the wrapper exists:

- The original BraiLab `tts.dll` plays audio directly through WinMM (waveOut), bypassing NVDA's audio pipeline.
- NVDA works best when synth audio goes through `nvwave` (device routing, consistent stop behavior, fewer conflicts).
- This wrapper hooks the WinMM waveOut APIs, captures PCM, and lets the NVDA driver feed it into `nvwave.WavePlayer`.

### What's in this repo

- `brailab_wrapper.dll` (built from the sources here)
- A Python NVDA synth driver (`synthDrivers/brailab.py`) that uses the wrapper
- **`src/talkhun_emu/`: an emulator of the BraiLab PC itself** (see below)
- **`third_party/brailab/`: TALKHUN**, the original BraiLab PC speech program
  for DOS, by Vaspöri Teréz and Arató András, included with their permission.
  See [`NOTICE.md`](NOTICE.md).

### What's NOT in this repo

- **The BraiLab speech engine (`TTS.dll`, `BINADATA.BIN`, `BINAHANK.BIN`).**
  These are included only in the release packages, unmodified, as the original
  authors' files; their source code is not distributed. See
  [`NOTICE.md`](NOTICE.md).
- **The games.** They are Hungarian blind-community software from the 1990s and
  belong in a public archive rather than in this repository.

### Licence

This project's own code is under the MIT License (see `LICENSE`). The BraiLab
software, both TALKHUN in `third_party/brailab/` and TTS.dll in the release
packages, is **not**: its copyright belongs to its authors, and it is
distributed under the terms described in [`NOTICE.md`](NOTICE.md).

### How the wrapper works (high level)

1. The NVDA driver calls into `brailab_wrapper.dll`.
2. The wrapper loads `tts.dll`.
3. MinHook detours WinMM functions (`waveOutOpen`, `waveOutWrite`, etc.).
4. When `tts.dll` tries to output PCM via `waveOutWrite`, the wrapper captures the PCM bytes.
5. The NVDA driver pulls PCM from the wrapper and feeds it to `nvwave`, so NVDA controls the audio output device.

The wrapper also:
- Paces output to prevent "fast synthesis / skipping" behavior.
- Applies tempo/pitch/volume on the same worker thread that calls `StartSay` (some engines behave like this internally).
- Supports an option to disable intonation using `TTS_StartSayWithNoIntonation` when available.
- Offers a gentler comma intonation ("Gentler comma intonation" in NVDA's voice settings, off by default). TTS.dll ends the clause before a comma with a steep rise; the option removes the rise and halves the fall before it. The values change only in the loaded copy of TTS.dll, never in the file, and only for the one TTS.dll build the wrapper recognises.

The wrapper's exports carry a version (`bl_getApiVersion`, 2 as of this option). Older exports never change meaning, so an older driver works with a newer wrapper; a newer driver asks what the wrapper can do and leaves out what it cannot, so it works with an older wrapper too.

### Requirements

Build tools:
- Windows
- Visual Studio Build Tools (MSVC) + Windows SDK
- CMake + Ninja
- MinHook sources vendored into the repo (recommended)

Runtime:
- NVDA (the driver is written for modern NVDA versions; tested with NVDA 2025.x)
- BraiLab `tts.dll` (provided in the NVDA driver release package, not this repo)

### `src/talkhun_emu/`: the BraiLab PC emulator

The wrapper above gives you the *voice*. This gives you the *machine*.

It runs the DOS programs written for BraiLab PC in the late 80s and 90s, with
the speech coming out of your speakers, and it does so by loading the original
**`TALKHUN.COM`** and running it, resident, inside an emulated DOS. That is the
real 1991 code, not a reimplementation. It watches `INT 10h` and speaks whatever
a program prints, exactly as it did on real hardware; the I2C traffic it
bit-bangs at the parallel port is decoded here and synthesised by a software
PCF-8200.

None of those programs were written to know about speech. They just printed,
and something else did the talking.

```
set BRAILAB_ARCHIVE=third_party\brailab
python src/talkhun_emu/braipc.py            # browse for a program and run it
python src/talkhun_emu/speak.py "mama."     # just the synthesiser
```

`F12` opens a settings menu (tempo, pitch, furcsa), which speaks itself, so it
needs no screen reader. Holding `Ctrl` skips through speech the way the real
card did, blips and all.

**`TALKHUN.COM` is Vaspöri Teréz and Arató András's work, not ours.** It is in
`third_party/brailab/` with their permission; see [`NOTICE.md`](NOTICE.md).

The technical basis is Arató's 1992 candidate dissertation, *A BraiLab beszélő
számítógépcsalád*, public at the Hungarian Electronic Library:
<https://mek.oszk.hu/02000/02025/02025.htm>

### Building `brailab_wrapper.dll` (32-bit)

BraiLab is a **32-bit** DLL, so you must build the wrapper as **Win32/x86**.

From an **"x86 Native Tools Command Prompt for VS"**:

```bat
cmake -S . -B build-x86 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-x86
```

---

## Magyarul

A magyar BraiLab PC beszédszintetizátor a mai számítógépekre.

A projekt egy kis natív burkolót (wrappert) ad a klasszikus **BraiLab PC**
beszédmotor köré, hogy az **NVDA** a saját hangkezelésén (**nvwave**) keresztül
tisztán használhassa, valamint magának a BraiLab PC-nek az emulátorát.

Miért kell a burkoló:

- Az eredeti BraiLab `tts.dll` közvetlenül a WinMM-en (waveOut) játssza le a hangot, megkerülve az NVDA hangkezelését.
- Az NVDA akkor működik a legjobban, ha a beszédhang az `nvwave`-en keresztül megy (eszközválasztás, megbízható leállítás, kevesebb ütközés).
- A burkoló elfogja a WinMM waveOut-hívásait, elkapja a hangot, és átadja az NVDA-illesztőnek, amely az `nvwave.WavePlayer`-rel játssza le.

### Mi van ebben a tárolóban

- `brailab_wrapper.dll` (az itteni forrásból készül)
- Python nyelvű NVDA-beszédillesztő (`synthDrivers/brailab.py`), amely a burkolót használja
- **`src/talkhun_emu/`: magának a BraiLab PC-nek az emulátora** (lásd lent)
- **`third_party/brailab/`: a TALKHUN**, a BraiLab PC eredeti DOS-os
  beszélőprogramja, Vaspöri Teréz és Arató András munkája, az ő engedélyükkel.
  Lásd: [`NOTICE.md`](NOTICE.md).

### Mi NINCS ebben a tárolóban

- **A BraiLab beszédmotorja (`TTS.dll`, `BINADATA.BIN`, `BINAHANK.BIN`).** Ezek
  csak a kiadási csomagokban szerepelnek, változtatás nélkül, az eredeti
  szerzők fájljaiként; a forráskódjukat nem terjesztjük. Lásd:
  [`NOTICE.md`](NOTICE.md).
- **A játékok.** Ezek az 1990-es évek magyar vak közösségének programjai, és
  nyilvános archívumban, nem ebben a tárolóban van a helyük.

### Licenc

A projekt saját kódja MIT-licenc alatt áll (lásd: `LICENSE`). A BraiLab
szoftverekre, vagyis a `third_party/brailab/` mappában lévő TALKHUN-ra és a
kiadási csomagokban lévő TTS.dll-re ez **nem** vonatkozik: a szerzői jog a
szerzőiké, és a [`NOTICE.md`](NOTICE.md) fájlban leírt feltételekkel
terjesztjük őket.

### Hogyan működik a burkoló (nagy vonalakban)

1. Az NVDA-illesztő meghívja a `brailab_wrapper.dll`-t.
2. A burkoló betölti a `tts.dll`-t.
3. A MinHook eltéríti a WinMM függvényeit (`waveOutOpen`, `waveOutWrite` stb.).
4. Amikor a `tts.dll` a `waveOutWrite`-tal hangot akar kiadni, a burkoló elkapja a hangadatot.
5. Az NVDA-illesztő átveszi a hangot a burkolótól, és az `nvwave`-nek adja, így a kimeneti eszközről az NVDA dönt.

A burkoló ezenkívül:
- ütemezi a kimenetet, hogy a beszéd ne rohanjon és ne ugráljon;
- a tempót, a hangmagasságot és a hangerőt ugyanazon a szálon állítja be, amelyik a `StartSay`-t hívja (egyes motorok belül így működnek);
- kérésre kikapcsolja a hanglejtést a `TTS_StartSayWithNoIntonation` hívással, ha elérhető;
- szelídebb vesszős hanglejtést kínál (az NVDA hangbeállításai között „Gentler comma intonation”, alapból kikapcsolva). A TTS.dll a vessző előtti tagmondat végén meredeken felviszi a hangot; a beállítás ezt az emelést elhagyja, az előtte lévő süllyedést pedig megfelezi. Az értékek csak a TTS.dll betöltött példányában változnak, a fájlban soha, és csak annál a TTS.dll-változatnál, amelyet a burkoló felismer.

A burkoló függvényeinek verziója van (`bl_getApiVersion`, ezzel a beállítással 2). A régebbi függvények jelentése nem változik, ezért egy régebbi illesztő az újabb burkolóval is működik; az újabb illesztő pedig megkérdezi, mit tud a burkoló, és amit az nem tud, azt nem kínálja fel, így régebbi burkolóval is működik.

### Követelmények

Fordításhoz:
- Windows
- Visual Studio Build Tools (MSVC) és Windows SDK
- CMake és Ninja
- a MinHook forrása a tárolóban (ajánlott)

Futtatáshoz:
- NVDA (az illesztő a mai NVDA-változatokhoz készült; az NVDA 2025.x-szel kipróbálva)
- a BraiLab `tts.dll` (az NVDA-illesztő kiadási csomagjában, nem ebben a tárolóban)

### `src/talkhun_emu/`: a BraiLab PC emulátora

A fenti burkoló a *hangot* adja. Ez a *gépet*.

Az 1980-as évek végén és az 1990-es években BraiLab PC-re írt DOS-os
programokat futtatja, a beszéd pedig a hangszóróidból szól. Mindezt úgy, hogy
betölti az eredeti **`TALKHUN.COM`**-ot, és rezidensen futtatja egy emulált
DOS-ban. Ez a valódi 1991-es program, nem újraírás. Figyeli az `INT 10h`-t, és
kimondja, amit egy program kiír, pontosan úgy, ahogy a valódi gépen tette; a
párhuzamos porton kiküldött I2C-forgalmat itt fejtjük vissza, és egy szoftveres
PCF-8200 szólaltatja meg.

Ezeket a programokat nem beszédre írták. Csak kiírtak, a beszédet pedig valami
más intézte.

```
set BRAILAB_ARCHIVE=third_party\brailab
python src/talkhun_emu/braipc.py            # programválasztás és futtatás
python src/talkhun_emu/speak.py "mama."     # csak a szintetizátor
```

Az `F12` beállításmenüt nyit (tempó, hangmagasság, furcsa hang), amely maga is
beszél, így képernyőolvasó sem kell hozzá. A `Ctrl` nyomva tartásával úgy lehet
átugrani a beszédet, ahogy a valódi kártyán, a sípolásokkal együtt.

**A `TALKHUN.COM` Vaspöri Teréz és Arató András munkája, nem a miénk.** Az ő
engedélyükkel van a `third_party/brailab/` mappában; lásd:
[`NOTICE.md`](NOTICE.md).

A technikai alap Arató András 1992-es kandidátusi értekezése, *A BraiLab beszélő
számítógépcsalád*, amely a Magyar Elektronikus Könyvtárban nyilvánosan elérhető:
<https://mek.oszk.hu/02000/02025/02025.htm>

### A `brailab_wrapper.dll` fordítása (32 bites)

A BraiLab **32 bites** DLL, ezért a burkolót is **Win32/x86** változatként kell
fordítani.

Az **„x86 Native Tools Command Prompt for VS”** ablakból:

```bat
cmake -S . -B build-x86 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-x86
```
