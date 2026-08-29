# BraiLab PC v3.2 — it sounds like a real unit now

*English below · Magyarul lentebb*

> **Re-released 2026-08-29 as 3.2.1.** The first 3.2 build filtered too hard and
> threw away the bass. If you downloaded 3.2.0, please take this one instead —
> see *The correction* below for what happened and why.

---

## English

The emulated BraiLab has always been a little dull — boxy, distant, a bit like a
voice coming through a telephone. That turned out to be a real, measurable fault,
and it is fixed.

### What was wrong

Too much of the sound we produced was below 250 Hz — about **36%** of it.

Almost none of that was audible as bass. What it did instead was fill up the
available loudness, so everything from 500 Hz upward came out quieter than it
should. That is what made the voice sound muffled: not a missing top end, but an
over-compensation across the bottom range of the spectrum.

No real BraiLab had that problem. The chip drives an amplifier through a coupling
capacitor, which rolls off the bottom of the band before a listener ever hears
it. We had simply never modelled that part of the machine.

### What changed

An output high-pass at 90 Hz, in three gentle stages — the amplifier's coupling,
in other words. Nothing else moved: the low-pass and the source tilt are exactly
as they were.

The reference is the original vendor DLL, TTS.dll, which puts **23.6%** of its
energy below 250 Hz. We now sit at **24.2%**, and the overall spectral distance
from TTS.dll falls from **0.763 to 0.312**.

Removing bass costs loudness, and unlike the first attempt this one cannot put
much back — trimming only the deepest rumble frees almost no headroom. The
result is very slightly quieter than 3.2.0 was, which is the honest price of
keeping the low end. The rest is left to NVDA's volume slider on purpose:
recovering it with a limiter would trade the artefact we just removed for a
different one.

### The correction

3.2.0, released hours earlier, had this same filter set to **600 Hz** — and that
was wrong.

It was tuned against a recording of genuine PCF-8200 hardware, which seemed like
the most authentic reference available. It is not, for this purpose. That
recording is a small speaker in a room, and a small speaker passes almost nothing
below 250 Hz: only **1.5%** of its energy is down there. Matching that number
meant matching the loudspeaker's limitations rather than the chip's voice, and it
removed the low end completely.

Tomi heard it immediately: *"there's also a bit of a bass-end, around like the
75 Hz range — TTS.dll still produces that."* He was right, and the measurement
agrees once the right reference is used. TTS.dll reaches a sound card rather than
a two-inch cone, which makes it the correct target for anyone listening on
headphones or decent speakers.

So the original diagnosis stands — there really was too much bass — but the first
prescription was far too strong. 90 Hz trims the excess. 600 Hz amputated it.

**The v3.2.0 games bundle was also wrong, in a different way:** it never contained
the audio fix at all. The bundle is assembled by a script that was not re-run
before publishing, so the zip on that release still had the pre-3.2 chip core
while the notes claimed otherwise. That claim was untrue and this is the
correction. The assembler now refuses to build if its staged copy differs from
the source, and it produces the zip itself so the shipped file cannot be older
than the tree it came from.

### What to expect

Clearer speech, more present, less like a phone call — with the low end intact,
and slightly quieter than before, so you may want a little more volume. The voice
itself is unchanged: same engine, same frames, same intonation. Only the
loudspeaker it is imagined to be coming out of is now the right one.

This affects the **emulated** synthesiser and the portable games bundle. The
real-hardware add-on is untouched — it has a real speaker already.

### Also in this release

- `pcf8200`, the standalone library, is **1.1.1** and gains the same `highpass`
  control, at the corrected cutoff. It models a PCF-8200 **device** — chip and
  amplifier — because that is what anyone wants to hear; pass `highpass=0` for
  the bare chip's own output.

  It also, at last, actually contains the two fixes from v3.1. The published zip
  had been built once by hand and then re-attached to two later releases, so the
  library people could download was missing the FS frame-timing fix and the rate
  control that the repository has had all along. It is built by a script now,
  which refuses to package a tree that is behind — and which, after today, checks
  the filter's *value* and not merely its presence.

### Credit

Based on the work of **Arató András** and the KFKI. The PCF-8200 is Philips'.
The hardware recording that started this investigation is of a **CIBERVEU
Ciber232P**, a Spanish cousin of the BraiLab built on the same chip, and we owe
it to **Guillem Leon** — it diagnosed the problem correctly even though it was
the wrong thing to tune against.

---

## Magyarul

Az emulált BraiLab hangja mindig kicsit tompa volt — dobozos, távoli, mintha
telefonon szólna. Kiderült, hogy ez valódi, mérhető hiba volt, és most javítva
van.

> **2026-08-29-én újra kiadva, 3.2.1 néven.** Az első 3.2 túl erősen szűrt, és
> elvitte a mélyeket. Ha a 3.2.0-t töltötted le, kérlek, ezt vedd helyette — hogy
> mi történt, azt *A javítás* szakasz mondja el.

### Mi volt a baj

Az általunk előállított hang túl nagy része, mintegy **36%-a**, 250 Hz alatt szólt.

Basszusként szinte semmi sem hallatszott belőle. Ehelyett elfogyasztotta a
rendelkezésre álló hangerőt, így 500 Hz fölött minden halkabban szólt a
kelleténél. Ettől tűnt tompának a hang: nem a magasak hiányoztak, hanem
túlkompenzáltuk a spektrum alsó tartományát.

Valódi BraiLabnál ez nem volt gond. A chip csatolókondenzátoron át hajt meg egy
erősítőt, és az levágja a sáv alját, mielőtt bárki hallaná. Ezt a részét a gépnek
egyszerűen nem modelleztük.

### Mi változott

Egy kimeneti felüláteresztő szűrő 90 Hz-en, három lágy fokozatban — vagyis az
erősítő csatolása. Semmi más nem mozdult: az aluláteresztő és a gerjesztés
lejtése pontosan ugyanaz.

A referencia a gyári TTS.dll, amely energiájának **23,6%-át** viszi 250 Hz alatt.
Mi most **24,2%-on** állunk, és a TTS.dll-től mért teljes spektrális eltérés
**0,763-ról 0,312-re** esik.

A mélyek elvétele hangerőbe kerül, és az elsőtől eltérően ez a változat keveset
tud visszaadni: a legmélyebb dörmögés levágása alig szabadít fel tartalékot. Az
eredmény egy hajszálnyival halkabb, mint a 3.2.0 volt — ez a mélyek megtartásának
őszinte ára. A többit szándékosan az NVDA hangerő-csúszkájára bízzuk: limiterrel
visszaszerezni azt jelentené, hogy az imént eltávolított műterméket egy másikra
cseréljük.

### A javítás

A néhány órával korábban kiadott 3.2.0-ban ugyanez a szűrő **600 Hz-en** állt —
és ez hiba volt.

Valódi PCF-8200 hardverről készült felvételhez hangoltuk, ami a leghitelesebb
elérhető referenciának látszott. Erre a célra viszont nem az. Az a felvétel egy
kis hangszóró egy szobában, és egy kis hangszóró 250 Hz alatt szinte semmit nem
enged át: energiájának mindössze **1,5%-a** van odalent. Ehhez a számhoz igazodni
annyit tett, hogy a hangszóró korlátait másoltuk le a chip hangja helyett — és ez
teljesen elvitte a mélyeket.

Tomi azonnal meghallotta: *„van egy kis mély is, olyan 75 Hz környékén — a
TTS.dll ezt még mindig előállítja."* Igaza volt, és a mérés is ezt mondja, amint
a helyes referenciához nyúlunk. A TTS.dll hangkártyára megy, nem egy ötcentis
membránra, ezért ez a helyes cél mindenkinek, aki fejhallgatón vagy rendes
hangszórón hallgat.

Az eredeti diagnózis tehát áll — valóban túl sok volt a mély —, csak a felírt
adag volt sokszorosan túl erős. A 90 Hz lenyesi a felesleget. A 600 Hz amputálta.

**A 3.2.0 játékcsomag is hibás volt, másképp:** egyáltalán nem tartalmazta a
hangjavítást. A csomagot szkript állítja össze, amelyet a közzététel előtt nem
futtattunk le újra, így a kiadáshoz csatolt zipben még a 3.2 előtti chip-mag volt,
miközben a kiadási jegyzet mást állított. Ez az állítás nem volt igaz, és most
javítjuk. Az összeállító mostantól megtagadja a build-et, ha az előkészített
másolat eltér a forrástól, és maga készíti a zipet is, hogy a kiadott fájl ne
lehessen régebbi a fánál, amelyből származik.

### Mire számíts

Tisztább, jelenlévőbb beszéd, kevésbé telefonszerű — megmaradt mélyekkel, és
kicsit halkabban, mint eddig, úgyhogy lehet, hogy egy kevéssel több hangerő kell.
Maga a hang változatlan: ugyanaz a motor, ugyanazok a keretek, ugyanaz a
hangsúlyozás. Csak a hangszóró lett a helyes, amelyből képzeletben megszólal.

Ez az **emulált** beszélőt és a hordozható játékcsomagot érinti. A valódi
hardveres kiegészítő változatlan — annak már van igazi hangszórója.

### Még ebben a kiadásban

- A `pcf8200` önálló könyvtár **1.1.1** lett, és megkapja ugyanezt a `highpass`
  vezérlőt, a javított vágási frekvenciával. Egy PCF-8200 **készüléket** modellez
  — chip és erősítő —, mert ezt akarja bárki hallani; a `highpass=0` a chip saját
  kimenetét adja.

  Végre valóban tartalmazza a v3.1 két javítását is. A közzétett zip egyszer,
  kézzel készült, majd két későbbi kiadáshoz is változatlanul csatoltuk, így a
  letölthető könyvtárból hiányzott az FS-időzítés javítása és a sebességvezérlő,
  amelyek a tárolóban régóta megvoltak. Mostantól szkript építi, amely nem
  hajlandó elmaradt állapotot csomagolni — és amely a mai nap után a szűrő
  *értékét* ellenőrzi, nem csupán a meglétét.

### Köszönet

**Arató András** és a KFKI munkája alapján. A PCF-8200 a Philips fejlesztése.
A vizsgálatot elindító hardveres felvétel egy **CIBERVEU Ciber232P**-ről készült,
a BraiLab spanyol unokatestvéréről, amely ugyanarra a chipre épült — köszönet
érte **Guillem Leonnak**. A hibát helyesen mutatta meg, még ha nem is hozzá
kellett volna hangolni.
