# The chips behind BraiLab: a timeline of the MEA8000 and the PCF8200

[Magyarul: history-hu.md](history-hu.md)

BraiLab spoke through two Philips chips: the MEA8000 in the BraiLab Basic and Plus, and the PCF8200 in
the BraiLab PC. This page sets out, year by year, what the published record says about those two chips
and the machines built on them: in Budapest, in Barcelona, and in a few places nobody would look for a
relative of BraiLab.

Every entry names its source by a number in square brackets; the sources are listed at the end. Each
entry also says what kind of evidence it rests on:

- **paper:** a journal or conference paper, or a dissertation, by the people who built the thing;
- **maker:** the chip maker's own data sheet or journal;
- **museum:** the pages of *A magyar beszédtechnológia múzeuma* (magyarbeszed.hu), kept by Olaszy Gábor
  and Abari Kálmán, on systems Olaszy helped to build;
- **emulator:** what the MAME project records in the driver that emulates the machine;
- **program:** the software itself, preserved and readable today;
- **later account:** something written afterwards by someone else.

Where two sources disagree, both are given. Everything here can be checked in a public source.

## The two chips

- **MEA8000.** A formant speech synthesizer on one chip, by Philips; data sheets carry the Mullard and
  Signetics names [3]. It has no built-in voice and no microprocessor: the host sends it 32-bit frames,
  so the same chip can speak any language its host has data for [4]. Philips' own description: an
  8th-order filter "with three programmable formant frequencies and four programmable bandwidths",
  NMOS, a 4 kHz speech band [24]. MAME's model has four formant filters working at 8 kHz and frames
  of 8, 16, 32 or 64 ms [5].
- **PCF8200.** Philips' CMOS successor: "Like its predecessor the MEA8000, the PCF8200 uses vocal
  formant synthesis" [1]. It has five formant filters (male speech uses five, female four), a speech
  band of 0 to 5 kHz, frames from 8.8 to 88 ms, a bit rate of 455 to 4545 bits a second, a parallel bus
  and an I²C bus, and an 11-bit converter on the chip [1][2]. Its frames are five bytes long [2].
  CPCWiki notes that it "isn't backwards-compatible, but works similarly" [4].
- **What both leave to the host.** Neither chip knows any language. Each product below had to bring
  its own table of sounds and its own rules for joining them, and that is why two machines with the
  same chip can sound so different.

## Before the chips

- **1979 to 1982: HungaroVox** (museum, paper). Hungary's first text-to-speech system, built at the
  Phonetics Department of the Linguistics Institute of the Hungarian Academy of Sciences by Olaszy
  Gábor, Nikléczy Péter and Kiss Gábor, and shown in 1982. The museum describes a shoebox-sized
  analogue formant synthesizer, the VOX-12, driven by a DEC PDP-11/34 the size of a bookcase [14a].
  A 1987 paper describes the Institute's research system as a Swedish OVE III synthesizer and a
  PDP-11/34 [8]. Either way: a room, not a chip.
- **The early 1980s: speech on one chip.** The same 1987 paper names the chips that made a talking
  appliance possible: "UAA1003, TMS5200, SC-01, SP0256, MEA8000" [8].

## 1982 to 1984: the MEA8000 arrives

- **February 1982: Philips announces the MEA8000** (maker). Philips' journal presents "our newly
  developed, totally digital integrated voice synthesiser MEA8000", and explains it with a Dutch
  street organ: the chip is the instrument, and the speech data is the punched-card score [24]. The
  article on the PCF8200 four years later uses the same organ [1].
- **24 February 1982: a talking-characters patent** (maker). A Philips patent with that priority
  date, by Johannes N. Kroon, describes a device that speaks characters, and makes a capital letter
  sound different from a small one by changing the voice instead of adding words. It names its
  synthesizer as the "PHILIPS MEA 8000" [25]. Screen readers still mark capitals by pitch today.
- **1983, in other accounts.** The museum says Philips put the chip on the market in 1983 [14b].
  CPCWiki lists a Philips publication of that year, "MEA8000 voice synthesizer: principles and
  interfacing" (Technical Publication 101), which we have not seen [4].
- **1982: work on Scriptovox begins** (museum). The speech group of the Technical University of
  Budapest, led by Gordos Géza, starts on machine speech with the Academy's Phonetics Laboratory;
  Olaszy Gábor develops the phonetic control, Takács György the development software. The circuit
  drives a MEA8000 [14c].
- **Before 1985: Arató's development systems** (paper). At the Central Research Institute for
  Physics (KFKI), Arató András had made an Intel SDK-85 kit talk in fixed English words so that blind
  people could use it. He adds a braille keyboard and a MEA8000 to it, and builds a second
  MEA8000 development system on a Commodore 64, with Kiss Gábor, to work out the Hungarian formant
  data [7]. The Commodore system is described in a paper of its own [9]. The fixed-word kit used a
  Digitalker synthesizer with 144 words [15].
- **1984, by MAME's dating: "Brailab 4"** (emulator). MAME's driver for the HomeLab computers of Lukács
  József and Endre includes a machine it calls Brailab 4, dated 1984, with a MEA8000 at ports F8h and
  F9h clocked at 3.84 MHz [6]. The name and the year are MAME's. Arató's own account gives 1985 (see
  below).

## 1985

- **BraiLab Basic** (paper). Arató's dissertation: the first BraiLab, "in 1985", is a HomeLab computer
  with an added MEA8000 block. The HomeLab is a Z80 machine by Lukács József and Endre; the BraiLab
  version has 64 KB of RAM and five 4 KB EPROMs, and its BASIC, assembler and monitor all speak [7].
  The whole Hungarian sound database for the MEA8000 stayed under 4 KB [7]. The institute's own
  history page gives the same year, and calls it the first device that let blind Hungarians get to
  know computers [22]. The developers' 1994 survey says it "was built in the summer of 1985", for
  teaching, with 48 KB left free for the user's programs [15].
- **18 September 1985: the patent application** (paper). The dissertation cites a patent application
  filed in Budapest on that day, for a method and device that synthesize speech "and/or singing" (our
  translation) with no dictionary, in real time [7].

## 1986

- **The PCF8200 is announced** (maker). Philips' data sheet, marked "Development data", is dated July
  1986. It lists "aids for the handicapped" among the chip's uses [2]. Philips' own journal introduces
  it the same year, with a demonstration board (OM8200) that holds up to twelve minutes of speech, and
  a speech development system for the IBM PC (OM8210) [1].
- **The first Hungarian reading machine** (paper). Recognita, the character-recognition program of the
  Computing Research Institute (SZKI), runs on a Proper 16 computer and sends the text it reads over a
  serial line to a BraiLab Basic, which speaks it. The dissertation calls this the first Hungarian
  reading machine, and says it was exhibited in 1986 [7].
- **A pinball machine** (emulator). Stargame's *Space Ship* (1986) and *White Force* (1987) carry a
  MEA8000 beside their sound chips [16].

## 1987

- **BraiLab Plus** (paper). Its hardware card is finished in 1987, to Arató's specification; the
  hardware and the CP/M-compatible system are by Lukács József and Endre. Like the Basic it has a Z80
  and a MEA8000. It adds a talking word processor, terminal program and database, and a braille
  translation and printing system; the dissertation says this machine already meets the demands of
  real work [7]. The 1994 survey has it ready "by the end of 1987", and supplied with a German
  text-to-speech system as well [15].
- **95 machines** (paper). A paper of that year by Kiss, Arató, Lukács, Sulyán and Vaspöri introduces
  "Braille-Lab" and "Braille-Lab+", states that the Hungarian federation of the blind has approved and
  adopted the machine, and counts: "95 sets have been installed so far" [8]. It also describes the
  voice: 218 frames, laid out so that each pair of sounds is made of neighbouring frames, at some cost
  in quality: hard to follow at first hearing, and no trouble at all for its regular users [8].
- **Scriptovox as a reading machine** (museum, paper). Olaszy and Gordos present it at the European
  Conference on Speech Technology in Edinburgh [13]. Attached to the Commodore 64's parallel port it
  was sold as the Microvox-64, made in series by the Magamicro cooperative; the museum gives no year
  for that. It adds that the commercial version already used the PCF8200 [14c]. That is one of the
  two Hungarian lines crossing from one chip to the other. BraiLab's developers remember it as the
  Mikro-vox, whose Basic-vox software helped blind people learn BASIC, and add: "Only five of these
  devices were purchased" [15]. The museum says many people bought it [14c]; the two may be counting
  different buyers.
- **The Multivox family begins** (museum). The museum dates the family 1987 to 2002, and the joint
  work behind it, between the Technical University (hardware and software) and the Academy's Phonetics
  Laboratory (phonetic data, rules, languages), from 1983 [14d].

## 1988

- **BraiLab speaks German, and sings** (paper). At the Austrian-Hungarian conference *Beyond Number
  Crunching*, Arató demonstrates the Hungarian and German systems built into the BraiLab Plus. The
  German database for the MEA8000 was worked out with Olaszy Gábor's help. For singing, in Hungarian
  and in German, Arató made separate versions of both databases [7].

## 1989

- **MULTIVOX on the PCF8200** (paper). Olaszy, at Eurospeech 1989: a text-to-speech system for the IBM
  PC in Hungarian, Finnish, German, Esperanto and Italian, with Spanish and Portuguese in progress.
  One language's programs, data and rules take at most 32 KB, and a new language takes one to three
  months. "MULTIVOX is designed to use the Philips PCF 8200 formant synthesizer" [10].
- **Multivox-8** (museum). An external unit built on the PCF8200, on the PC's parallel port, driven by
  software written for each language. The museum lists eight: Hungarian, German, Dutch, Spanish,
  Finnish, Italian, Arabic and Esperanto [14e]. They came over several years: the papers date Italian
  to 1990 and 1991 and Arabic to 1992 [11][12]. NIKOL sells it in Europe from 1989 to 2000 [14e].
  NIKOL is the company of Nikléczy Péter and Olaszy Gábor [21].

## 1990

- **BraiLab PC** (paper). "The BraiLab PC system was finished in 1990" (our translation). Its hardware
  is a PCF8200 with an amplifier and a filter, built into a good loudspeaker. The chip is reached over
  its I²C bus through the PC's printer port, using only a few of the port's data lines, and the
  connector passes through so that another device can share the port. It draws so little that a
  battery fits in the loudspeaker. Lukács József and Endre helped with the adapter and the I²C code;
  a version with a regular printer-port interface was made as well [7].
- **A new voice for the new chip** (paper). The speech data grows from 4 KB to 20 KB, cut this time
  from carefully articulated speech instead of everyday speech. The talking software is 45 KB with its
  exception dictionary, and 53 KB as a memory-resident DOS screen reader [7]. This is the other
  Hungarian line crossing from the MEA8000 to the PCF8200.
- **Barcelona: CIBERVEU** (later account). A history of assistive technology in Spain dates to 1990
  the CIBERVEU or CIBERVOZ of the telecommunications engineer Andrés Ursueguía Balbuena, and calls it
  the first speech synthesis made in Spain, built to add intelligibility and languages, Catalan among
  them [18].
- **MULTIVOX at the first speech synthesis workshop** (paper). Olaszy, Gordos and Németh Géza describe
  it at the first ESCA workshop on speech synthesis: Hungarian, German, Finnish, Italian and
  Esperanto on IBM PCs, with Spanish, French and Portuguese on the way, speaking through the "Philips
  PCF8200 free programmable formant synthesizer chip" [26].
- **1990 to 1991: MULTIVOX learns Italian** (paper). The Italian version is derived from the Esperanto
  one, whose sounds and word stress are close to it [11].

## 1991

- **The German MULTIVOX is sold** (museum). An Austrian and a German company buy the patent of the
  German-language system [14e].
- **The oldest BraiLab PC software we have** (program). The BraiLab PC collection on the Internet
  Archive, published with its authors' permission, holds versions from 1991 to 2003. Its earliest
  build is from 1991 [20]. The institute's history page also puts the BraiLab PC at 1991 [22], and
  so does the developers' 1994 survey: "in 1991 we created BraiLab PC, an external speech output
  adapter built with PCF-8200 synthesizer chip" [15].
- **The PCF8200 in communication aids** (paper). At Eurospeech 1991, R. W. King describes tools for
  building low-cost text-to-speech for communication aids, with several accents and male and female
  voices: an editor for a phoneme set's formant and excitation data, written for the "Philips
  PCF8200 single chip serial formant synthesizer device" [27].

## 1992

- **Arató's dissertation** (paper): *A BraiLab beszélő számítógépcsalád* ("The BraiLab talking computer
  family"), Budapest, 1992: the source for most of the BraiLab entries above [7]. In it the German
  text-to-speech program for the PCF8200 is written, and still has no sound database [7].
- **MULTIVOX in Arabic** (paper). Two papers by Sabah, Gordos and Olaszy describe 255 acoustic building
  units made for "the free programmable PCF-8200 formant synthesizer chip", and report MULTIVOX on
  sale for German, Italian, Hungarian, Dutch, Finnish and Esperanto [12].
- **A prize** (museum). MULTIVOX-8 is one of the Hungarian winners of the *Software for Europe*
  competition. It was shown at CeBIT in Hannover more than once [14e].

## 1993

- **Ciber232, in print** (paper). At the ESCA workshop on speech and language technology for disabled
  persons (Stockholm, 31 May to 2 June 1993), Llisterri, Fernández, Gudayol, Poyatos and Martí report
  on how blind users accept Ciber232, a Spanish and Catalan text-to-speech system. Their description
  ends where BraiLab PC's does: "the final waveform is generated by a Philips PCF8200 formant
  synthesizer" [17]. Some of the users they interviewed had had it for two years, which suggests it
  was in use by about 1991; that is our reading, not a date the paper gives.

## 1994

- **PC-ROBOT** (museum, program). A speech card inside the PC, with only a loudspeaker socket showing,
  designed by Tihanyi Attila of the Technical University and made by NIKOL from 1994. It reads
  Hungarian and sings over four octaves [14f]. The preserved RobotVOX Multimedia 2.0, which speaks
  through a Sound Blaster instead of the card, carries NIKOL's 1994 copyright [21]. The one PC-ROBOT
  card this project has worked with holds a Philips PCF8200, which this repository's DOS driver can
  feed ([dos_speaker/NOTES.md](dos_speaker/NOTES.md)). The chip's date code is 9318, the 18th week of
  1993; that is our own observation.
- **BraiLab PC everywhere** (later account). A catalogue of talking books for blind readers, written
  after 1994, "primarily supports the BRAILAB-PC speaking adaptor which is widely used by the
  Hungarian blinds" [19]. The institute's own history page later said that in the MS-DOS years
  nearly all blind Hungarians used their computers through BraiLab PC [22].
- **Ten years, looked back on** (paper). In July 1994 Vaspöri Teréz and Arató András, the developers
  of BraiLab, survey a decade of computer use by blind people in Hungary. Their count: "four hundred
  BraiLab Basic, seventy BraiLab Plus and more than two hundred BraiLab PC adapters sold by the end
  of 1993". They count about six hundred pupils in the special schools, 125 in secondary schools and
  fifty in higher education, and write: "All of these students use talking computers" [15].
- **The other voices, as BraiLab's makers heard them** (paper). The same survey says the Mikro-vox
  developers wrote a general Hungarian text-to-speech program for the PCF8200 that needs about 150 KB
  of resident memory, did not deal with screen readers, and later gained more languages. It also
  mentions Király József's PC Talker, on Sound Blaster hardware, whose speech "was purer than
  PCF8200's, cost more and required much more resident memory" [15]. PC-TALKER had no speech chip
  at all: it joined elements cut from recordings of Király's own voice. He began it in 1987 and
  showed it at the 1988 Budapest fair driving a converter on the printer port. Editions for the bare
  PC speaker came before the Sound Blaster one of 1991, the earliest dated 18 March 1990. The
  speaker and Sound Blaster editions speak again in a sibling project, with his permission [29].
- **Ciber 232P** (later account). The same Spanish history shows a Ciber 232P dated 1994, among the
  "improved versions" that followed CIBERVEU [18]. We have found nothing in print about what is
  inside it.

## 2000 to 2002

- **Multivox 4** (museum). A Windows program with no hardware at all, with a SAPI 4.0 interface, free
  to download from 2002: "the first free Hungarian speech synthesizer software" (our translation)
  [14g]. Its Internet Archive page, published at its author's request, adds that the PCF8200 had first
  been imitated on a TMS320 signal processor at the university, and that the software grew out of
  that [23].

## 2026

- **The collections** (program). The BraiLab PC software, PC-ROBOT and Multivox 4 are published on the
  Internet Archive with their authors' permission [20][21][23].
- **This repository.** The BraiLab PC's own resident program runs under emulation and sends its
  five-byte frames to a software PCF8200; a real BraiLab PC adapter was recorded in November 2026 and
  the model corrected from it. The details are in [src/talkhun_emu/README.md](src/talkhun_emu/README.md)
  and [src/pcf8200/README.md](src/pcf8200/README.md). These are this project's findings, not part of
  the published record above.
- **PC-ROBOT** speaks again on today's Windows through an NVDA add-on [14f].

## The MEA8000 elsewhere

The MEA8000 had a second life in France, where home computers got speech add-ons built on it.

- **TMPI** (Techni-musique & parole informatique) "provided speech extensions for several 8-bit
  computers (Thomson, Amstrad, Oric)", and the chip "was quite popular in France because of its
  ability to spell 'u'" [5]. CPCWiki documents the Amstrad CPC one [4].
- **Thomson.** MAME emulates a "Cedic-Nathan Speech Synthesizer" for the Thomson computers on its
  MEA8000 [16], and CPCWiki keeps a recording of the chip made on a Thomson TO8 [4].
- **A book.** *Parole et micros: synthèse vocale* (1985), in French, on the chip and its use [4].
- **Stargame's pinball machines:** see 1986.

## The PCF8200 elsewhere

Outside Philips' own boards [1], every PCF8200 product we have found in print is on this page:
Microvox-64, the BraiLab PC and Multivox-8 in Budapest, and Ciber232 in Barcelona. PC-ROBOT belongs
to the Multivox family, whose chips the museum names as the MEA8000 and then the PCF8200 [14d]; its
own page does not say which chip is on the card [14f], but the card we have worked with holds a
PCF8200 (see 1994). If you know of another product, please open an issue.

Three more traces, all found through SpeechChips.com, Scott Savage's museum of speech chips [28],
whose reference lists also led us to the 1982 article and patent above [24][25]:

- **Communication aids:** King's 1991 tools were written for the chip (see 1991) [27]. We do not know
  which aids, if any, shipped with it.
- **A car** (later account). SpeechChips.com lists the navigation unit of the BMW E38 as a machine
  that gave its spoken directions through a PCF8200 [28]. The page gives no year and no source. It
  would fit the data sheet, whose list of uses begins with "automotive" [2].
- **A 1988 chip.** The PCF8200P photographed there carries the code 8814, the 14th week of 1988 if
  it reads like other Philips date codes [28]. The marking is read from a small photograph.

## Ciber232 and this project

Ciber232 is on this timeline because a paper names its chip. That does not make it part of this
software. Nothing from Ciber232 or Ciber 232P is included in this repository or in its releases,
and its place on this page is not a plan to include it.

## What we could not settle

- **When the MEA8000 could first be bought.** Philips called it newly developed in February 1982
  [24]; the museum says it reached the market in 1983 [14b].
- **BraiLab Basic: 1984 or 1985.** MAME says 1984 [6]; Arató says 1985 [7].
- **How many BraiLabs.** 95 installed by 1987 [8]. By the end of 1993: 400 BraiLab Basics, 70
  BraiLab Plus machines and more than 200 BraiLab PC adapters sold [15]; the institute's history page
  repeats the 400 [22]. The museum speaks of several hundred of the first machines and of several
  thousand BraiLab PCs with users by the 1990s [14b].
- **BraiLab PC: 1990 or 1991.** The dissertation says the system was finished in 1990 [7]. The 1994
  survey and the institute's page say 1991 [15][22], and the oldest build we have is from 1991 [20].
- **PC-ROBOT's first year.** The museum says NIKOL made it from 1994 [14f]. The description on its
  Internet Archive page, which this project wrote, says 1990 to 1995 [21]; we have no dated document
  for the earlier year. The chip on the card we have seen was made in the spring of 1993.
- **When the PCF8200 stopped being made.**
- **Ciber232's dates,** beyond the two above.

## Sources

1. Menno ten Have, "Speech synthesis: the complete approach with the PCF8200", *Electronic Components
   and Applications*, vol. 7, no. 4, pp. 229–238. Philips; the issue is copyright 1986.
   <https://www.worldradiohistory.com/Archive-Company-Publications/Philips-Technical-Review/Electronic-Compoinents/Electronic-Components-&-Apps-Vol-7-No-4.pdf>
2. Philips, *PCF8200 Voice Synthesizer*, data sheet ("Development data"), July 1986. A scan is kept in
   the vintage-soundchip-collection:
   <https://github.com/DL1XY/vintage-soundchip-collection/blob/main/PCF8200/PCF8200_datasheet.pdf>
3. MEA8000 data sheets under the Mullard and Signetics names, in the same collection:
   <https://github.com/DL1XY/vintage-soundchip-collection/tree/main/MEA8000>
4. CPCWiki, "MEA8000" (page last edited 21 June 2024). <https://www.cpcwiki.eu/index.php/MEA8000>
5. Antoine Miné, `mea8000.cpp`, the MAME project, 2006.
   <https://github.com/mamedev/mame/blob/master/src/devices/sound/mea8000.cpp>
6. `homelab.cpp`, the MAME project.
   <https://github.com/mamedev/mame/blob/master/src/mame/homelab/homelab.cpp>
7. Arató András, *A BraiLab beszélő számítógépcsalád: műszaki leírás* (candidate's dissertation),
   Budapest, 1992. Hungarian Electronic Library. <https://mek.oszk.hu/02000/02025/>
8. G. Kiss, A. Arató, J. Lukács, J. Sulyán, T. Vaspöri, "Braille-Lab, a full Hungarian text-to-speech
   microcomputer for the blind", *Magyar Fonetikai Füzetek* 17 (1987), pp. 116–131.
   <https://real.mtak.hu/237547/>
9. Arató András, Kiss Gábor, Tajthy Tamás, "A MEA 8000 beszédszintetizátor Commodore 64 számítógépen
   működő fejlesztő rendszere", *Magyar Fonetikai Füzetek* 15, pp. 143–154 (dated 1986 by the
   repository). <https://real.mtak.hu/237543/>
10. Gábor Olaszy, "MULTIVOX: a flexible text-to-speech system for Hungarian, Finnish, German,
    Esperanto, Italian and other languages for IBM-PC", *Eurospeech 1989*, pp. 2525–2528.
    <https://www.isca-archive.org/eurospeech_1989/olaszy89_eurospeech.html>
11. Gábor Olaszy, "Adaptation of the MULTIVOX text-to-speech system to Italian", *Eurospeech 1991*,
    pp. 1247–1250. <https://www.isca-archive.org/eurospeech_1991/olaszy91_eurospeech.html>
12. M. A. Sabah, G. Gordos, G. Olaszy, "Acoustic building units for formant synthesis text-to-speech
    converter system for Modern Standard Arabic", *Periodica Polytechnica Electrical Engineering*
    36/1 (1992), pp. 39–52, <https://pp.bme.hu/ee/article/download/4507/3612/8265>; and "Data-base
    rule-system for the MULTIVOX text-to-speech converter application for Arabic language", 36/2
    (1992), pp. 93–105, <https://pp.bme.hu/ee/article/download/4512/3617/8270>
13. G. Olaszy, G. Gordos, "Automatic text-to-speech system applied in a reading machine", European
    Conference on Speech Technology, Edinburgh, 1987, pp. 25–29. Cited from [14c]; not read by us.
14. *A magyar beszédtechnológia múzeuma* (Olaszy Gábor and Abari Kálmán), pages last updated
    11 September 2026:
    - a. HungaroVox: <https://www.magyarbeszed.hu/tts-kezdetek/hungarovox_03/>
    - b. Brailab PC: <https://www.magyarbeszed.hu/tts-kezdetek/brailab_06/>
    - c. Scriptovox C-64: <https://www.magyarbeszed.hu/tts-kezdetek/scriptvox_05/>
    - d. The Multivox family: <https://www.magyarbeszed.hu/tts-multivox/>
    - e. MULTIVOX: <https://www.magyarbeszed.hu/tts-multivox/multivox_01/>
    - f. PC-robot: <https://www.magyarbeszed.hu/tts-multivox/pcrobot_02/>
    - g. MULTIVOX 4: <https://www.magyarbeszed.hu/tts-multivox/multivox_03/>
15. Vaspöri Teréz, Arató András, "Ten Years of Computer Use by Visually Impaired People in Hungary",
    *Information Technology and Disabilities*, vol. 1, no. 3, July 1994. The journal's own address now
    leads to its front page; an archived copy:
    <https://web.archive.org/web/20241004235239/https://easi.cc/itd/volume1/number3/arato.html>
16. `stargame.cpp` and `bus/thomson/speech.cpp`, the MAME project.
    <https://github.com/mamedev/mame/blob/master/src/mame/pinball/stargame.cpp>,
    <https://github.com/mamedev/mame/blob/master/src/devices/bus/thomson/speech.cpp>
17. J. Llisterri, N. Fernández, F. Gudayol, J. J. Poyatos, J. Martí, "Testing user's acceptance of
    Ciber232, a text-to-speech system used by blind persons", in *Speech and Language Technology for
    Disabled Persons*, ESCA workshop, Stockholm, 1993, pp. 203–206.
    <https://joaquimllisterri.cat/publicacions/Stockholm_93/>
18. Xavier Doménech Riera, "Historia de la Tiflotecnología en España", *No Solo Usabilidad*, no. 9,
    2010. <https://www.nosolousabilidad.com/articulos/tiflotecnologia.htm>
19. The "Tallózó" (Browser) program's own page. <https://legeza.oszk.hu/histeng2.htm>
20. *BraiLab PC: Hungarian talking screen access system for blind users (KFKI, 1991–2003)*, Internet
    Archive. <https://archive.org/details/brailab-pc-archive>
21. *PC-ROBOT / RobotVOX Multimedia 2.0*, Internet Archive. <https://archive.org/details/pcrobot-archive>
22. "History of our solutions developed for the blind and autistic people", Wigner Research Centre for
    Physics. The page is no longer served; an archived copy:
    <https://web.archive.org/web/20231203004727/https://rehab.wigner.hu/en/node/36>
23. *Multivox 4*, Internet Archive. <https://archive.org/details/multivox-4>
24. H. E. van Brück, D. J. A. Teuling, "Integrated voice synthesiser", *Electronic Components and
    Applications*, vol. 4, no. 2, February 1982, pp. 72–79. Philips.
    <https://www.worldradiohistory.com/Archive-Company-Publications/Philips-Technical-Review/Electronic-Compoinents/Electronic-Components-&-Apps-Vol-4-No-2.pdf>
25. Johannes N. Kroon, "Device for generating the audio information of a set of characters", US
    patent 4,783,810, U.S. Philips Corp., priority 24 February 1982, granted 8 November 1988.
    <https://patents.google.com/patent/US4783810A/en>
26. Gábor Olaszy, Géza Gordos, Géza Németh, "Phonetic aspects of the MULTIVOX text-to-speech system",
    First ESCA Workshop on Speech Synthesis, 1990, pp. 277–280.
    <https://www.isca-archive.org/ssw_1990/olaszy90_ssw.html>
27. R. W. King, "Tools and processes for developing low-cost and high-quality text-to-speech synthesis
    for communication aids", *Eurospeech 1991*, pp. 325–329.
    <https://www.isca-archive.org/eurospeech_1991/king91_eurospeech.html>
28. SpeechChips.com (Scott Savage), "Philips PCF8200" and "BMW E38 Navigation System unit".
    <https://speechchips.com/chips/pcf8200.html>,
    <https://speechchips.com/devices/bmw-navigation.html>
29. *pctalker-nvda*: Király József's PC-TALKER as NVDA speech synthesizers, with its history in the
    README. <https://github.com/tgeczy/pctalker-nvda>
