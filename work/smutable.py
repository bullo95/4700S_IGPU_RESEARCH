#!/usr/bin/env python3
"""Lecture statique de la table de messages hote->SMU (queue 0) d'un SMU_FW extrait d'une image BIOS.
Heuristique reprise de bc250-collective/amd_smu_reverse_engineering : entrees de 8 octets
(mot de garde, pointeur de fonction), fonction commencant par l'instruction Xtensa ENTRY (0x36)."""
import struct, sys, pspdir

def fw_of(path):
    img = open(path, "rb").read()
    for d, dofs, t, sub, rt, o, size, h, blob in pspdir.walk(img):
        if t == 0x08 and blob:
            return blob[0x100:0x100 + 0x40000], blob[0x60:0x64]

def u32(b, i): return struct.unpack_from("<I", b, i)[0]

def is_func(fw, a):
    return a and a + 4 <= len(fw) and (u32(fw, a) & 0xFF) == 0x36 and (u32(fw, a) & 0xFF0000) == 0

def gate_ok(g): return (g & ~(7 | 0x200)) == 0

def queue0(fw):
    # premiere entree valide = TestMessage ; la suivante = GetSmuVersion
    for i in range(0, len(fw) - 16, 4):
        if gate_ok(u32(fw, i)) and is_func(fw, u32(fw, i + 4)) and gate_ok(u32(fw, i + 8)) and is_func(fw, u32(fw, i + 12)):
            out, mid, j = [], 1, i
            while j + 8 <= len(fw) and gate_ok(u32(fw, j)) and mid <= 0x3F:
                f = u32(fw, j + 4)
                out.append((mid, f if is_func(fw, f) else 0))
                mid += 1; j += 8
            return i, out

NAMES = {0x0E: "RequestGfxclk", 0x0F: "QueryGfxclk", 0x18: "RequestActiveWgp", 0x19: "SetMinDeepSleepGfxclk",
         0x1A: "SetMaxDeepSleepDfllGfxDiv", 0x1E: "QueryActiveWgp", 0x2F: "GfxCacWeightOperation",
         0x37: "GetGfxFrequency", 0x38: "GetGfxVid", 0x39: "ForceGfxFreq", 0x3A: "UnForceGfxFreq",
         0x3B: "ForceGfxVid", 0x3C: "UnforceGfxVid", 0x3D: "GetEnabledSmuFeatures",
         0x0B: "RequestCorePstate", 0x0C: "QueryCorePstate", 0x11: "QueryVddcrSocClock", 0x13: "QueryDfPstate"}

if __name__ == "__main__":
    res = {}
    for p in sys.argv[1:]:
        fw, v = fw_of(p)
        base, tab = queue0(fw)
        res[p] = dict(tab)
        print(f"{p}: SMU {v[2]}.{v[1]}.{v[0]}  table queue0 @ {base:#x}, {len(tab)} entrees, {sum(1 for _, f in tab if f)} gestionnaires")
    print("\nmsg  " + "  ".join(f"{p.split('/')[-1][:18]:>18s}" for p in res) + "  nom")
    for mid in sorted(NAMES):
        print(f"0x{mid:02X} " + "  ".join(f"{('oui' if res[p].get(mid) else '-'):>18s}" for p in res) + f"  {NAMES[mid]}")
