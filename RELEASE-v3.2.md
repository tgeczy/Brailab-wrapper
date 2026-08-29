# BraiLab PC v3.2 — it sounds like a real unit now

*English below · Magyarul lentebb*

---

## English

The emulated BraiLab has always been a little dull — boxy, distant, a bit like a
voice coming through a telephone. That turned out to be a real, measurable fault,
and it is fixed.

### What was wrong

A third of the sound we produced was below 250 Hz.

A recording of genuine PCF-8200 hardware has **1.5%** of its energy down there.
We had **23%**. None of it was audible as bass — a small speaker cannot reproduce
it — but it filled up the available loudness, so everything from 500 Hz upward
came out 5 to 17 dB quieter than it should. That is what made the voice sound
muffled: not a missing top end, but a bottom end that should never have existed.

No real BraiLab produced it either. The chip drives an amplifier through a
coupling capacitor and then a small speaker, and neither passes anything near
there. We had simply never modelled that part of the machine.

### What changed

An output high-pass, at 600 Hz, in three gentle stages — the amplifier and the
speaker, in other words. Nothing else moved: the low-pass and the source tilt
are exactly as they were.

Measured against a recording of a working unit speaking a phrase we can
reproduce frame for frame, the difference between our sound and the real one
falls from **0.955 to 0.108** — about nine times closer. Energy below 250 Hz
lands on **1.5%**, the same as the hardware.

Removing that bass costs real loudness, and about 4.5× of it is put back — as
much as fits without clipping. The rest is left to NVDA's volume slider on
purpose: recovering it with a limiter would trade the artefact we just removed
for a different one.

### What to expect

Clearer speech, more present, less like a phone call — and slightly quieter, so
you may want a little more volume than before. The voice itself is unchanged:
same engine, same frames, same intonation. Only the loudspeaker it is imagined
to be coming out of is now the right one.

This affects the **emulated** synthesiser and the portable games bundle. The
real-hardware add-on is untouched — it has a real speaker already.

### Also in this release

- `pcf8200`, the standalone library, is **1.1.0** and gains the same `highpass`
  control. It models a PCF-8200 **device** — chip, amplifier and speaker —
  because that is what anyone wants to hear; pass `highpass=0` for the bare
  chip's own output.

  It also, at last, actually contains the two fixes from v3.1. The published zip
  had been built once by hand and then re-attached to two later releases, so the
  library people could download was missing the FS frame-timing fix and the rate
  control that the repository has had all along. It is built by a script now,
  which refuses to package a tree that is behind.

### Credit

Based on the work of **Arató András** and the KFKI. The PCF-8200 is Philips'.
The reference recording is of a **CIBERVEU Ciber232P**, a Spanish cousin of the
BraiLab built on the same chip, and we owe it to **Guillem Leon**.

---

## Magyarul

Az emulált BraiLab hangja mindig kicsit tompa volt — dobozos, távoli, mintha
telefonon szólna. Kiderült, hogy ez valódi, mérhető hiba volt, és most javítva
van.

### Mi volt a baj

Az általunk előállított hang harmada 250 Hz alatt szólt.

Egy valódi PCF-8200 hardverről készült felvételen ez a tartomány az energia
**1,5%-át** viszi. Nálunk **23%** volt. Basszusként semmi sem hallatszott belőle
— egy kis hangszóró nem is adja vissza —, de elfogyasztotta a rendelkezésre álló
hangerőt, így 500 Hz fölött minden 5–17 dB-lel halkabban szólt a kelleténél. Ettől
tűnt tompának a hang: nem a magasak hiányoztak, hanem olyan mélyek voltak benne,
amelyeknek soha nem kellett volna ott lenniük.

Valódi BraiLab sem állította elő őket. A chip csatolókondenzátoron át hajt meg
egy erősítőt, majd egy kis hangszórót, és egyik sem enged át semmit odalent. Ezt
a részét a gépnek egyszerűen nem modelleztük.

### Mi változott

Egy kimeneti felüláteresztő szűrő 600 Hz-en, három lágy fokozatban — vagyis az
erősítő és a hangszóró. Semmi más nem mozdult: az aluláteresztő és a gerjesztés
lejtése pontosan ugyanaz.

Egy működő készülék felvételéhez mérve — olyan mondathoz, amelyet keretről
keretre reprodukálni tudunk — a mi hangunk és a valódi közti eltérés **0,955-ről
0,108-ra** esik, nagyjából kilencszer közelebb. A 250 Hz alatti energia **1,5%**
lett, ugyanannyi, mint a hardveren.

A mélyek eltávolítása valódi hangerőbe kerül, ebből mintegy 4,5-szörös kerül
vissza — annyi, amennyi torzítás nélkül belefér. A többit szándékosan az NVDA
hangerő-csúszkájára bízzuk: limiterrel visszaszerezni azt jelentené, hogy az
imént eltávolított műterméket egy másikra cseréljük.

### Mire számíts

Tisztább, jelenlévőbb beszéd, kevésbé telefonszerű — és kicsit halkabb, úgyhogy
lehet, hogy egy kevéssel több hangerő kell, mint eddig. Maga a hang változatlan:
ugyanaz a motor, ugyanazok a keretek, ugyanaz a hangsúlyozás. Csak a hangszóró
lett a helyes, amelyből képzeletben megszólal.

Ez az **emulált** beszélőt és a hordozható játékcsomagot érinti. A valódi
hardveres kiegészítő változatlan — annak már van igazi hangszórója.

### Még ebben a kiadásban

- A `pcf8200` önálló könyvtár **1.1.0** lett, és megkapja ugyanezt a `highpass`
  vezérlőt. Egy PCF-8200 **készüléket** modellez — chip, erősítő és hangszóró —,
  mert ezt akarja bárki hallani; a `highpass=0` a chip saját kimenetét adja.

  Végre valóban tartalmazza a v3.1 két javítását is. A közzétett zip egyszer,
  kézzel készült, majd két későbbi kiadáshoz is változatlanul csatoltuk, így a
  letölthető könyvtárból hiányzott az FS-időzítés javítása és a sebességvezérlő,
  amelyek a tárolóban régóta megvoltak. Mostantól szkript építi, amely nem
  hajlandó elmaradt állapotot csomagolni.

### Köszönet

**Arató András** és a KFKI munkája alapján. A PCF-8200 a Philips fejlesztése.
A referenciafelvétel egy **CIBERVEU Ciber232P**-ről készült, a BraiLab spanyol
unokatestvéréről, amely ugyanarra a chipre épült — köszönet érte **Guillem
Leonnak**.
