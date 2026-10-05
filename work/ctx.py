import sys,pefile,capstone,re
from capstone import x86
path=sys.argv[1]; lo=int(sys.argv[2],16); hi=int(sys.argv[3],16)
pe=pefile.PE(path); mem=pe.get_memory_mapped_image()
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64); md.detail=True
def s_at(a):
    m=re.match(rb"[\x20-\x7e\n\t]{4,}",mem[a:a+120])
    return m.group().decode().replace("\n","\\n") if m else None
for i in md.disasm(mem[lo:hi],lo):
    note=""
    for op in i.operands:
        if op.type==x86.X86_OP_MEM and op.mem.base==x86.X86_REG_RIP:
            tgt=i.address+i.size+op.mem.disp
            s=s_at(tgt); note=f'   ; [{tgt:#x}] "{s}"' if s else f"   ; [{tgt:#x}]"
    print(f"{i.address:#07x}: {i.mnemonic} {i.op_str}{note}")
