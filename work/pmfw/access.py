"""Acces MMIO (base l32r + offset l32i/s32i) dans un PMFW desassemble : renvoie [(fonction, pc, op, adresse)]."""
import re, struct
def accesses(name, lo=0x01000000, hi=0x04000000):
    fw = open(name + ".bin", "rb").read()
    lines = [l for l in open(name + ".dis")]
    out = []; func = 0; regs = {}
    for l in lines:
        m = re.match(r"\s*0x([0-9a-f]+)\s+(\S+)\s*(.*)", l)
        if not m: continue
        pc, op, args = int(m[1], 16), m[2], m[3]
        a = [x.strip() for x in args.split(",")]
        if op == "entry": func = pc; regs = {}; continue
        if op == "l32r":
            t = int(a[1], 16)
            regs[a[0]] = struct.unpack_from("<I", fw, t)[0] if 0 <= t < len(fw) - 3 else None
            continue
        mm = re.match(r"([ls])(8|16|32)[a-z]*(\.n)?$", op)
        if mm and len(a) == 3 and a[1] in regs and regs[a[1]] is not None:
            addr = regs[a[1]] + int(a[2], 0)
            if lo <= addr < hi: out.append((func, pc, op, addr))
        if a and a[0] in regs and not (mm and mm[1] == "s"): regs.pop(a[0], None)
        if op in ("retw", "retw.n"): regs = {}
    return out
