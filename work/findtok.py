import sys,json,struct,capstone,pefile
from capstone import x86
tag=sys.argv[1]; toks={int(x,16) for x in sys.argv[2:]}
m=json.load(open(f"uefi/mods_{tag}.json"))
for name,lst in sorted(m.items()):
    path=lst[0][0]; b=open(path,"rb").read()
    if b[:2]==b"VZ":
        stripped=struct.unpack_from("<H",b,6)[0]; delta=stripped-0x28; code=b; base=delta; mode=capstone.CS_MODE_32
    else:
        try: pe=pefile.PE(data=b)
        except Exception: continue
        code=pe.get_memory_mapped_image(); base=0; mode=capstone.CS_MODE_64 if pe.FILE_HEADER.Machine==0x8664 else capstone.CS_MODE_32
    md=capstone.Cs(capstone.CS_ARCH_X86,mode); md.skipdata=True
    ins=list(md.disasm(code,base))
    for k,i in enumerate(ins):
        if i.mnemonic in ("mov","push") and any(i.op_str.endswith(f"{t:#x}") for t in toks) and ("ecx" in i.op_str or "edx" in i.op_str or i.mnemonic=="push"):
            nxt=" | ".join(f"{j.mnemonic} {j.op_str}" for j in ins[k+1:k+5])
            prv=" | ".join(f"{j.mnemonic} {j.op_str}" for j in ins[max(0,k-3):k])
            print(f"{name:30s} {i.address:#07x}: {i.mnemonic} {i.op_str}   << {prv}   >> {nxt}")
