"""Re-desassemble un PMFW Xtensa fonction par fonction (ENTRY alignes sur 4) avec r2, pour eviter la desynchronisation."""
import subprocess, sys
name = sys.argv[1]
fw = open(name + ".bin", "rb").read()
ents = [i for i in range(0x1000, len(fw) - 3, 4) if fw[i] == 0x36 and (fw[i+1] & 0x0F) == 0x1 and fw[i+2] < 0x10]
cmds = []
for k, e in enumerate(ents):
    end = ents[k+1] if k + 1 < len(ents) else len(fw)
    cmds.append(f"pD {min(end - e, 0x4000)} @ {e}")
open(name + ".r2", "w").write("\n".join(cmds) + "\n")
out = subprocess.run(["r2", "-q", "-a", "xtensa", "-b", "32", "-e", "scr.color=0", "-e", "asm.bytes=false",
                      "-e", "asm.comments=false", "-i", name + ".r2", name + ".bin"], capture_output=True, text=True).stdout
open(name + ".dis", "w").write(out)
print(name, len(ents), "fonctions")
