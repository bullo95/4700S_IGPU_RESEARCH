"""Graphe de references entre fonctions d'un PMFW Xtensa : call8 directs + l32r d'une adresse de fonction (callx8)."""
import re, collections, struct
def refgraph(name):
    fw = open(name + ".bin", "rb").read()
    entries = set(); lines = []
    for line in open(name + ".dis"):
        m = re.match(r"\s*0x([0-9a-f]+)\s+(\S+)\s*(.*)", line)
        if m:
            lines.append((int(m[1], 16), m[2], m[3]))
            if m[2] == "entry": entries.add(int(m[1], 16))
    callers = collections.defaultdict(set); func = 0
    for pc, op, args in lines:
        if op == "entry": func = pc
        elif op.startswith("call") and args.startswith("0x"):
            callers[int(args, 16)].add(func)
        elif op == "l32r":
            a = int(args.split(",")[-1], 16)
            if 0 <= a < len(fw) - 3:
                v = struct.unpack_from("<I", fw, a)[0]
                if v in entries: callers[v].add(func)
    return callers, entries
