# BraiLab PC v3.0

*English below · Magyarul lentebb*

---

## English

The big one. BraiLab now speaks with **no hardware and no vendor binary at all** —
the chip itself is software.

Two NVDA synthesisers ship here.

### 1. `brailabEmulated.nvda-addon` — the fully emulated BraiLab *(new)*

A BraiLab PC voice that needs nothing but NVDA. Two 1991 machines run inside your
screen reader at once:

- the original **`TALKHUN`** engine — the real 1991 code, under a CPU emulator,
  turning Hungarian text into the frames it always did; and
- the **Philips PCF-8200** formant chip it drove — now a from-scratch **software
  model**, rebuilt from the chip's own datasheet and matched, by ear and by
  measurement, against real PCF-8200 hardware.

No card, no `TTS.dll`, no external program — it all runs inside NVDA's own process,
in real time, snappy enough for everyday reading.

And it does the one thing the vendor's `TTS.dll` threw away: **furcsa hang**, the
weird voice, is a checkbox again. Flip it mid-sentence.

Install the usual way (open the file, or NVDA menu → Tools → Manage add-ons →
Install), then pick **"Brailab PC (emulated, PCF8200)"** as your synthesiser. In
the settings ring you'll find rate, volume, **Furcsa (weird voice)** and
**Use intonation**.

It is self-contained — the add-on carries the engine and everything it needs. It
is larger than the real-hardware add-on for that reason, and the first time you
select it there is a short pause while the 1991 engine boots.

### 2. `brailab.nvda-addon` — the real-hardware voice

The `TTS.dll` BraiLab as before, bumped to 3.0 for this release. This is the
authentic vendor binary path; the emulated add-on above is the pure-software one.
Ship whichever suits you — or both; they sit side by side.

### Credit

BraiLab was created by **Arató András** and **Vaspöri Teréz**. Their 1991
`TALKHUN` code is included in this release package with permission; it is not in
the source repository.

The emulated voice was only possible because the **Philips PCF-8200** was
understood directly — its frame layout, its two quantization tables, its
excitation and five-formant cascade, and the fact that it runs a 10 kHz internal
speech path — worked out from the silicon's own behaviour and the chip's technical
documentation, then rebuilt in software until it agreed with real hardware. That
understanding is the whole reason a BraiLab can now talk with no BraiLab in the
room.

Arató's 1992 candidate dissertation, *A BraiLab beszélő számítógépcsalád*, is
public at the Hungarian Electronic Library: <https://mek.oszk.hu/02000/02025/02025.htm>.

---

## Magyarul

A nagy kiadás. A BraiLab mostantól **hardver és gyártói bináris nélkül** is beszél
— maga a chip is szoftver.

Két NVDA-szintetizátor van ebben a kiadásban.

### 1. `brailabEmulated.nvda-addon` — a teljesen emulált BraiLab *(új)*

Egy BraiLab PC hang, amelyhez az NVDA-n kívül semmi nem kell. Két 1991-es gép fut
egyszerre a képernyőolvasón belül:

- az eredeti **`TALKHUN`** motor — a valódi 1991-es kód, egy CPU-emulátorban,
  ugyanúgy frame-ekké alakítva a magyar szöveget, ahogy mindig is; és
- a **Philips PCF-8200** formánschip, amelyet hajtott — ez most **nulláról írt
  szoftveres modell**, a chip saját adatlapjából újraépítve, és füllel és méréssel
  is a valódi PCF-8200 hardverhez igazítva.

Nincs kártya, nincs `TTS.dll`, nincs külső program — minden az NVDA saját
folyamatában fut, valós időben, a napi olvasáshoz elég fürgén.

És tudja azt az egyet, amit a gyártói `TTS.dll` eldobott: a **furcsa hang** újra
egy jelölőnégyzet. Mondat közben is átkapcsolható.

Telepítés a szokásos módon (nyissa meg a fájlt, vagy NVDA menü → Eszközök →
Kiegészítők kezelése → Telepítés), majd válassza a **„Brailab PC (emulated,
PCF8200)”** szintetizátort. A beállítási gyűrűben ott a sebesség, a hangerő, a
**Furcsa (weird voice)** és a **Use intonation**.

Önálló csomag — a kiegészítő magával hozza a motort és mindent, ami kell. Ezért
nagyobb, mint a valódi hardveres kiegészítő, és amikor először kiválasztja, egy
rövid szünet van, amíg az 1991-es motor elindul.

### 2. `brailab.nvda-addon` — a valódi hardveres hang

A `TTS.dll`-es BraiLab, mint eddig, ehhez a kiadáshoz 3.0-ra emelve. Ez a hiteles
gyártói bináris út; a fenti emulált kiegészítő a tisztán szoftveres. Azt
használja, amelyik jobban megfelel — vagy mindkettőt, elférnek egymás mellett.

### Köszönet

A BraiLabot **Arató András** és **Vaspöri Teréz** alkotta. Az 1991-es `TALKHUN`
kódjuk engedéllyel része ennek a kiadásnak; a forráskód-tárolóban nincs benne.

Az emulált hang csak azért volt lehetséges, mert a **Philips PCF-8200**-at
közvetlenül sikerült megérteni — a frame-szerkezetét, a két kvantálási
táblázatát, a gerjesztését és öt-formánsos szűrőláncát, és azt, hogy belül 10
kHz-es beszédútvonalon dolgozik — a szilícium saját viselkedéséből és a chip
műszaki dokumentációjából kibogozva, majd szoftverben addig újraépítve, amíg meg
nem egyezett a valódi hardverrel. Ez a megértés az egész oka annak, hogy egy
BraiLab most úgy tud beszélni, hogy közben nincs a szobában BraiLab.

Arató 1992-es kandidátusi értekezése, *A BraiLab beszélő számítógépcsalád*,
nyilvánosan elérhető a Magyar Elektronikus Könyvtárban:
<https://mek.oszk.hu/02000/02025/02025.htm>.
