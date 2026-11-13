# -*- coding: utf-8 -*-
"""The listening-test recording for the real BraiLab PC: what FELV.EXE says.

    python make_braiplay.py felv_program.py FELV.EXE

Each part is announced by its number, so a recording of it can be cut up by ear.  Tempo 4
throughout, except in the tempo part.
"""
import os

ESC = b'\x1b'
BASE = ESC + b'P*' + ESC + b'S4' + ESC + b'F0' + ESC + b'R0' + ESC + b'C0' + ESC + b'E1' + ESC + b'K1'
S_SENTENCES = ['A cica és a macska sziszeg, a fecske sikeres.', 'Szép, csendes szombat este, szia Zsuzsa!']
COMMA_SENTENCES = ['Az alapítvány, röviden az INFOALAP, sok ezer embernek segített.',
                   'A tanulásban, a munkában és a mindennapi életben.']

PROGRAM = [('set', BASE)]


def part(number_word):
    PROGRAM.extend([('pause', 1200), ('say', number_word), ('pause', 400)])


def lines(texts, gap=0):
    for t in texts:
        PROGRAM.append(('say', t))
        if gap:
            PROGRAM.append(('pause', gap))


part('Egyes.')                      # the hissing sounds in running speech
lines(S_SENTENCES)

part('Kettes.')                     # single words, apart
lines(['Szép.', 'Csendes.', 'Szombat.', 'Este.', 'Négyes.', 'Ötös.'], gap=500)

part('Hármas.')                     # commas
lines(COMMA_SENTENCES + S_SENTENCES[1:])

part('Négyes.')                     # every accented letter
lines(['Árvíztűrő tükörfúrógép.', 'Őszi éjjel izzik a galagonya ruhája.'])

part('Ötös.')                       # statement, question, exclamation, a list
lines(['Ma szép idő van.', 'Ma szép idő van?', 'Ma szép idő van!', 'Hogy vagy ma?',
       'Egy, kettő, három, négy, öt, hat, hét, nyolc, kilenc, tíz.'])

# The sounds one at a time.  NOT fit for measuring as written: TALKHUN takes a letter with a full
# stop after it for an abbreviation or a Roman numeral and says the word ("l." liter, "m." méter,
# "i." as a numeral), as Tomi heard on the real box on 2026-11-13.  For single sounds use the
# chip sweep (make_sweep.py), which writes the frames itself.
part('Hatos.')
lines(['a.', 'á.', 'e.', 'é.', 'i.', 'í.', 'o.', 'ó.', 'ö.', 'ő.', 'u.', 'ú.', 'ü.', 'ű.'], gap=300)
PROGRAM.append(('pause', 600))
lines(['s.', 'sz.', 'cs.', 'c.', 'zs.', 'z.', 'f.', 'h.', 'ty.', 'gy.', 'ny.', 'r.', 'l.', 'm.', 'n.'], gap=300)

part('Hetes.')                      # the eight tempos
for n in range(1, 9):
    PROGRAM.append(('set', ESC + b'S%d' % n))
    lines(['Tempó %d. Szép, csendes szombat este.' % n], gap=300)
PROGRAM.append(('set', ESC + b'S4'))

part('Nyolcas.')                    # pitch
for code, text in ((b'!', 'Ez a mély hang.'), (b'*', 'Ez a rendes hang.'), (b'=', 'Ez a magas hang.')):
    PROGRAM.append(('set', ESC + b'P' + code))
    lines([text], gap=300)
PROGRAM.append(('set', ESC + b'P*'))

part('Kilences.')                   # furcsa
PROGRAM.append(('set', ESC + b'F1'))
lines(['Ez a furcsa hang.'] + S_SENTENCES + COMMA_SENTENCES[:1])
PROGRAM.append(('set', ESC + b'F0'))

part('Tízes.')                      # the detailed mode
PROGRAM.append(('set', ESC + b'R1'))
lines(['Ez a részletező üzemmód.', 'Szép, csendes szombat este.'])
PROGRAM.append(('set', ESC + b'R0'))

# The authors' own demonstration, exactly as they wrote it, escape sequences and all.  It is
# their file and is not in this repository; the part is left out where it is missing.
_EFFECTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'BRAILAB-archive', 'EFFECTS.DOC')
if os.path.isfile(_EFFECTS):
    part('Tizenegyes.')
    with open(_EFFECTS, 'rb') as f:
        for _line in f.read().rstrip(b'\x1a\r\n').split(b'\r\n'):
            if _line.strip():
                # a line at a time; the file itself turns line ends off (ESC C1), so its
                # sentences still run across them as the authors meant
                PROGRAM.append(('say', _line))
    PROGRAM.append(('set', BASE))

part('Vége.')
