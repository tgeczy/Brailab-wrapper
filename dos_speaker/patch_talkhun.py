# -*- coding: utf-8 -*-
"""Make TALKHUNS.COM: TALKHUN.COM (v4, 1991-2003 BraiLab screen reader) with its
two printer-port touch points redirected to the BRAISPK TSR's INT 61h.

Everything TALKHUN ever does to the adapter funnels through two places, found by
disassembly and confirmed by tracing a spoken sentence under the Unicorn DOS host
(only these instructions touched 0x378-0x37A):

  0x537f  the 2-wire primitive:  and ah,3 / mov al,ah / mov dx,[base] /
          out dx,al / inc dx / inc dx / xor al,2 / out dx,al / ret
          AH = (clock<<1)|data.  Becomes  int 61h / ret.
  0x5314  inside the ready poll at 0x5308:  mov dx,[base] / inc dx / in al,dx
          then test al,10h (busy) / test al,20h (must be set).  Becomes
          mov ah,0FFh / nop / nop / int 61h, and the poll's retry jump is moved
          one byte earlier so it re-executes the int.  The poll clobbers DX
          itself (mov dx,0 / mov es,dx) and every caller reloads DX, so dropping
          the load is safe.

The TSR answers INT 61h: AH=0FFh -> AL=status (0x30 busy / 0x20 ready, bit 5
always set or TALKHUN reads a broken adapter and goes mute); any other AH ->
port write with bits AH&3.  The original file is never modified.
"""
import sys, os

PATCHES = [
    # (offset in code space, original bytes, replacement)
    (0x5314, bytes.fromhex('8b16e75242ec'), bytes.fromhex('b4ff9090cd61')),
    (0x532a, bytes.fromhex('72ed'),         bytes.fromhex('72ec')),
    (0x537f, bytes.fromhex('80e403'),       bytes.fromhex('cd61c3')),
]
ORG = 0x100


def patch(src, dst):
    img = bytearray(open(src, 'rb').read())
    for addr, old, new in PATCHES:
        off = addr - ORG
        have = bytes(img[off:off + len(old)])
        if have != old:
            raise SystemExit('%s: bytes at %04x are %s, expected %s -- not the '
                             'TALKHUN.COM this patcher knows; refusing'
                             % (src, addr, have.hex(), old.hex()))
        img[off:off + len(new)] = new
    open(dst, 'wb').write(img)
    print('%s -> %s: %d bytes, %d patches applied' % (src, dst, len(img), len(PATCHES)))


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else r'C:\git\Brailab-wrapper\BRAILAB-archive\TALKHUN.COM'
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TALKHUNS.COM')
    patch(src, dst)
