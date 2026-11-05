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

TALKHUN.COM is not distributed here.  By default it is fetched from the Internet
Archive item its authors approved; --from uses your own copy instead.  Either way
it has to be the exact file below.

    python patch_talkhun.py                      download, write TALKHUNS.COM here
    python patch_talkhun.py --from TALKHUN.COM   use a local copy
    python patch_talkhun.py --out D:\\BRAILAB\\TALKHUNS.COM
"""
import argparse, hashlib, os, ssl, urllib.error, urllib.request

ARCHIVE_URL = ('https://archive.org/download/brailab-pc-archive/'
               'brailab-pc-archive.zip/brailab-pc%2FTALKHUN.COM')
SHA256 = '01ff78039a9e595857fe205c4f2b44e4dc12636a3c61b2622e294c1d024708cf'

PATCHES = [
    # (offset in code space, original bytes, replacement)
    (0x5314, bytes.fromhex('8b16e75242ec'), bytes.fromhex('b4ff9090cd61')),
    (0x532a, bytes.fromhex('72ed'),         bytes.fromhex('72ec')),
    (0x537f, bytes.fromhex('80e403'),       bytes.fromhex('cd61c3')),
]
ORG = 0x100


def download():
    print('downloading TALKHUN.COM from archive.org')
    # archive.org's GoDaddy chain fails Python 3.13's strict X.509 default ("Basic
    # Constraints of CA cert not marked critical").  The chain and host name are
    # still verified, and patch() checks the file's SHA-256.
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    try:
        with urllib.request.urlopen(ARCHIVE_URL, timeout=60, context=ctx) as r:
            return r.read()
    except (urllib.error.URLError, OSError) as e:
        raise SystemExit('could not download TALKHUN.COM: %s\n'
                         'If you have your own copy, use --from FILE.' % e)


def patch(data, src, dst):
    have = hashlib.sha256(data).hexdigest()
    if have != SHA256:
        raise SystemExit('%s: %d bytes, SHA-256 %s\nexpected the 64941-byte '
                         'TALKHUN.COM of 20 June 2000, SHA-256 %s; refusing'
                         % (src, len(data), have, SHA256))
    img = bytearray(data)
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
    ap = argparse.ArgumentParser(description='Make TALKHUNS.COM for BRAISPK.')
    ap.add_argument('--from', dest='src', metavar='FILE',
                    help='your own TALKHUN.COM instead of the archive.org copy')
    ap.add_argument('--out', metavar='FILE', help='where to write (default: TALKHUNS.COM here)',
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TALKHUNS.COM'))
    args = ap.parse_args()
    if args.src:
        try:
            with open(args.src, 'rb') as f:
                data = f.read()
        except OSError as e:
            raise SystemExit('could not read %s: %s' % (args.src, e.strerror))
        patch(data, args.src, args.out)
    else:
        patch(download(), 'archive.org', args.out)
