#!/usr/bin/env python3
"""Teste l'accessibilité de la SRAM MP1 via les DEUX paires SMN index/data.
Lecture seule, aucune écriture SMN."""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"

# Paire 1 : standard (smnread.py)
IDX1, DATA1 = 0x60, 0x64
# Paire 2 : secondaire (celle utilisée par smuq3read.py pour les registres mailbox)
IDX2, DATA2 = 0xB8, 0xBC

DENY = [(0x03B00000, 0x03C00000), (0x00003D64, 0x00003D68), (0x09000000, 0x0A000000)]

ADDRS = [
    0x03C00000,  # juste avant le +4
    0x03C00004,  # MP1_SRAM officiel
    0x03C00008,  # 2e mot
    0x03C00100,  # plus loin dans la SRAM
    0x03C00EBC,  # dispatcher (devrait contenir 0x004136xx)
    0x03C00EC0,  # dispatcher +4
    0x03C0CA44,  # fn_ptr sub0 (devrait contenir 0x0001BBF4)
    0x03C0CA48,  # fn_ptr sub0 +4
    # Contrôle : lire une adresse connue comme fonctionnelle
    0x00000000,  # NBIO device ID (devrait lire 0x14501022 ou similaire)
    0x0005A000,  # SMUIO (devrait donner une valeur non-FF)
]

def main():
    for a in ADDRS:
        if any(lo <= a < hi for lo, hi in DENY):
            print(f"  {a:#010x} : SKIP (deny list)")
            continue

    fd = os.open(CFG, os.O_RDWR)
    log = open(sys.argv[1], "a") if len(sys.argv) > 1 else sys.stdout

    try:
        print(f"{'Adresse':>12s}  {'0x60/0x64':>12s}  {'0xB8/0xBC':>12s}  Note")
        print("-" * 60)
        for a in ADDRS:
            if any(lo <= a < hi for lo, hi in DENY):
                continue
            # Paire 1
            os.pwrite(fd, struct.pack("<I", a), IDX1)
            v1 = struct.unpack("<I", os.pread(fd, 4, DATA1))[0]
            # Paire 2
            os.pwrite(fd, struct.pack("<I", a), IDX2)
            v2 = struct.unpack("<I", os.pread(fd, 4, DATA2))[0]
            
            note = ""
            if a == 0x00000000: note = "NBIO devid (contrôle)"
            elif a == 0x0005A000: note = "SMUIO (contrôle)"
            elif a == 0x03C00004: note = "MP1_SRAM base"
            elif a == 0x03C0CA44: note = "fn_ptr sub0"
            
            same = "=" if v1 == v2 else "≠"
            line = f"  {a:#010x}  {v1:#010x}  {v2:#010x}  {same}  {note}"
            print(line, flush=True)
            if log != sys.stdout:
                log.write(f"{time.strftime('%H:%M:%S')} SRAM-PROBE {line.strip()}\n")
                log.flush()
    finally:
        os.pwrite(fd, struct.pack("<I", 0), IDX1)
        os.close(fd)

if __name__ == "__main__":
    main()
