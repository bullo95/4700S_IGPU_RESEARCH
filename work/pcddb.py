#!/usr/bin/env python3
"""EDK2 PCD database v6 decoder (PEI + DXE). Token n (1-based, global) -> value.
usage: pcddb.py <pei_db.raw> <dxe_db.raw> [token ...]"""
import struct, sys
SIZES = {0x1: 1, 0x2: 2, 0x4: 4, 0x8: 8, 0x3: 1}
NAMES = {0x0: "PTR", 0x1: "U8", 0x2: "U16", 0x4: "U32", 0x8: "U64", 0x3: "BOOL"}
def hdr(b):
    f = struct.unpack_from("<IIQIIIIIIIIHHH", b, 16)
    return dict(zip("bv length sku uninit ltt exmap guid string size skuid name lcount excount gcount".split(), f))
def db_tokens(b, first):
    h = hdr(b); out = {}
    for i in range(h["lcount"]):
        v = struct.unpack_from("<I", b, h["ltt"] + 4 * i)[0]
        off, dt, typ = v & 0xFFFFFF, (v >> 24) & 0xF, (v >> 28) & 0xF
        sz = SIZES.get(dt, 0)
        if typ != 0 or not sz: val = f"type={typ:x}"
        elif off + sz <= h["length"]: val = int.from_bytes(b[off:off + sz], "little")
        else: val = 0  # uninitialised area -> zero default
        out[first + i] = (NAMES.get(dt, "?"), off, typ, val)
    return h, out
def load(pei, dxe):
    hp, tp = db_tokens(open(pei, "rb").read(), 1)
    hd, td = db_tokens(open(dxe, "rb").read(), 1 + hp["lcount"])
    return {**tp, **td}
if __name__ == "__main__":
    t = load(sys.argv[1], sys.argv[2])
    want = [int(x, 16) for x in sys.argv[3:]] or sorted(t)
    for k in want:
        d, off, typ, val = t.get(k, ("-", 0, 0, "absent"))
        print(f"token {k:#05x} {d:4s} off={off:#06x} = {val:#x}" if isinstance(val, int) else f"token {k:#05x} {d:4s} = {val}")
