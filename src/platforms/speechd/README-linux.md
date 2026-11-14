# The BraiLab voices for Linux

[English](#english) · [Magyarul](#magyarul)

## English

A speech-dispatcher module, `sd_brailab`, for Orca, `spd-say` and anything else that speaks through
speech-dispatcher. One program, nothing else to install.

| Voice | What it is |
|---|---|
| BraiLab PC | the BraiLab PC itself: its own 1991 program, TALKHUN, on an emulated 8086, speaking through a model of its speech chip, the Philips PCF8200 |
| BraiLab PC furcsa | the same with TALKHUN's "furcsa" (weird) voice |
| BraiLab TTS | the later software voice; an optional plug-in, see below |

### Install

```sh
tar -xzf brailab-*-linux-*.tar.gz
cd brailab-*-linux-*
sudo ./install.sh
killall speech-dispatcher
spd-say -o brailab "Jó napot kívánok"
```

In Orca: Preferences, Speech, Speech synthesizer: `brailab`, then the voice.

`sudo ./install.sh --default` also makes it the default synthesizer. `sudo ./uninstall.sh` removes everything
the installer added and gives `speechd.conf` back as it was.

### The BraiLab TTS voice

The package holds the two BraiLab PC voices. BraiLab TTS is a binary plug-in of about 100 KB, kept as a separate
download in the same release. The installer asks whether you want it:

- answer yes, or run `sudo ./install.sh --with-tts`, and it is fetched, checked against its checksum and set up;
- answer no, or run `sudo ./install.sh --without-tts`, and you have the two BraiLab PC voices, nothing missing;
- with no network, download `brailab-tts-plugin-linux-<arch>.tar.gz` from the release page on another machine
  and run `sudo ./install.sh --tts-file brailab-tts-plugin-linux-<arch>.tar.gz`.

You can run the installer again at any time to add the voice later. If the download fails, the BraiLab PC
voices are installed all the same.

### Settings

`brailab.conf` in speech-dispatcher's modules folder explains each setting. A file of your own,
`~/.config/brailab/sd_brailab.conf`, wins over it line by line, needs no root and survives reinstalling.

### Building it yourself

```sh
./build_linux.sh                         # build/linux/sd_brailab
tools/package_linux.sh 4.0.0             # build/brailab-4.0.0-linux-<arch>.tar.gz
```

Any C and C++ compiler will do; there is nothing to install first. A build from source is the two BraiLab PC
voices; the plug-in is not built from this repository, and the module is complete without it.

TALKHUN is Arató András and Vaspöri Teréz's work and is here with their permission; see `licenses/NOTICE.md`.

## Magyarul

Egy speech-dispatcher modul, az `sd_brailab`: az Orca, az `spd-say` és minden más program számára, amely a
speech-dispatcheren keresztül beszél. Egyetlen program, semmi mást nem kell hozzá telepíteni.

| Hang | Mi ez |
|---|---|
| BraiLab PC | maga a BraiLab PC: saját, 1991-es programja, a TALKHUN fut egy emulált 8086-oson, és a beszédchipje, a Philips PCF8200 modelljén keresztül szól |
| BraiLab PC furcsa | ugyanez a TALKHUN „furcsa” hangjával |
| BraiLab TTS | a későbbi, szoftveres hang; külön letölthető kiegészítő, lásd lent |

### Telepítés

```sh
tar -xzf brailab-*-linux-*.tar.gz
cd brailab-*-linux-*
sudo ./install.sh
killall speech-dispatcher
spd-say -o brailab "Jó napot kívánok"
```

Az Orcában: Beállítások, Beszéd, Beszédszintetizátor: `brailab`, utána a hang.

A `sudo ./install.sh --default` alapértelmezett szintetizátorrá is teszi. A `sudo ./uninstall.sh` mindent
eltávolít, amit a telepítő hozzáadott, és a `speechd.conf` olyan lesz, amilyen előtte volt.

### A BraiLab TTS hang

A csomagban a két BraiLab PC hang van. A BraiLab TTS egy körülbelül 100 KB-os bináris kiegészítő, amely
ugyanannak a kiadásnak külön letölthető része. A telepítő megkérdezi, kéri-e:

- ha igennel válaszol, vagy a `sudo ./install.sh --with-tts` parancsot futtatja, a telepítő letölti,
  ellenőrzi az ellenőrzőösszegét, és beállítja;
- ha nemmel válaszol, vagy a `sudo ./install.sh --without-tts` parancsot futtatja, megvan a két BraiLab PC
  hang, és semmi sem hiányzik;
- hálózat nélkül töltse le egy másik gépen a kiadás oldaláról a `brailab-tts-plugin-linux-<arch>.tar.gz`
  fájlt, és futtassa: `sudo ./install.sh --tts-file brailab-tts-plugin-linux-<arch>.tar.gz`.

A telepítőt bármikor újra lefuttathatja, ha később szeretné hozzáadni a hangot. Ha a letöltés nem sikerül,
a BraiLab PC hangok akkor is települnek.

### Beállítások

A speech-dispatcher modulmappájában lévő `brailab.conf` minden beállítást elmagyaráz. A saját
`~/.config/brailab/sd_brailab.conf` fájlja soronként felülírja, nem kell hozzá rendszergazdai jog, és az
újratelepítést is túléli.

### Fordítás forrásból

```sh
./build_linux.sh                         # build/linux/sd_brailab
tools/package_linux.sh 4.0.0             # build/brailab-4.0.0-linux-<arch>.tar.gz
```

Bármilyen C és C++ fordító megfelel, előre semmit sem kell telepíteni. A forrásból fordított változat a két
BraiLab PC hangot tartalmazza; a kiegészítő nem ebből a tárolóból készül, a modul nélküle is teljes.

A TALKHUN Arató András és Vaspöri Teréz munkája, az ő engedélyükkel szerepel itt; lásd: `licenses/NOTICE.md`.
