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

A caveat for the **real-hardware** add-on. Its pitch slider works, but in three
steps only — low, normal, high — because the vendor's `TTS.dll` takes just those
three values.

**Correction (3.1.1):** an earlier version of these notes said capital pitch
change could not work on the `TTS.dll` voice because NVDA's 32-bit bridge dropped
pitch commands. **That was wrong, and unfair to NVDA — the bridge carries them
correctly.** The fault was a bug in this add-on: the speech host applies pitch at
the moment an utterance *runs*, and we restored the user's own setting a moment
too early, wiping the capital's pitch before any sound was produced. Fixed in
`brailab-3.1.1.nvda-addon`.

One real limit remains, and it is small: the hardware voice carries one pitch per
utterance, so a pitch change in the middle of a sentence is not possible there.
Capitals are unaffected — NVDA speaks a capital as its own utterance.

### The portable games emulator

`BraiLabPC-portable.zip` — the self-contained bundle for playing the 1991 DOS
programs with real BraiLab speech, carrying its own Python so it runs on machines
too old for a modern install — is updated in this release too.

It gains a **fine pitch trim** in the F12 menu. BraiLab's own `ESC P` command has
exactly three pitches — low, normal, high — which is coarse if you are going to
listen for an hour, so the trim fills in between them in seven steps without
touching what the program itself asked for.

It also now **remembers your tempo and pitch**. It always intended to — it read
them back at start-up — but never actually saved them, so every session began at
the defaults again.

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

Egy megjegyzés a **valódi hardveres** kiegészítőhöz: a hangmagasság-csúszkája
működik, de csak három fokozatban — mély, normál, magas —, mert a gyártói
`TTS.dll` csak ezt a három értéket ismeri.

**Helyesbítés (3.1.1):** e jegyzetek korábbi változata azt állította, hogy a
nagybetűk hangmagasság-változása a `TTS.dll` hangnál azért nem működhet, mert az
NVDA 32 bites hídja eldobja a hangmagasság-parancsokat. **Ez tévedés volt, és
igazságtalan az NVDA-val szemben — a híd rendben átviszi őket.** A hiba ebben a
kiegészítőben volt: a beszédkiszolgáló akkor alkalmazza a hangmagasságot, amikor
egy megnyilatkozás *lefut*, mi pedig egy pillanattal korábban állítottuk vissza a
felhasználó saját beállítását, így a nagybetű hangmagassága még azelőtt eltűnt,
hogy bármilyen hang keletkezett volna. Javítva: `brailab-3.1.1.nvda-addon`.

Egy valódi korlát marad, és az kicsi: a hardveres hang megnyilatkozásonként egy
hangmagasságot tud, így mondat közben nem lehet hangmagasságot váltani. A
nagybetűket ez nem érinti — az NVDA a nagybetűt önálló megnyilatkozásként mondja.

### A hordozható játékemulátor

A `BraiLabPC-portable.zip` — az önálló csomag az 1991-es DOS programok valódi
BraiLab-hanggal való játszásához, saját Pythonnal, így olyan gépeken is elfut,
amelyek egy mai telepítéshez már túl régiek — szintén frissült ebben a kiadásban.

Kapott egy **finomhangolást** az F12 menübe. A BraiLab saját `ESC P` parancsa
pontosan három hangmagasságot ismer — mély, normál, magas —, ami elég durva, ha
órákig hallgatod, így a finomhangolás hét lépésben tölti ki a köztes értékeket
anélkül, hogy hozzányúlna ahhoz, amit maga a program kért.

Mostantól **megjegyzi a tempót és a hangmagasságot** is. Mindig is ez volt a
szándék — indításkor visszaolvasta őket —, de valójában sosem mentette el, így
minden munkamenet újra az alapértékekkel indult.

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
