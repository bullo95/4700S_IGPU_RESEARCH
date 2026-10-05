"""Constantes 32 bits construites par paires MOVW/MOVT (ARM, mode A32) et litteraux, dans un binaire PSP."""
import struct, sys, collections
def movpairs(b):
    out = []; last = {}
    for i in range(0, len(b) - 3, 4):
        w = struct.unpack_from("<I", b, i)[0]
        if (w & 0x0FF00000) == 0x03000000:    # MOVW
            last[(w >> 12) & 0xF] = (i, ((w >> 4) & 0xF000) | (w & 0xFFF))
        elif (w & 0x0FF00000) == 0x03400000:  # MOVT
            rd = (w >> 12) & 0xF; hi = ((w >> 4) & 0xF000) | (w & 0xFFF)
            lo = last.get(rd, (None, 0))
            if lo[0] is not None and i - lo[0] <= 64: out.append((i, (hi << 16) | lo[1]))
            else: out.append((i, hi << 16))
    return out
if __name__ == "__main__":
    for f in sys.argv[1:]:
        b = open(f, "rb").read()
        c = collections.Counter(v for _, v in movpairs(b) if 0x03000000 <= v < 0x04000000)
        print(f.split("/")[-1], len(movpairs(b)), " ".join(f"{k:#x}" for k in sorted(c))[:900])
