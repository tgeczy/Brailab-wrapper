# BraiLab PC v3.2.2 — the crackle on loud words is gone, and it's louder

*English below · Magyarul lentebb*

---

## English

If you ever heard a faint crackle or static on the loud part of a long sentence —
a bit like a needle skating on a record — that was real, and it is gone.

### What it was

Digital clipping. The output was running past what a 16-bit sample can hold, and
every sample past the limit got flattened.

It only happened on **long, inflected phrases**, never on single words, and that
detail turned out to be the whole diagnosis. The voice slides up and down across
a phrase; the top of that slide is where it ran out of room. A word on its own
has no slide, so it never got there. Reading out a downloads list, or a
paragraph, or anything in say-all — that is where it lived.

Measured on a real example, a file listing read aloud: the signal peaked **44%
past the ceiling** and flattened 46 samples. A say-all sentence flattened 120.

**This is an old fault, not a new one.** Every emulated build up to and including
3.1.x had it. It was not introduced by v3.2 — v3.2 is what removed it, as a side
effect of taking out the excess bass, because that bass was what pushed the peaks
over the edge in the first place. Same root cause as the muffling, one fix.

### What is new in 3.2.2

**It is 1.2 dB louder, and it can no longer clip at all.**

Not "does not clip on everything we tried" — *cannot*. The output stage now bends
as it approaches full scale instead of hitting a wall, the way a real amplifier
runs out of swing gradually. The curve approaches the limit without ever reaching
it, so no volume setting and no phrase can get there. That is a property of the
arithmetic, not a lucky result on a test corpus.

The bend touches **0.04% of samples** — four in ten thousand — and it is what
makes the extra loudness safe.

### Why it wasn't simply "turn it up"

Compared against the original TTS.dll, our average level was already the same
(RMS 0.103 against 0.107). We were never quieter on average. We were **peakier**:
crest factor 7.70 against its 6.16.

TTS.dll is not doing anything clever — it is not compressing or limiting, it has
no flattened peaks, and it never goes above 0.81 of full scale. It simply has a
less spiky waveform, so it has room to spare where we had none. "Louder without
clipping" was therefore never a trade-off; it was a crest problem, and closing
part of that gap is what made room for the level.

### What to expect

The same voice, a little louder, and clean on the loud peaks of long sentences.
Nothing about the speech itself changed: same engine, same frames, same
intonation.

Anyone measuring the chip rather than a device is unaffected — asking for the
bare chip's output still bypasses the amplifier model entirely.

### Also in this release

- The portable games bundle, rebuilt with the same audio.
- `pcf8200`, the standalone library, is **1.1.2** and gains the same output
  stage. It models a PCF-8200 **device**, so pass `highpass=0` for the bare
  chip — that path has no makeup gain and no knee.

### Credit

Based on the work of **Arató András** and the KFKI. The PCF-8200 is Philips'.
The hardware recording that started this line of work is of a **CIBERVEU
Ciber232P**, and we owe it to **Guillem Leon**.

The diagnosis in this release is **Tomi's**: that the crackle tracked the
intonation slide rather than any particular word, which is why "három" alone was
clean and "három" inside a version string was not. Every measurement here came
from chasing that observation. Thanks also to everyone who reported the static
rather than quietly living with it.

---

## Magyarul

Ha valaha hallottál halk recsegést vagy sercegést egy hosszú mondat hangos
részén — kicsit olyat, mint amikor a tű megcsúszik a lemezen —, az valóban ott
volt, és most eltűnt.

### Mi volt az

Digitális vágás. A kimenet túllépte azt, amit egy 16 bites minta tárolni tud, és
minden határon túli minta lelapult.

Csak **hosszú, hangsúlyozott mondatoknál** fordult elő, önálló szavaknál soha —
és éppen ez a részlet volt a megfejtés. A hang egy mondaton belül fel-le csúszik;
ennek a csúszásnak a teteje az, ahol elfogyott a hely. Egy magában álló szóban
nincs ilyen csúszás, így oda sose jutott el. Egy letöltéslista felolvasásában,
egy bekezdésben, vagy bármiben, amit folyamatos olvasással hallgatsz — ott élt.

Egy valódi példán mérve, egy fájllista felolvasásakor a jel a **határ fölé 44%-kal**
ment, és 46 mintát lapított le. Egy folyamatos olvasásra jellemző mondat 120-at.

**Ez régi hiba, nem új.** Minden emulált változatban benne volt egészen a 3.1.x-ig
bezárólag. Nem a v3.2 hozta be — a v3.2 az, ami megszüntette, a fölös mély
eltávolításának mellékhatásaként, mert éppen az a mély tolta át a csúcsokat a
határon. Ugyanaz a gyökérok, mint a tompaságé, egyetlen javítással.

### Mi új a 3.2.2-ben

**1,2 dB-lel hangosabb, és többé egyáltalán nem tud vágni.**

Nem úgy, hogy „amit kipróbáltunk, azon nem vág" — hanem *nem tud*. A kimeneti
fokozat mostantól elhajlik a teljes kivezérlés közelében, ahelyett hogy falnak
ütközne, ahogy egy valódi erősítőből is fokozatosan fogy ki a hely. A görbe
közelít a határhoz, de sosem éri el, így semmilyen hangerő és semmilyen mondat nem
juthat oda. Ez a számtan tulajdonsága, nem egy szerencsés tesztsorozaté.

Az elhajlás a minták **0,04%-át** érinti — tízezerből négyet —, és ez teszi
biztonságossá a többlethangerőt.

### Miért nem egyszerűen „hangosítás" volt

Az eredeti TTS.dll-hez mérve az átlagos szintünk már eddig is ugyanaz volt (RMS
0,103 a 0,107 ellenében). Átlagban sosem voltunk halkabbak. **Csúcsosabbak**
voltunk: 7,70-es crest a 6,16 ellenében.

A TTS.dll nem csinál semmi trükköset — nem tömörít és nem limitál, nincsenek
lelapított csúcsai, és sosem megy 0,81 fölé a teljes kivezérlésből. Egyszerűen
kevésbé tüskés a hullámformája, ezért van tartaléka ott, ahol nekünk nem volt. A
„hangosabb vágás nélkül" tehát sosem kompromisszum volt, hanem csúcstényező-kérdés,
és ennek a résnek a részleges bezárása teremtett helyet a szintnek.

### Mire számíts

Ugyanaz a hang, kicsit hangosabban, és tisztán a hosszú mondatok hangos csúcsain.
Magában a beszédben semmi nem változott: ugyanaz a motor, ugyanazok a keretek,
ugyanaz a hangsúlyozás.

Akit a chip érdekel, nem pedig egy készülék, azt ez nem érinti — a csupasz chip
kimenetének kérése továbbra is teljesen megkerüli az erősítőmodellt.

### Még ebben a kiadásban

- A hordozható játékcsomag, ugyanazzal a hanggal újraépítve.
- A `pcf8200` önálló könyvtár **1.1.2** lett, és megkapja ugyanezt a kimeneti
  fokozatot. Egy PCF-8200 **készüléket** modellez, így a `highpass=0` adja a
  csupasz chipet — azon az úton nincs sem kiegyenlítő erősítés, sem elhajlás.

### Köszönet

**Arató András** és a KFKI munkája alapján. A PCF-8200 a Philips fejlesztése.
Az ezt a munkát elindító hardveres felvétel egy **CIBERVEU Ciber232P**-ről
készült — köszönet érte **Guillem Leonnak**.

A diagnózis ebben a kiadásban **Tomié**: hogy a recsegés a hangsúlycsúszást
követte, nem egy-egy szót, és ezért volt tiszta a „három" önmagában, miközben a
verziószámban nem. Minden itteni mérés ennek az észrevételnek a nyomán született.
Köszönet mindenkinek is, aki jelezte a sercegést, ahelyett hogy szó nélkül
együtt élt volna vele.
