# BraiLab PC v3.1 — pitch, and capital letters you can hear

*English below · Magyarul lentebb*

---

## English

The emulated BraiLab now has a **pitch** control, and — the part that actually
matters day to day — it honours NVDA's **capital pitch change percentage**.

### Capitals sound like capitals

When NVDA reads a capital letter it asks the synthesiser to say that one letter a
little higher. That is how you *hear* the difference between `a` and `A` without
anything interrupting to tell you.

Both BraiLab drivers were quietly ignoring the request. Not mis-handling it —
never receiving it: a driver has to tell NVDA it understands pitch commands, and
neither did. So "capital pitch change percentage" sat in the settings dialog and
did nothing at any value you chose.

Fixed in both. Set it in NVDA → Preferences → Settings → Voice, and capitals are
audibly higher. At NVDA's default of 30% the emulated voice moves from about
**101 Hz to 128 Hz** on a capital, and drops straight back for the next word — a
capital never leaves the voice retuned.

### A pitch slider that works

The emulated synthesiser had no pitch setting at all. It has one now, in the
settings ring alongside rate and volume, spanning an octave: half above the
voice's own pitch and half below. Rate is untouched by it — changing pitch does
not change how fast it reads.

There is an honest caveat for the **real-hardware** add-on. The wiring there is
complete and correct, but this build of the vendor's `TTS.dll` appears to ignore
pitch entirely — `TTS_SetPitch` measured as an inert stub across its whole range,
the same gap that removed *furcsa* from that build. So on the hardware voice the
command now arrives and the engine may simply not act on it. Nothing is broken
that was working; if a `TTS.dll` with a live pitch path ever turns up, it will
work with no further change. **For capitals you can actually hear today, use the
emulated voice.**

### Also in this release

- `pcf8200`, the standalone Python library, now honours the chip's **FS speed
  bits** when timing frames. It had been timing every frame at 12.8 ms and
  ignoring the control write, so any stream using a different speed rendered
  about 1.45x too slow.
- Both the library and the emulation engine now have test suites that run in CI.

### Install

Open the `.nvda-addon` file, or NVDA menu → Tools → Manage add-ons → Install,
then choose **"Brailab PC (emulated, PCF8200)"** as your synthesiser.

### Credit

Based on the work of **Arató András** and the KFKI. The PCF-8200 is Philips'.

---

## Magyarul

Az emulált BraiLab mostantól **hangmagasság**-szabályzót kapott, és — ami a
mindennapi használatban igazán számít — figyelembe veszi az NVDA
**nagybetűk hangmagasság-változása** beállítását.

### A nagybetűk nagybetűnek hangzanak

Amikor az NVDA nagybetűt olvas, arra kéri a beszélőt, hogy azt az egy betűt kicsit
magasabban mondja. Így *hallani* az `a` és az `A` közti különbséget anélkül, hogy
bármi félbeszakítaná az olvasást.

Mindkét BraiLab meghajtó csendben figyelmen kívül hagyta ezt a kérést. Nem
rosszul kezelte — meg sem kapta: a meghajtónak jeleznie kell az NVDA felé, hogy
érti a hangmagasság-parancsokat, és egyik sem jelezte. Így a beállítás ott volt a
párbeszédablakban, de semmilyen értéknél nem csinált semmit.

Mindkettőben javítva. Állítsd be az NVDA → Beállítások → Hang menüben, és a
nagybetűk hallhatóan magasabbak lesznek. Az NVDA alapértelmezett 30%-ánál az
emulált hang nagybetűnél kb. **101 Hz-ről 128 Hz-re** vált, és a következő szónál
azonnal visszaáll — egy nagybetű soha nem hangolja át tartósan a hangot.

### Működő hangmagasság-csúszka

Az emulált beszélőnek eddig egyáltalán nem volt hangmagasság-beállítása. Most van,
a beállításgyűrűben a sebesség és a hangerő mellett, egy oktáv széles tartománnyal:
fele a hang saját magassága fölött, fele alatta. A sebességet nem érinti — a
hangmagasság módosítása nem változtatja meg az olvasás tempóját.

Egy őszinte megjegyzés a **valódi hardveres** kiegészítőhöz: ott a bekötés teljes
és helyes, de a gyártói `TTS.dll` ezen változata láthatóan teljesen figyelmen kívül
hagyja a hangmagasságot — a `TTS_SetPitch` a teljes tartományában hatástalannak
mérhető, ugyanaz a hiányosság, ami a *furcsa* hangot is kivette abból a buildből.
Tehát a hardveres hangnál a parancs immár megérkezik, de a motor lehet, hogy nem
reagál rá. Semmi nem romlott el, ami eddig működött; ha egyszer előkerül egy élő
hangmagasság-útvonallal rendelkező `TTS.dll`, minden további változtatás nélkül
működni fog. **A ma is hallható nagybetűkhöz használd az emulált hangot.**

### Még ebben a kiadásban

- A `pcf8200` önálló Python könyvtár mostantól figyelembe veszi a chip **FS
  sebességbitjeit** a keretek időzítésénél. Korábban minden keretet 12,8 ms-ra
  időzített, így minden más sebességű adatfolyam kb. 1,45-szer lassabban szólt.
- A könyvtár és az emulációs motor is kapott CI-ban futó tesztkészletet.

### Telepítés

Nyisd meg a `.nvda-addon` fájlt, vagy NVDA menü → Eszközök → Kiegészítők kezelése
→ Telepítés, majd válaszd a **„Brailab PC (emulated, PCF8200)"** beszélőt.

### Köszönet

**Arató András** és a KFKI munkája alapján. A PCF-8200 a Philips fejlesztése.
