"""Decoupe un .dis en fonctions et calcule une signature (suite des mnemoniques) pour apparier deux PMFW."""
import re, hashlib, collections
def funcs(name):
    F = collections.OrderedDict(); cur = None
    for l in open(name + ".dis"):
        m = re.match(r"\s*0x([0-9a-f]+)\s+(\S+)", l)
        if not m: continue
        pc, op = int(m[1], 16), m[2]
        if op == "entry" and pc % 4 == 0: cur = pc; F[cur] = []
        if cur is not None: F[cur].append(op)
    return {f: hashlib.md5(" ".join(ops).encode()).hexdigest() for f, ops in F.items()}, {f: len(o) for f, o in F.items()}
