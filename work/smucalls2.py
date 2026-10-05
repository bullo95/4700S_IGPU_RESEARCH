#!/usr/bin/env python3
"""List SMU BIOS-mailbox messages sent by a UEFI module (PE x64 or TE ia32).
Finds the function containing the write to SMN 0x3B10528, then every direct call to it
(and one level of wrappers) with the RequestId argument."""
import sys, struct, re, capstone, pefile
from capstone import x86

def image(path):
    b = open(path, "rb").read()
    if b[:2] == b"VZ":
        stripped = struct.unpack_from("<H", b, 6)[0]
        delta = stripped - 0x28
        return b, delta, 32, [(delta + 0x28, len(b) + delta)]
    pe = pefile.PE(data=b)
    mem = pe.get_memory_mapped_image()
    bits = 64 if pe.FILE_HEADER.Machine == 0x8664 else 32
    txt = [(s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize) for s in pe.sections if s.Name.startswith(b".text")]
    return mem, 0, bits, txt

def run(path, label=""):
    data, delta, bits, text = image(path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64 if bits == 64 else capstone.CS_MODE_32)
    md.detail = True; md.skipdata = True
    insns = []
    for lo, hi in text:
        insns += list(md.disasm(data[lo - delta:hi - delta], lo))
    addr_idx = {ins.address: k for k, ins in enumerate(insns)}
    targets = sorted({i.operands[0].imm for i in insns if i.mnemonic == "call" and i.operands and i.operands[0].type == x86.X86_OP_IMM})
    const = [i.address for i in insns if "0x3b10528" in i.op_str]
    svc = set()
    for c in const:
        cands = [t for t in targets if t <= c]
        if cands: svc.add(cands[-1])
    def callers(fset):
        out = []
        for k, ins in enumerate(insns):
            if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == x86.X86_OP_IMM and ins.operands[0].imm in fset:
                out.append(k)
        return out
    def fn_of(addr):
        c = [t for t in targets if t <= addr]
        return c[-1] if c else None
    def msg_at(k):
        ctx = insns[max(0, k - 25):k]
        if bits == 64:
            for c in reversed(ctx):
                if c.op_str.startswith(("edx, ", "rdx, ")) and c.mnemonic in ("mov", "lea", "xor", "or"):
                    return f"{c.mnemonic} {c.op_str}"
        else:
            pushes = [c for c in reversed(ctx) if c.mnemonic == "push"]
            return " / ".join(p.op_str for p in pushes[:4])
        return "?"
    print(f"## {label} {path.split('/')[-3][:45]} bits={bits} svc={[hex(s) for s in svc]}")
    level1 = callers(svc)
    wrappers = {}
    for k in level1:
        f = fn_of(insns[k].address)
        print(f"  L1 call@{insns[k].address:#07x} in fn {f:#07x}: msg <- {msg_at(k)}")
        wrappers.setdefault(f, 0); wrappers[f] += 1
    # one level up: callers of functions that call svc and pass edx through
    l2 = callers(set(wrappers) - svc)
    for k in l2:
        print(f"  L2 call@{insns[k].address:#07x} -> {insns[k].operands[0].imm:#07x}: edx/args <- {msg_at(k)}")

if __name__ == "__main__":
    for p in sys.argv[1:]:
        run(p)
