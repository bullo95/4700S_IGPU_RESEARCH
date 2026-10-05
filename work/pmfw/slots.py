#!/usr/bin/env python3
"""Decode la table des fenetres SMN du MP1 : la fonction d'init ecrit des paires de bases 16 bits (SMN >> 20)
dans 0x03220000 + 4*k ; fenetre locale n = 0x01000000 + n * 1 Mo (hypothese du schema 'slots' PSP).
usage: slots.py nom_pmfw 0xFONCTION"""
import re, subprocess, sys
name, root = sys.argv[1], int(sys.argv[2], 16)
out = subprocess.run(["r2", "-q", "-a", "xtensa", "-b", "32", "-e", "scr.color=0", "-e", "asm.bytes=false",
                      "-c", f"pd 400 @ {root}", name + ".bin"], capture_output=True, text=True).stdout
regs, mem, base, slots = {}, {}, None, {}
for l in out.splitlines()[1:]:
    m = re.search(r"0x([0-9a-f]{8})\s+(\S+)\s+(.*)", l)
    if not m: continue
    op = m[2]; a = [x.strip() for x in m[3].split(";")[0].split(",")]
    if op in ("retw.n", "retw", "entry"): break
    if op == "l32r":
        v = re.search(r"\]=0x([0-9a-f]+)", l); regs[a[0]] = int(v[1], 16)
        if regs[a[0]] == 0x03220000: base = a[0]
    elif op in ("movi", "movi.n"): regs[a[0]] = int(a[1], 0) & 0xFFFFFFFF
    elif op in ("mov.n", "mov"): regs[a[0]] = regs.get(a[1])
    elif op == "s16i" and a[1] == "a1": mem[int(a[2], 0)] = regs.get(a[0])
    elif op in ("l32i.n", "l32i") and a[1] == "a1" and int(a[2], 0) == 0:
        lo, hi = mem.get(0), mem.get(2)
        regs[a[0]] = None if lo is None or hi is None else lo | hi << 16
    elif op in ("s32i.n", "s32i") and a[1] == base:
        k = int(a[2], 0) // 4; v = regs.get(a[0])
        slots[2 * k] = None if v is None else v & 0xFFFF
        slots[2 * k + 1] = None if v is None else v >> 16
for n in sorted(slots):
    s = slots[n]
    print(f"fenetre {n:2d}  local {0x01000000 + n * 0x100000:#010x}  ->  SMN {'?' if s is None else f'{s << 20:#010x}'}")
