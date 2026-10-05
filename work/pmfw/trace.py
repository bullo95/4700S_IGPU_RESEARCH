#!/usr/bin/env python3
"""Trace statique (ordre du code, sans suivre les branches) des acces MMIO d'une fonction PMFW et de ses appeles.
usage: trace.py nom_pmfw 0xFONCTION [profondeur]"""
import re, struct, sys
name, root = sys.argv[1], int(sys.argv[2], 16)
maxd = int(sys.argv[3]) if len(sys.argv) > 3 else 4
fw = open(name + ".bin", "rb").read()
F = {}; cur = None
for l in open(name + ".dis"):
    m = re.match(r"\s*0x([0-9a-f]+)\s+(\S+)\s*(.*)", l)
    if not m: continue
    pc, op, args = int(m[1], 16), m[2], m[3]
    if op == "entry" and pc % 4 == 0: cur = pc; F[cur] = []
    if cur is not None: F[cur].append((pc, op, [x.strip() for x in args.split(",")] if args else []))
def walk(f, d, stack):
    if f not in F or f in stack: return
    regs = {}; imm = {}
    for pc, op, a in F[f]:
        if op == "l32r":
            t = int(a[1], 16); regs[a[0]] = struct.unpack_from("<I", fw, t)[0] if 0 <= t < len(fw) - 3 else None; continue
        if op in ("movi", "movi.n"): imm[a[0]] = int(a[1], 0); continue
        mm = re.match(r"([ls])(8|16|32)[a-z]*(\.n)?$", op)
        if mm and len(a) == 3 and regs.get(a[1]) is not None:
            ad = regs[a[1]] + int(a[2], 0)
            if 0x01000000 <= ad < 0x04000000:
                v = f" <- {imm[a[0]]:#x}" if mm[1] == "s" and a[0] in imm else ""
                print(f"{'  ' * d}{pc:#07x} {'W' if mm[1] == 's' else 'R'} {ad:#010x}{v}")
        if op.startswith("call") and a and a[0].startswith("0x"):
            t = int(a[0], 16)
            if d < maxd and t in F:
                print(f"{'  ' * d}{pc:#07x} -> {t:#x}"); walk(t, d + 1, stack | {f})
        if op in ("retw", "retw.n") and pc > F[f][0][0] + 4 and False: break
        if a and op not in ("s32i", "s32i.n", "s16i", "s8i") and not op.startswith("b"):
            if a[0] in regs and op != "l32r": regs.pop(a[0], None)
            if a[0] in imm and op not in ("movi", "movi.n"): imm.pop(a[0], None)
walk(root, 0, frozenset())
