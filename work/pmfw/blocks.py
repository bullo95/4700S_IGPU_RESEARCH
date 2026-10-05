"""Liste (bit de config, adresse) des pages par IP ecrites par la routine 'offset 0x230' d'un PMFW."""
import re, subprocess, sys
def blocks(name, root):
    out = subprocess.run(["r2", "-q", "-a", "xtensa", "-b", "32", "-e", "scr.color=0", "-e", "asm.bytes=false",
                          "-c", f"pd 460 @ {root}", name + ".bin"], capture_output=True, text=True).stdout
    bit = None; base = {}; res = []
    for l in out.splitlines():
        m = re.search(r"0x([0-9a-f]{8})\s+(\S+)\s+(.*)", l)
        if not m: continue
        op = m[2]; a = [x.strip() for x in m[3].split(";")[0].split(",")]
        if op == "retw.n": break
        if op == "l32r":
            v = re.search(r"\]=0x([0-9a-f]+)", l); base[a[0]] = int(v[1], 16) if v else None
        if op in ("bbci", "bbsi"): bit = int(a[1])
        if op.startswith("s32i") and base.get(a[1]) is not None: res.append((bit, base[a[1]] + int(a[2], 0)))
    return res
if __name__ == "__main__":
    a = blocks("bc250_200", 0x31434); b = blocks("4700s_c0a", 0x2d0fc)
    print(len(a), len(b))
    sa = {x for _, x in a}; sb = {x for _, x in b}
    print("BC-250 seul :", " ".join(hex(x) for x in sorted(sa - sb)))
    print("4700S seul  :", " ".join(hex(x) for x in sorted(sb - sa)))
    print("ordre BC-250:", " ".join(f"b{k}:{x>>12&0xff:02x}" for k, x in a))
