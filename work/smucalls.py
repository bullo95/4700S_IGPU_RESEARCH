#!/usr/bin/env python3
"""Find the SMU BIOS-mailbox service function (the one that touches SMN 0x3B10528) in a UEFI
PE/TE module and list every direct call to it with the message ID loaded just before."""
import sys, struct, capstone
from capstone import x86

def load(path):
    b = open(path, "rb").read()
    if b[:2] == b"VZ":  # TE image (PEI, IA32)
        machine, nsec, subsys, stripped, ep, codebase, imgbase = struct.unpack_from("<HBBHIIQ", b, 2)
        delta = stripped - 0x28
        return b, 32, (imgbase & 0xFFFFFFFF), delta
    import pefile
    pe = pefile.PE(data=b)
    mem = pe.get_memory_mapped_image()
    bits = 64 if pe.FILE_HEADER.Machine == 0x8664 else 32
    return mem, bits, 0, 0

def main(path):
    b, bits, base, delta = load(path)
    # TE: file offset f maps to RVA f+delta
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64 if bits == 64 else capstone.CS_MODE_32)
    md.detail = True
    code = b
    insns = list(md.disasm(code, delta))
    # find functions touching 0x3b10528 -> take nearest preceding function start heuristically
    touch = [i for i in insns if "0x3b10528" in i.op_str]
    starts = set()
    for t in touch:
        # walk back to a plausible prologue (after ret/int3 padding)
        idx = insns.index(t)
        j = idx
        while j > 0 and not (insns[j-1].mnemonic in ("ret", "int3", "jmp") and insns[j].mnemonic in ("push", "mov", "sub")):
            j -= 1
        starts.add(insns[j].address)
    print(f"{path}: bits={bits} svc functions at {[hex(s) for s in sorted(starts)]}")
    for k, ins in enumerate(insns):
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == x86.X86_OP_IMM and ins.operands[0].imm in starts:
            ctx = insns[max(0, k-12):k]
            msg = None
            if bits == 64:
                for c in reversed(ctx):
                    if c.mnemonic == "mov" and c.op_str.startswith("edx, ") :
                        msg = c.op_str.split(", ")[1]; break
            else:
                pushes = [c for c in reversed(ctx) if c.mnemonic == "push"]
                if len(pushes) >= 2: msg = pushes[1].op_str
            print(f"  call @{ins.address:#x} -> {ins.operands[0].imm:#x} msg={msg}   ctx: " + " | ".join(f"{c.mnemonic} {c.op_str}" for c in ctx[-6:]))

for p in sys.argv[1:]:
    main(p)
