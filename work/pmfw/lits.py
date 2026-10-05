#!/usr/bin/env python3
"""Constantes 32 bits chargees par l32r dans un PMFW desassemble (r2 pD), avec la fonction (dernier ENTRY) qui les charge."""
import re, struct, sys, collections
def lits(name):
    fw = open(name + ".bin", "rb").read()
    out = collections.defaultdict(set); func = 0
    for line in open(name + ".dis"):
        m = re.match(r"\s*0x([0-9a-f]+)\s+(\S+)\s*(.*)", line)
        if not m: continue
        pc, op, args = int(m[1], 16), m[2], m[3]
        if op == "entry": func = pc
        elif op == "l32r":
            a = int(args.split(",")[-1], 16)
            if 0 <= a < len(fw) - 3:
                out[struct.unpack_from("<I", fw, a)[0]].add(func)
    return out
if __name__ == "__main__":
    a, b = lits(sys.argv[1]), lits(sys.argv[2])
    print(len(a), len(b))
