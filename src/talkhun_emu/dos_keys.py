# -*- coding: utf-8 -*-
"""A key as DOS's INT 16h AH=0 gives it: AX = (scan code << 8) | character.

Standard library only, and nothing of the emulator's, so anything that hands keys to a DOS program can share
it (BraiLabPC does) and its tests need no Unicorn.
"""

#: Keys that come from the console as 00h or E0h and a second byte: arrows,
#: Home, End, Page Up and Down, Insert, Delete, F1 to F4.
EXTENDED = {
    'H': 0x4800, 'P': 0x5000, 'K': 0x4B00, 'M': 0x4D00,   # arrows
    'G': 0x4700, 'O': 0x4F00, 'I': 0x4900, 'Q': 0x5100,   # home/end/pgup/pgdn
    'R': 0x5200, 'S': 0x5300,                             # insert/delete
    ';': 0x3B00, '<': 0x3C00, '=': 0x3D00, '>': 0x3E00,   # F1-F4
}
#: Control keys with their own scan codes.
SIMPLE = {'\r': 0x1C0D, '\n': 0x1C0D, '\x1b': 0x011B, ' ': 0x3920,
          '\x08': 0x0E08, '\t': 0x0F09}

#: AX values of the keys a menu steers by.
K_ESC, K_UP, K_DOWN, K_LEFT, K_RIGHT = 0x011B, 0x4800, 0x5000, 0x4B00, 0x4D00
K_ENTER = 0x1C0D

#: Scan codes of the US layout's printable keys (IBM PC AT set 1), so a
#: program that looks at AH sees the key it would have on a real machine.
_SCAN_ROWS = (
    (0x02, '1234567890-='), (0x10, 'qwertyuiop[]'), (0x1E, "asdfghjkl;'`"),
    (0x2B, '\\zxcvbnm,./'),
)
_SHIFTED = dict(zip('!@#$%^&*()_+{}:"~|<>?', '1234567890-=[];\'`\\,./'))
SCAN = {k: start + i for start, keys in _SCAN_ROWS for i, k in enumerate(keys)}


def key_ax(byte):
    """The AX INT 16h gives for one byte of console input (msvcrt.getch()).

    The console gives its own OEM byte, which is what a DOS program expects in
    AL: BraiLabPC decoded it as CP852 and cut the Unicode code point to a byte,
    so á (A0h) reached the program as E1h and ő (8Bh) as the letter Q (#35).
    The byte goes through as it is; AH is the key's scan code where the key is
    on the US layout, else 0 (an accented letter has no fixed key).
    """
    c = chr(byte)
    if c in SIMPLE:
        return SIMPLE[c]
    if byte < 0x80:
        base = c.lower() if c.isalpha() else _SHIFTED.get(c, c)
        return (SCAN.get(base, 0) << 8) | byte
    return byte
