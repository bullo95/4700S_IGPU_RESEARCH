#!/usr/bin/env python3
"""Lecture SMN en lecture seule par la paire index/data du pont racine (PCI 00:00.0, config 0x60/0x64).
Seul le registre d'index est ecrit (adresse SMN a lire), jamais un registre SMN.
Chaque adresse est journalisee et synchronisee sur disque AVANT la lecture : si la machine fige,
la derniere ligne du journal designe le registre fautif.
usage: sudo smnread.py journal.log 0xADDR [0xADDR ...]
A lancer apres 'rmmod k10temp' (k10temp utilise la meme paire index/data)."""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
IDX, DATA = 0x60, 0x64
# Bloc de la boite aux lettres MP1 et registres signales comme figeant le SMU : refuses.
# 0x09xxxxxx (pages de controle par IP du MP1) : la lecture de 0x0900E230 a fige la machine le 04/10/2026.
# 0x03C00000-0x04000000 (SRAM MP1) : aperture fermee par le PSP, lecture = 0xFFFFFFFF, ecriture msg 0x98 = gel SMU (05/10/2026).
# 0x01210000-0x01220000 : registres internes SMU (securite PMFW). Lecture de 0x01210BC0 a fige la machine le 05/10/2026.
# 0x03210000-0x03220000 : registres internes SMU (securite dispatch). Meme risque que 0x0121xxxx.
DENY = [(0x03B00000, 0x04000000), (0x00003D64, 0x00003D68), (0x09000000, 0x0A000000),
        (0x01210000, 0x01220000), (0x03210000, 0x03220000)]

def main():
    log = open(sys.argv[1], "a")
    addrs = [int(a, 16) for a in sys.argv[2:]]
    for a in addrs:
        if a & 3 or any(lo <= a < hi for lo, hi in DENY):
            sys.exit(f"adresse refusee : {a:#010x}")
    if any(l.startswith("k10temp ") for l in open("/proc/modules")):
        sys.exit("k10temp est charge : rmmod k10temp d'abord")
    fd = os.open(CFG, os.O_RDWR)
    try:
        for a in addrs:
            log.write(f"{time.strftime('%H:%M:%S')} AVANT {a:#010x}\n"); log.flush(); os.fsync(log.fileno())
            os.sync()
            os.pwrite(fd, struct.pack("<I", a), IDX)
            v1 = struct.unpack("<I", os.pread(fd, 4, DATA))[0]
            os.pwrite(fd, struct.pack("<I", a), IDX)
            v2 = struct.unpack("<I", os.pread(fd, 4, DATA))[0]
            line = f"{a:#010x} = {v1:#010x}" + ("" if v1 == v2 else f"  (2e lecture {v2:#010x})")
            print(line, flush=True)
            log.write(f"{time.strftime('%H:%M:%S')} {line}\n"); log.flush(); os.fsync(log.fileno())
    finally:
        os.pwrite(fd, struct.pack("<I", 0), IDX)
        os.close(fd)

if __name__ == "__main__":
    main()
