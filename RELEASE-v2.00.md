# BraiLab PC v2.00

*English below · Magyarul lentebb*

---

## English

Two things ship here.

### 1. `brailab.nvda-addon` — the speech synthesiser for NVDA 2026.1+

The BraiLab PC voice as an NVDA synthesiser, working on 64-bit NVDA. NVDA
2026.1 introduced its own 32-bit bridge (`SynthDriverProxy32`), and the driver
uses it, so the older custom host process is gone — the add-on is now 82 KB
instead of 7 MB.

Install it the usual way: open the file, or NVDA menu → Tools → Manage add-ons
→ Install.

### 2. `BraiLabPC.exe` — the emulator

Runs the DOS programs written for BraiLab PC in the late 80s and 90s, with the
speech coming out of your speakers.

**It is not an emulator of a game. It is an emulator of the machine those games
were listened to on.** The original `TALKHUN.COM` is loaded and runs, resident,
inside the emulated DOS — the real 1991 code, not a reimplementation. It
watches `INT 10h` and speaks whatever a program prints, exactly as it did on
real hardware, and the parallel-port traffic it bit-bangs out is decoded and
synthesised here. Nothing in the corpus was ever written to know about speech;
it just printed, and something else did the talking.

Run it and browse for a program, or drop one on the executable.

| key | |
|---|---|
| **F12** | BraiLab settings — tempo, pitch, furcsa. The menu speaks itself. |
| **Ctrl** (hold) | skip through speech, with the blips the real card made |
| **Ctrl+C** | quit |

Tempo, pitch and furcsa are remembered between runs.

**You need `TALKHUN.COM`.** It is not included — it is Vaspöri Teréz and Arató
András's work, not ours to redistribute. Put it in a folder and point the
emulator at it:

```
set BRAILAB_ARCHIVE=C:\path\to\your\brailab\files
```

**Self-extracting archives work.** Point the emulator at an original `.EXE`
from the era and it unpacks itself, reading its own progress aloud as it goes.

### What it does not do

It is not a general DOS prompt. There is no `EXEC`, so nothing can launch
another program — which is fine, because nothing in the corpus tries. A real
`COMMAND.COM` would load and `DIR` would probably even work, but it could not
run anything. Programs see exactly one directory: the folder holding the
program you started, and they cannot reach outside it.

Sampled-audio games (the ones needing a Sound Blaster) are silent. That is a
different chip and a different project.

### Credit

BraiLab was created by **Arató András** and **Vaspöri Teréz**. The technical
description is Arató's 1992 candidate dissertation, *A BraiLab beszélő
számítógépcsalád*, which is public at the Hungarian Electronic Library:
<https://mek.oszk.hu/02000/02025/02025.htm>. It is the source that confirmed
the PCF-8200 frame layout, that `PI = 16` means noise, that the frame fields
are table indices rather than Hz, and that the chip has five formants — every
one of which this emulator had reverse-engineered from bytes and was glad to
have checked.

The games are not distributed here. They are Hungarian blind-community
software from the 1990s and belong in a public archive, not in this repository.

---

## Magyarul

Két dolog van ebben a kiadásban.

### 1. `brailab.nvda-addon` — beszédszintetizátor NVDA 2026.1+ alá

A BraiLab PC hang NVDA szintetizátorként, 64 bites NVDA alatt is. Az NVDA
2026.1 saját 32 bites hidat kapott (`SynthDriverProxy32`), és a meghajtó ezt
használja, így a korábbi külön gazdafolyamat megszűnt: a kiegészítő 7 MB
helyett most 82 KB.

Telepítés a szokásos módon: nyissa meg a fájlt, vagy NVDA menü → Eszközök →
Kiegészítők kezelése → Telepítés.

### 2. `BraiLabPC.exe` — az emulátor

Futtatja azokat a DOS-programokat, amelyeket a nyolcvanas-kilencvenes években
BraiLab PC-re írtak, és a beszéd a hangszórón szól.

**Nem egy játék emulátora. Annak a gépnek az emulátora, amin ezeket a
játékokat hallgatták.** Az eredeti `TALKHUN.COM` betöltődik és rezidensen fut
az emulált DOS-ban — a valódi 1991-es kód, nem újraírás. Figyeli az `INT 10h`
hívásokat, és felolvassa, amit a program kiír, pontosan úgy, ahogy az igazi
gépen tette; a párhuzamos porton kiadott jeleket pedig itt dekódoljuk és
szintetizáljuk. A programok egyike sem tudott a beszédről: csak kiírtak, és
más beszélt helyettük.

Indítsa el, és tallózzon egy programot, vagy húzzon rá egyet.

| billentyű | |
|---|---|
| **F12** | BraiLab beállítások — tempó, hangmagasság, furcsa hang. A menü kimondja magát. |
| **Ctrl** (nyomva tartva) | átugrás a beszéden, ugyanazokkal a pattogó hangokkal, mint a valódi kártyán |
| **Ctrl+C** | kilépés |

A tempót, a hangmagasságot és a furcsa hangot megjegyzi a következő indításig.

**Szükség van a `TALKHUN.COM`-ra.** Nincs mellékelve: Vaspöri Teréz és Arató
András munkája, nem a miénk terjeszteni. Tegye egy mappába, és mutasson rá:

```
set BRAILAB_ARCHIVE=C:\ide\a\brailab\fajlok
```

**Az önkicsomagoló archívumok működnek.** Mutasson rá egy korabeli `.EXE`
fájlra, és kicsomagolja magát — közben hangosan felolvassa a saját haladását.

### Amit nem tud

Nem általános DOS parancssor. Nincs `EXEC`, így egyik program sem tud másikat
indítani — ami nem baj, mert a korabeli programok közül egy sem próbálja. Egy
igazi `COMMAND.COM` betöltődne, a `DIR` valószínűleg működne is, de semmit nem
tudna elindítani. A programok pontosan egy könyvtárat látnak: azt, amelyikben
az elindított program van, és onnan nem tudnak kilépni.

A mintavételezett hangot használó játékok (amelyekhez Sound Blaster kellett)
némák. Az más chip és más feladat.

### Köszönet

A BraiLabot **Arató András** és **Vaspöri Teréz** alkotta. A műszaki leírás
Arató 1992-es kandidátusi értekezése, *A BraiLab beszélő számítógépcsalád*,
amely nyilvánosan elérhető a Magyar Elektronikus Könyvtárban:
<https://mek.oszk.hu/02000/02025/02025.htm>. Ez erősítette meg a PCF-8200
frame-szerkezetét, hogy a `PI = 16` zajt jelent, hogy a mezők táblázatindexek
és nem Hz-értékek, és hogy a chipnek öt formánsa van — mindezt az emulátor
bájtokból fejtette vissza, és jólesett ellenőrizve látni.

A játékok nem részei ennek a kiadásnak. Kilencvenes évekbeli magyar vakos
közösségi szoftverek, amelyeknek nyilvános archívumban a helyük, nem ebben a
tárolóban.
