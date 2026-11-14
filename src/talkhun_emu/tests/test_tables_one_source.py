"""The chip's tables exist twice on disk: src/pcf8200/tables.py, the library's, and pcf8200_tables.py here,
which this folder's programs and the portable bundle import by that flat name.  They must be the same file,
byte for byte, so that there is still only one set of tables: change the library's and copy it here.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_two_copies_are_one():
    with open(os.path.join(HERE, "pcf8200_tables.py"), "rb") as f:
        here = f.read().replace(b"\r\n", b"\n")
    with open(os.path.join(os.path.dirname(HERE), "pcf8200", "tables.py"), "rb") as f:
        library = f.read().replace(b"\r\n", b"\n")
    assert here == library
