# A BraiLab mögötti chipek: a MEA8000 és a PCF8200 időrendje

[In English: history-en.md](history-en.md)

A BraiLab két Philips chipen keresztül beszélt: a BraiLab Basic és a Plus a MEA8000-en, a BraiLab PC a
PCF8200-on. Ez az oldal évről évre sorra veszi, mit mondanak a nyilvános források erről a két chipről
és a rájuk épült gépekről: Budapesten, Barcelonában, és néhány olyan helyen, ahol senki sem keresné a
BraiLab rokonait.

Minden tétel szögletes zárójelben, számmal jelöli a forrását; a források a lap végén állnak. Minden
tétel azt is megmondja, milyen bizonyítékon áll:

- **közlemény:** folyóiratcikk, konferencia-előadás vagy értekezés azoktól, akik a gépet építették;
- **gyártó:** a chip gyártójának saját adatlapja vagy folyóirata;
- **múzeum:** *A magyar beszédtechnológia múzeuma* (magyarbeszed.hu) oldalai, amelyeket Olaszy Gábor és
  Abari Kálmán gondoz, olyan rendszerekről, amelyeknek Olaszy maga is alkotója volt;
- **emulátor:** amit a MAME projekt rögzít a gépet emuláló meghajtójában;
- **program:** maga a szoftver, amely fennmaradt és ma is olvasható;
- **későbbi beszámoló:** amit utólag más írt le.

Ahol két forrás ellentmond egymásnak, mindkettő szerepel. Itt minden ellenőrizhető nyilvános forrásban.

## A két chip

- **MEA8000.** Egyetlen chipre épített formáns beszédszintetizátor a Philipstől; az adatlapjai a Mullard
  és a Signetics nevét viselik [3]. Nincs beépített hangja, és nincs benne mikroprocesszor: a gazdagép
  32 bites kereteket (frame-eket) küld neki, így ugyanaz a chip bármilyen nyelven megszólal, amelyhez
  a gazdagépnek van adata [4]. A Philips saját leírása szerint nyolcadrendű szűrő három programozható
  formánsfrekvenciával és négy programozható sávszélességgel, NMOS technológiával, 4 kHz-es
  beszédsávval [24]. A MAME modelljében négy, 8 kHz-en dolgozó formánsszűrő és 8, 16, 32 vagy 64 ms
  hosszú keretek vannak [5].
- **PCF8200.** A Philips CMOS utódja: „elődjéhez, a MEA8000-hez hasonlóan a PCF8200 is formáns
  szintézist használ” (saját fordítás) [1]. Öt formánsszűrője van (a férfihang ötöt használ, a női
  négyet), a beszédsávja 0-tól 5 kHz-ig tart, a keretei 8,8 és 88 ms közöttiek, az adatsebessége 455
  és 4545 bit/s közötti, van párhuzamos és I²C busza, és 11 bites átalakító is van a chipen [1][2].
  Egy kerete öt bájt [2]. A CPCWiki megjegyzi, hogy visszafelé nem kompatibilis, de hasonlóan működik
  [4].
- **Amit mindkettő a gazdagépre hagy.** Egyik chip sem tud semmilyen nyelvet. Az alább felsorolt
  gépek mindegyikének magával kellett hoznia a saját hangtáblázatát és az összefűzés szabályait. Ezért
  szólhat két, azonos chipre épült gép ennyire másképp.

## A chipek előtt

- **1979-től 1982-ig: HungaroVox** (múzeum, közlemény). Az első magyar szövegfelolvasó rendszer az MTA
  Nyelvtudományi Intézetének Fonetikai Osztályán készült; alkotói Olaszy Gábor, Nikléczy Péter és Kiss
  Gábor, 1982-ben mutatták be. A múzeum cipősdoboz méretű, digitálisan vezérelhető analóg
  formánsszintetizátort (VOX-12) és egy könyvszekrény nagyságú DEC PDP-11/34-et ír le [14a]. Egy
  1987-es cikk az Intézet kutatórendszerét svéd OVE III szintetizátorként és PDP-11/34-ként írja le
  [8]. Akárhogy is: egy szobányi gép, nem egy chip.
- **Az 1980-as évek eleje: beszéd egyetlen chipen.** Ugyanez az 1987-es cikk fel is sorolja azokat a
  chipeket, amelyek lehetővé tették a beszélő készülékeket: „UAA1003, TMS5200, SC-01, SP0256, MEA8000”
  [8].

## 1982-től 1984-ig: megérkezik a MEA8000

- **1982. február: a Philips bejelenti a MEA8000-et** (gyártó). A Philips folyóirata bemutatja az
  „újonnan kifejlesztett, teljesen digitális integrált beszédszintetizátort”, a MEA8000-et (saját
  fordítás), és egy holland verklivel magyarázza el: a chip a hangszer, a beszédadat pedig a
  lyukkártyás kotta [24]. A PCF8200-ról négy évvel később megjelent cikk ugyanezt a verklit
  használja [1].
- **1982. február 24.: szabadalom a felolvasott betűkről** (gyártó). Egy ilyen elsőbbségi napú
  Philips-szabadalom, Johannes N. Kroon munkája, olyan eszközt ír le, amely karaktereket mond ki, és
  a nagybetűt nem plusz szavakkal, hanem a hang megváltoztatásával különbözteti meg a kisbetűtől. A
  szintetizátorát meg is nevezi: „PHILIPS MEA 8000” [25]. A képernyőolvasók ma is hangmagassággal
  jelzik a nagybetűt.
- **1983, más források szerint.** A múzeum szerint a Philips 1983-ban dobta piacra a chipet [14b].
  A CPCWiki egy abban az évben megjelent Philips-kiadványt említ („MEA8000 voice synthesizer:
  principles and interfacing”, Technical Publication 101), amelyet nem láttunk [4].
- **1982: elkezdődik a Scriptovox munkája** (múzeum). A Budapesti Műszaki Egyetem beszédkutató
  csoportja Gordos Géza vezetésével gépi beszéddel kezd foglalkozni, együtt az MTA Fonetikai
  Laboratóriumával; a fonetikai vezérlést Olaszy Gábor, a fejlesztői szoftvert Takács György készíti.
  Az áramkör MEA8000-et vezérel [14c].
- **1985 előtt: Arató fejlesztőrendszerei** (közlemény). A Központi Fizikai Kutatóintézetben (KFKI)
  Arató András egy Intel SDK-85 készletet kötött szavas, angolul beszélő rendszerré alakított, hogy
  vakok is használhassák. Ezt braille-klaviatúrával és MEA8000-rel egészíti ki, és Kiss Gábor
  segítségével egy második, Commodore 64-re épülő MEA8000-es fejlesztőrendszert is készít, a magyar
  formánsparaméterek kialakítására [7]. A Commodore-os rendszerről külön cikk szól [9]. A kötött
  szavas készletben egy 144 szavas Digitalker szintetizátor volt [15].
- **1984, a MAME keltezése szerint: „Brailab 4”** (emulátor). A MAME Lukács József és Endre HomeLab
  gépeit emuláló meghajtójában szerepel egy Brailab 4-nek nevezett, 1984-re keltezett gép, amelyben a
  MEA8000 az F8h és F9h porton ül, 3,84 MHz-es órajellel [6]. A név és az évszám a MAME-é. Arató saját
  leírása 1985-öt mond (lásd lent).

## 1985

- **BraiLab Basic** (közlemény). Arató értekezése szerint az első BraiLab, „1985-ben”, egy HomeLab gép
  MEA8000 szintetizátoros kiegészítő blokkal. A HomeLab Lukács József és Endre Z80-as gépe; a BraiLab
  változatban 64 kilobájt RAM és öt darab 4 kilobájtos EPROM van, és a BASIC-je, az assemblere és a
  monitora is beszél [7]. A MEA8000 teljes magyar hangadatbázisa 4 kilobájt alatt maradt [7]. Az
  intézet saját történeti oldala ugyanezt az évet adja meg, és azt írja, hogy ez volt az első eszköz,
  amellyel a magyar vakok megismerkedhettek a számítástechnikával [22]. A fejlesztők 1994-es
  áttekintése szerint 1985 nyarán készült el, oktatási célra, és 48 kilobájt maradt szabadon a
  felhasználó programjainak [15].
- **1985. szeptember 18.: a szabadalmi bejelentés** (közlemény). Az értekezés hivatkozik egy aznap
  Budapesten benyújtott szabadalmi bejelentésre: eljárás és berendezés hang szintetizálására,
  előnyösen „beszéd és/vagy ének” szótár nélküli, a vezérléssel azonos idejű előállítására [7].

## 1986

- **Bejelentik a PCF8200-at** (gyártó). A Philips „Development data” jelzésű adatlapja 1986 júliusi.
  A chip alkalmazásai között felsorolja a fogyatékos embereknek szánt segédeszközöket is [2]. A
  Philips saját folyóirata ugyanabban az évben mutatja be, egy bemutatókártyával (OM8200), amelyen
  akár tizenkét percnyi beszéd is elfér, és egy IBM PC-re készült beszédfejlesztő rendszerrel
  (OM8210) [1].
- **Az első magyar olvasógép** (közlemény). A Számítástechnikai Kutató Intézet Recognita nevű
  karakterfelismerő programja egy Proper 16 gépen fut, és soros vonalon küldi a felismert szöveget egy
  BraiLab Basicnek, amely felolvassa. Az értekezés ezt nevezi az első magyar olvasógépnek, és azt
  írja, hogy 1986-ban állították ki [7].
- **Egy flipper** (emulátor). A Stargame *Space Ship* (1986) és *White Force* (1987) gépében a
  hangchipek mellett egy MEA8000 is van [16].

## 1987

- **BraiLab Plus** (közlemény). A hardverkártyája 1987-ben készül el Arató útmutatásai alapján; a
  hardvert és a CP/M-kompatibilis alapszoftvert Lukács József és Endre tervezte. A Basichez hasonlóan
  Z80 és MEA8000 van benne. Beszélő szövegszerkesztőt, terminálkezelőt és adatbázis-kezelőt kap, és
  braille fordító- és nyomtatórendszert; az értekezés szerint ez a gép már valós munkarehabilitációs
  elvárásoknak is megfelel [7]. Az 1994-es áttekintés szerint 1987 végére készült el, és német
  nyelvű text-to-speech rendszert is kapott [15].
- **95 gép** (közlemény). Kiss, Arató, Lukács, Sulyán és Vaspöri abban az évben megjelent cikke
  bemutatja a „Braille-Lab”-ot és a „Braille-Lab+”-t, közli, hogy a vakok országos szövetsége
  jóváhagyta és átvette a gépet, és meg is számolja: eddig 95 darabot helyeztek üzembe [8]. A hangot
  is leírja: 218 keret, úgy elrendezve, hogy minden hangkapcsolatot szomszédos keretek adnak ki, a
  minőség rovására: első hallásra nehezen érthető, a rendszeres használóknak viszont semmi gondot nem
  okoz [8].
- **A Scriptovox mint olvasógép** (múzeum, közlemény). Olaszy és Gordos az edinburgh-i európai
  beszédtechnológiai konferencián mutatja be [13]. A Commodore 64 párhuzamos portjára csatlakoztatva
  Microvox-64 néven került forgalomba, a sorozatgyártást a Magamicro szövetkezet végezte; évszámot a
  múzeum ehhez nem ad. Azt viszont hozzáteszi, hogy a kereskedelmi változat már a PCF8200-at
  használta [14c]. Ez az egyik a két magyar vonal közül, amely az egyik chipről átlép a másikra. A
  BraiLab fejlesztői Mikro-vox néven emlékeznek rá, amelynek Basic-vox szoftvere a vakoknak segített
  megtanulni a BASIC-et, és hozzáteszik: ezekből az eszközökből csak ötöt vásároltak meg [15]. A
  múzeum szerint sokan vásárolták [14c]; lehet, hogy a két forrás más vevőket számol.
- **Elindul a Multivox család** (múzeum). A múzeum a családot 1987-től 2002-ig keltezi, a mögötte álló
  közös munkát pedig 1983-tól: a Műszaki Egyetem adta a hardvert és a szoftvert, az MTA Fonetikai
  Laboratóriuma a fonetikai adatokat, a szabályokat és a nyelvi adaptációkat [14d].

## 1988

- **A BraiLab németül beszél, és énekel** (közlemény). A *Beyond Number Crunching* című osztrák-magyar
  konferencián Arató bemutatja a BraiLab Plusba épített magyar és német nyelvű rendszerét. A
  MEA8000-re készült német adatbázist Olaszy Gábor segítségével dolgozták ki. Az énekhez, magyarul és
  németül, Arató mindkét adatbázisból külön változatot készített [7].

## 1989

- **MULTIVOX a PCF8200-on** (közlemény). Olaszy az Eurospeech 1989-en: szöveg-beszéd átalakító rendszer
  IBM PC-re magyar, finn, német, eszperantó és olasz nyelven; a spanyol és a portugál készülőben. Egy
  nyelv programjai, adatai és szabályai legfeljebb 32 kilobájtot foglalnak, és egy új nyelv egy-három
  hónap munka. A MULTIVOX-ot a Philips PCF 8200 formáns szintetizátorra tervezték [10].
- **Multivox-8** (múzeum). A PCF8200-ra épülő különálló egység a PC párhuzamos portján, amelyet az
  egyes nyelvekre fejlesztett szoftverek vezérelnek. A múzeum nyolc nyelvet sorol fel: magyar, német,
  holland, spanyol, finn, olasz, arab és eszperantó [14e]. Ezek több év alatt készültek el: a cikkek
  az olaszt 1990-re és 1991-re, az arabot 1992-re teszik [11][12]. Európában a NIKOL Kkt. forgalmazza
  1989-től 2000-ig [14e]. A NIKOL Nikléczy Péter és Olaszy Gábor cége [21].

## 1990

- **BraiLab PC** (közlemény). „A BraiLab PC rendszer 1990-ben készült el.” A hardver egy jó minőségű
  hangszóróba épített PCF8200, végerősítővel és szűrővel. A chip az I²C buszán keresztül csatlakozik a
  PC nyomtatóportjára úgy, hogy annak csak néhány adatvezetékét használja, a csatlakozó pedig átmenő,
  így más eszköz is rádugható ugyanarra a portra. A fogyasztása olyan csekély, hogy a hangszóróba
  akkumulátor is építhető. Az adapter hardverének és az I²C illesztésnek a kialakításában Lukács
  József és Endre segített; készült szabályos centronics változat is [7].
- **Új hang az új chiphez** (közlemény). A beszédparaméterek 4 kilobájtról 20 kilobájtra nőnek, és
  ezúttal nem hétköznapi, hanem erősen artikulált beszédmintákból készülnek. A beszélő szoftver a
  kivételszótárral együtt 45 kilobájt, tárrezidens DOS-os ernyőfelolvasóként 53 kilobájt [7]. Ez a
  másik magyar vonal, amely a MEA8000-ről átlép a PCF8200-ra.
- **Barcelona: CIBERVEU** (későbbi beszámoló). A spanyol tiflotechnika egyik története 1990-re teszi
  Andrés Ursueguía Balbuena távközlési mérnök CIBERVEU vagy CIBERVOZ nevű rendszerét, és az első
  Spanyolországban gyártott beszédszintézisnek nevezi; célja a jobb érthetőség és a több nyelv volt,
  köztük a katalán [18].
- **A MULTIVOX az első beszédszintézis-műhelyen** (közlemény). Olaszy, Gordos és Németh Géza az első
  ESCA beszédszintézis-műhelyen mutatja be: magyar, német, finn, olasz és eszperantó IBM PC-n, a
  spanyol, a francia és a portugál készülőben, a „szabadon programozható Philips PCF8200 formáns
  szintetizátor chipen” (saját fordítás) [26].
- **1990-től 1991-ig: a MULTIVOX megtanul olaszul** (közlemény). Az olasz változat az eszperantóból
  készül, mert annak hangkészlete és szóhangsúlya közel áll hozzá [11].

## 1991

- **Eladják a német MULTIVOX-ot** (múzeum). A német nyelvű rendszer szabadalmát egy osztrák és egy
  német vállalat veszi meg [14e].
- **A legrégebbi BraiLab PC szoftver, amelyünk van** (program). Az Internet Archive-on a szerzők
  engedélyével közzétett BraiLab PC gyűjtemény 1991 és 2003 közötti változatokat őriz. A legkorábbi
  1991-es [20]. Az intézet történeti oldala a BraiLab PC-t szintén 1991-hez írja [22], és a fejlesztők
  1994-es áttekintése is: 1991-ben készítették el a BraiLab PC-t, egy PCF-8200 szintetizátor chipre
  épülő külső beszédkimeneti adaptert [15].
- **A PCF8200 kommunikációs segédeszközökben** (közlemény). Az Eurospeech 1991-en R. W. King olyan
  eszközöket ír le, amelyekkel olcsó szöveg-beszéd átalakító építhető kommunikációs segédeszközökbe,
  többféle akcentussal, férfi- és női hanggal: egy szerkesztőt egy fonémakészlet formáns- és
  gerjesztési adataihoz, amely a Philips PCF8200 egychipes soros formáns szintetizátorhoz készült
  [27].

## 1992

- **Arató értekezése** (közlemény): *A BraiLab beszélő számítógépcsalád*, Budapest, 1992. A fenti
  BraiLab-tételek többségének ez a forrása [7]. Ekkor a PCF8200-ra írt német text-to-speech program
  már megvan, hangadatbázis még nincs hozzá [7].
- **MULTIVOX arabul** (közlemény). Sabah, Gordos és Olaszy két cikke 255 akusztikai építőelemet ír le,
  amelyek a szabadon programozható PCF-8200 formáns szintetizátor chipre készültek, és közli, hogy a
  MULTIVOX német, olasz, magyar, holland, finn és eszperantó nyelvre kereskedelmi forgalomban van
  [12].
- **Egy díj** (múzeum). A MULTIVOX-8 a *Software for Europe* verseny egyik magyar nyertese. A
  hannoveri CeBIT-en több ízben is bemutatták [14e].

## 1993

- **A Ciber232 nyomtatásban** (közlemény). A fogyatékos embereknek szánt beszéd- és nyelvtechnológiáról
  rendezett ESCA-műhelyen (Stockholm, 1993. május 31. – június 2.) Llisterri, Fernández, Gudayol,
  Poyatos és Martí arról számol be, hogyan fogadják a vak felhasználók a Ciber232-t, egy spanyol és
  katalán szöveg-beszéd átalakítót. A leírásuk ott ér véget, ahol a BraiLab PC-é: a végső hullámformát
  egy Philips PCF8200 formáns szintetizátor állítja elő (saját fordítás) [17]. A megkérdezett
  felhasználók egy része két éve használta, tehát 1991 körül már forgalomban lehetett; ez a mi
  következtetésünk, a cikk ilyen évszámot nem közöl.

## 1994

- **PC-ROBOT** (múzeum, program). Beszélő kártya a PC-ben, amelyből kívülről csak a hangszóró
  csatlakozója látszik; Tihanyi Attila (BME) tervezte, a NIKOL gyártotta 1994-től. Magyarul olvas fel,
  és négy oktáv terjedelemben énekel [14f]. A fennmaradt RobotVOX Multimedia 2.0, amely a kártya
  helyett Sound Blasteren szólal meg, a NIKOL 1994-es copyrightját viseli [21]. Azon az egy PC-ROBOT
  kártyán, amellyel ez a projekt dolgozott, egy Philips PCF8200 van, amelyet ennek a tárolónak a
  DOS-os meghajtója is meg tud szólaltatni ([dos_speaker/NOTES.md](dos_speaker/NOTES.md)). A chip
  dátumkódja 9318, vagyis 1993 18. hete; ez a saját megfigyelésünk.
- **BraiLab PC mindenütt** (későbbi beszámoló). Egy 1994 után írt hangoskönyv-katalógus program
  elsősorban a BRAILAB-PC beszélő adaptert támogatja, „amelyet a magyar vakok széles körben
  használnak” (saját fordítás) [19]. Az intézet saját történeti oldala később azt írta, hogy az
  MS-DOS éveiben szinte minden magyar vak a BraiLab PC segítségével használta a számítógépét [22].
- **Tíz év, visszatekintve** (közlemény). 1994 júliusában Vaspöri Teréz és Arató András, a BraiLab
  fejlesztői, áttekintik a magyarországi vakok számítógép-használatának egy évtizedét. A számaik:
  1993 végéig négyszáz BraiLab Basic, hetven BraiLab Plus és több mint kétszáz BraiLab PC adapter
  kelt el. Mintegy hatszáz tanulót számolnak a speciális iskolákban, 125-öt a középiskolákban és
  ötvenet a felsőoktatásban, és azt írják, hogy mindannyian beszélő számítógépet használnak [15].
- **A többi hang, ahogy a BraiLab készítői hallották** (közlemény). Ugyanez az áttekintés azt írja,
  hogy a Mikro-vox fejlesztői általános célú magyar text-to-speech programot készítettek a
  PCF8200-ra, amely mintegy 150 kilobájt rezidens memóriát igényel, képernyőolvasóval nem
  foglalkoztak, később pedig további nyelveket fejlesztettek hozzá. Megemlíti Király József PC
  Talkerét is, amely Sound Blaster hardveren szólt: a beszéde tisztább volt a PCF8200-énál, többe
  került, és sokkal több rezidens memóriát igényelt [15]. A PC-TALKER-ben egyáltalán nem volt
  beszédchip: Király saját hangjának felvételeiből kivágott elemeket fűzött össze. 1987-ben kezdte
  el, és az 1988-as budapesti vásáron mutatta be, a nyomtatóportra kötött átalakítóval.
  Az 1991-es Sound Blasteres kiadás előtt a puszta PC-hangszóróra is készültek változatok, a
  legkorábbi 1990. március 18-i keltezésű. A hangszórós és a Sound Blasteres kiadás egy
  testvérprojektben újra megszólal, az ő engedélyével [29].
- **Ciber 232P** (későbbi beszámoló). Ugyanaz a spanyol történet egy 1994-re keltezett Ciber 232P-t
  mutat a CIBERVEU-t követő „javított változatok” között [18]. Arról, hogy mi van benne, semmit sem
  találtunk nyomtatásban.

## 2000-től 2002-ig

- **Multivox 4** (múzeum). Hardver nélküli Windows-program SAPI 4.0 felülettel, 2002-től szabadon
  letölthető: „Az első ingyenes magyar beszédszintetizátor szoftver” [14g]. Az Internet Archive-on a
  szerző kérésére közzétett oldala hozzáteszi, hogy a PCF8200 működését az egyetemen előbb egy TMS320
  jelfeldolgozó processzoron utánozták, és a szoftver ebből a munkából nőtt ki [23].

## 2026

- **A gyűjtemények** (program). A BraiLab PC szoftvere, a PC-ROBOT és a Multivox 4 a szerzők
  engedélyével megjelent az Internet Archive-on [20][21][23].
- **Ez a tároló.** A BraiLab PC saját rezidens programja emuláció alatt fut, és az ötbájtos kereteit
  egy szoftveres PCF8200-nak küldi; 2026 novemberében egy valódi BraiLab PC adapterről felvétel
  készült, és a modellt ahhoz igazítottuk. A részletek az
  [src/talkhun_emu/README.md](src/talkhun_emu/README.md) és az
  [src/pcf8200/README.md](src/pcf8200/README.md) fájlban vannak. Ezek ennek a projektnek az
  eredményei, nem a fenti nyilvános források része.
- **A PC-ROBOT** NVDA-kiegészítőn keresztül újra megszólal a mai Windowson [14f].

## A MEA8000 máshol

A MEA8000-nek volt egy második élete Franciaországban, ahol az otthoni számítógépek erre a chipre
épülő beszédbővítőket kaptak.

- **A TMPI** (Techni-musique & parole informatique) több 8 bites géphez (Thomson, Amstrad, Oric)
  készített beszédbővítőt, és a chip azért volt népszerű Franciaországban, mert ki tudta mondani a
  francia u-t [5]. Az Amstrad CPC-hez készültet a CPCWiki dokumentálja [4].
- **Thomson.** A MAME a Thomson gépekhez egy „Cedic-Nathan Speech Synthesizer” nevű bővítőt emulál a
  MEA8000-ével [16], a CPCWiki pedig őriz egy felvételt a chipről, amely egy Thomson TO8-on készült
  [4].
- **Egy könyv.** *Parole et micros: synthèse vocale* (1985), franciául, a chipről és a használatáról
  [4].
- **A Stargame flipperei:** lásd 1986-nál.

## A PCF8200 máshol

A Philips saját kártyáin kívül [1] minden PCF8200-ra épülő termék, amelyet nyomtatásban találtunk,
szerepel ezen az oldalon: Budapesten a Microvox-64, a BraiLab PC és a Multivox-8, Barcelonában a
Ciber232. A PC-ROBOT a Multivox családhoz tartozik, amelynek chipjeiként a múzeum a MEA8000-et, majd
a PCF8200-at nevezi meg [14d]; a saját oldala nem írja le, melyik chip van a kártyán [14f], de azon
a kártyán, amellyel dolgoztunk, PCF8200 van (lásd 1994-nél). Ha tudsz még egy termékről, kérlek,
nyiss egy issue-t.

Még három nyom, mind a SpeechChips.com-ról, Scott Savage beszédchip-múzeumából [28], amelynek
irodalomjegyzéke a fenti 1982-es cikkhez és szabadalomhoz is elvezetett [24][25]:

- **Kommunikációs segédeszközök:** King 1991-es eszközei erre a chipre készültek (lásd 1991-nél)
  [27]. Nem tudjuk, hogy melyik segédeszköz került vele forgalomba, ha egyáltalán.
- **Egy autó** (későbbi beszámoló). A SpeechChips.com a BMW E38 navigációs egységét olyan gépként
  sorolja fel, amely PCF8200-on keresztül mondta be az útirányt [28]. Az oldal sem évszámot, sem
  forrást nem ad. Az adatlaphoz illene, amelynek alkalmazási listája az autóipari felhasználással
  kezdődik [2].
- **Egy 1988-as chip.** Az ott lefényképezett PCF8200P-n a 8814-es kód áll, ami 1988 14. hete, ha
  úgy olvasandó, mint a többi Philips dátumkód [28]. A feliratot egy kis fényképről olvastuk le.

## A Ciber232 és ez a projekt

A Ciber232 azért szerepel ezen az időrenden, mert egy cikk megnevezi a chipjét. Ettől még nem része
ennek a szoftvernek. A Ciber232-ből és a Ciber 232P-ből semmi sincs sem ebben a tárolóban, sem a
kiadásaiban, és az, hogy itt szerepel, nem jelenti azt, hogy ezt tervezzük.

## Amit nem tudtunk eldönteni

- **Mikortól lehetett megvenni a MEA8000-et.** A Philips 1982 februárjában újonnan kifejlesztettnek
  nevezte [24]; a múzeum szerint 1983-ban került piacra [14b].
- **BraiLab Basic: 1984 vagy 1985.** A MAME 1984-et mond [6], Arató 1985-öt [7].
- **Hány BraiLab készült.** 1987-ig 95 darabot helyeztek üzembe [8]. 1993 végéig 400 BraiLab Basic,
  70 BraiLab Plus és több mint 200 BraiLab PC adapter kelt el [15]; az intézet történeti oldala
  megismétli a 400-at [22]. A múzeum az első gépekből több százról, a 90-es évekre pedig több ezer,
  felhasználóknál lévő BraiLab PC-ről ír [14b].
- **BraiLab PC: 1990 vagy 1991.** Az értekezés szerint a rendszer 1990-ben készült el [7]. Az 1994-es
  áttekintés és az intézet oldala 1991-et mond [15][22], és a legrégebbi változat, amelyünk van,
  1991-es [20].
- **A PC-ROBOT első éve.** A múzeum szerint a NIKOL 1994-től gyártotta [14f]. Az Internet Archive-on
  lévő leírás, amelyet ez a projekt írt, 1990-től 1995-ig mondja [21]; a korábbi évszámra nincs
  keltezett dokumentumunk. Az általunk látott kártyán lévő chip 1993 tavaszán készült.
- **Mikor szűnt meg a PCF8200 gyártása.**
- **A Ciber232 évszámai** a fenti kettőn túl.

## Források

1. Menno ten Have, „Speech synthesis: the complete approach with the PCF8200”, *Electronic Components
   and Applications*, 7. évf. 4. szám, 229–238. o. Philips; a szám copyrightja 1986.
   <https://www.worldradiohistory.com/Archive-Company-Publications/Philips-Technical-Review/Electronic-Compoinents/Electronic-Components-&-Apps-Vol-7-No-4.pdf>
2. Philips, *PCF8200 Voice Synthesizer*, adatlap („Development data”), 1986. július. Egy beolvasott
   példánya a vintage-soundchip-collection gyűjteményben:
   <https://github.com/DL1XY/vintage-soundchip-collection/blob/main/PCF8200/PCF8200_datasheet.pdf>
3. A MEA8000 adatlapjai Mullard és Signetics néven, ugyanabban a gyűjteményben:
   <https://github.com/DL1XY/vintage-soundchip-collection/tree/main/MEA8000>
4. CPCWiki, „MEA8000” (utolsó szerkesztés: 2024. június 21.).
   <https://www.cpcwiki.eu/index.php/MEA8000>
5. Antoine Miné, `mea8000.cpp`, MAME projekt, 2006.
   <https://github.com/mamedev/mame/blob/master/src/devices/sound/mea8000.cpp>
6. `homelab.cpp`, MAME projekt.
   <https://github.com/mamedev/mame/blob/master/src/mame/homelab/homelab.cpp>
7. Arató András, *A BraiLab beszélő számítógépcsalád: műszaki leírás* (kandidátusi értekezés),
   Budapest, 1992. Magyar Elektronikus Könyvtár. <https://mek.oszk.hu/02000/02025/>
8. Kiss G., Arató A., Lukács J., Sulyán J., Vaspöri T., „Braille-Lab, a full Hungarian text-to-speech
   microcomputer for the blind”, *Magyar Fonetikai Füzetek* 17 (1987), 116–131. o.
   <https://real.mtak.hu/237547/>
9. Arató András, Kiss Gábor, Tajthy Tamás, „A MEA 8000 beszédszintetizátor Commodore 64 számítógépen
   működő fejlesztő rendszere”, *Magyar Fonetikai Füzetek* 15, 143–154. o. (a repozitórium szerint
   1986). <https://real.mtak.hu/237543/>
10. Olaszy Gábor, „MULTIVOX: a flexible text-to-speech system for Hungarian, Finnish, German,
    Esperanto, Italian and other languages for IBM-PC”, *Eurospeech 1989*, 2525–2528. o.
    <https://www.isca-archive.org/eurospeech_1989/olaszy89_eurospeech.html>
11. Olaszy Gábor, „Adaptation of the MULTIVOX text-to-speech system to Italian”, *Eurospeech 1991*,
    1247–1250. o. <https://www.isca-archive.org/eurospeech_1991/olaszy91_eurospeech.html>
12. M. A. Sabah, Gordos G., Olaszy G., „Acoustic building units for formant synthesis text-to-speech
    converter system for Modern Standard Arabic”, *Periodica Polytechnica Electrical Engineering*
    36/1 (1992), 39–52. o., <https://pp.bme.hu/ee/article/download/4507/3612/8265>; és „Data-base
    rule-system for the MULTIVOX text-to-speech converter application for Arabic language”, 36/2
    (1992), 93–105. o., <https://pp.bme.hu/ee/article/download/4512/3617/8270>
13. Olaszy G., Gordos G., „Automatic text-to-speech system applied in a reading machine”, European
    Conference on Speech Technology, Edinburgh, 1987, 25–29. o. A [14c] alapján idézzük; nem olvastuk.
14. *A magyar beszédtechnológia múzeuma* (Olaszy Gábor és Abari Kálmán), az oldalak utolsó frissítése:
    2026. szeptember 11.:
    - a. HungaroVox: <https://www.magyarbeszed.hu/tts-kezdetek/hungarovox_03/>
    - b. Brailab PC: <https://www.magyarbeszed.hu/tts-kezdetek/brailab_06/>
    - c. Scriptovox C-64: <https://www.magyarbeszed.hu/tts-kezdetek/scriptvox_05/>
    - d. A Multivox család: <https://www.magyarbeszed.hu/tts-multivox/>
    - e. MULTIVOX: <https://www.magyarbeszed.hu/tts-multivox/multivox_01/>
    - f. PC-robot: <https://www.magyarbeszed.hu/tts-multivox/pcrobot_02/>
    - g. MULTIVOX 4: <https://www.magyarbeszed.hu/tts-multivox/multivox_03/>
15. Vaspöri Teréz, Arató András, „Ten Years of Computer Use by Visually Impaired People in Hungary”,
    *Information Technology and Disabilities*, 1. évf. 3. szám, 1994. július. A folyóirat saját címe ma a
    kezdőlapjára vezet; archivált példány:
    <https://web.archive.org/web/20241004235239/https://easi.cc/itd/volume1/number3/arato.html>
16. `stargame.cpp` és `bus/thomson/speech.cpp`, MAME projekt.
    <https://github.com/mamedev/mame/blob/master/src/mame/pinball/stargame.cpp>,
    <https://github.com/mamedev/mame/blob/master/src/devices/bus/thomson/speech.cpp>
17. J. Llisterri, N. Fernández, F. Gudayol, J. J. Poyatos, J. Martí, „Testing user's acceptance of
    Ciber232, a text-to-speech system used by blind persons”, in *Speech and Language Technology for
    Disabled Persons*, ESCA-műhely, Stockholm, 1993, 203–206. o.
    <https://joaquimllisterri.cat/publicacions/Stockholm_93/>
18. Xavier Doménech Riera, „Historia de la Tiflotecnología en España”, *No Solo Usabilidad*, 9. szám,
    2010. <https://www.nosolousabilidad.com/articulos/tiflotecnologia.htm>
19. A „Tallózó” program saját oldala. <https://legeza.oszk.hu/histeng2.htm>
20. *BraiLab PC: Hungarian talking screen access system for blind users (KFKI, 1991–2003)*, Internet
    Archive. <https://archive.org/details/brailab-pc-archive>
21. *PC-ROBOT / RobotVOX Multimedia 2.0*, Internet Archive. <https://archive.org/details/pcrobot-archive>
22. „History of our solutions developed for the blind and autistic people”, Wigner Fizikai
    Kutatóközpont. Az oldal már nem érhető el; archivált példány:
    <https://web.archive.org/web/20231203004727/https://rehab.wigner.hu/en/node/36>
23. *Multivox 4*, Internet Archive. <https://archive.org/details/multivox-4>
24. H. E. van Brück, D. J. A. Teuling, „Integrated voice synthesiser”, *Electronic Components and
    Applications*, 4. évf. 2. szám, 1982. február, 72–79. o. Philips.
    <https://www.worldradiohistory.com/Archive-Company-Publications/Philips-Technical-Review/Electronic-Compoinents/Electronic-Components-&-Apps-Vol-4-No-2.pdf>
25. Johannes N. Kroon, „Device for generating the audio information of a set of characters”, 4 783 810
    számú amerikai szabadalom, U.S. Philips Corp., elsőbbség: 1982. február 24., megadva: 1988.
    november 8. <https://patents.google.com/patent/US4783810A/en>
26. Olaszy Gábor, Gordos Géza, Németh Géza, „Phonetic aspects of the MULTIVOX text-to-speech system”,
    First ESCA Workshop on Speech Synthesis, 1990, 277–280. o.
    <https://www.isca-archive.org/ssw_1990/olaszy90_ssw.html>
27. R. W. King, „Tools and processes for developing low-cost and high-quality text-to-speech synthesis
    for communication aids”, *Eurospeech 1991*, 325–329. o.
    <https://www.isca-archive.org/eurospeech_1991/king91_eurospeech.html>
28. SpeechChips.com (Scott Savage), „Philips PCF8200” és „BMW E38 Navigation System unit”.
    <https://speechchips.com/chips/pcf8200.html>,
    <https://speechchips.com/devices/bmw-navigation.html>
29. *pctalker-nvda*: Király József PC-TALKER-e NVDA beszédszintetizátorként, a történetével a
    README-ben. <https://github.com/tgeczy/pctalker-nvda>
