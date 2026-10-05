#!/usr/bin/env python3
"""Lecture SMN par le SMU lui-meme : file 3 (grande file) du PMFW, message 0x2A = lecture SMN sans filtrage.
Le SMU accede avec ses privileges a des plages que l'hote ne peut pas lire (ex. pages par IP SMN 0x09xxxxxx).
Boite aux lettres file 3 (rw-r-r-0644/bc250-core-unlock, confirmee par la table du PMFW) :
  commande SMN 0x03B10A20, reponse 0x03B10A80, argument 0x03B10A88 ; acces hote par config PCI 00:00.0 0xB8/0xBC.
LECTURE SEULE : n'envoie que 0x2A. Les messages 0x2B/0x2C (ecriture) ne sont jamais envoyes par ce script.
Chaque adresse est journalisee et synchronisee sur disque avant l'envoi.
usage: sudo smuq3read.py journal.log 0xADDR [0xADDR ...]"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
Q3_CMD, Q3_RSP, Q3_ARG = 0x03B10A20, 0x03B10A80, 0x03B10A88
MSG_SMN_READ = 0x2A
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}
# Bloc MP1 (boites aux lettres) : le lire par la file 3 fige le SMU (Keshas-dev). Zone GC/RLC basse : idem.
# 0x03C00000+ = SRAM MP1, aperture fermee, ecriture = gel SMU (05/10/2026).
DENY = [(0x03B00000, 0x04000000), (0x00003D64, 0x00003D68)]

fd = None

def rd(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def send(msg, arg, budget=2.0):
    end = time.monotonic() + budget
    while rd(Q3_RSP) not in DONE:
        if time.monotonic() > end: raise RuntimeError("file 3 occupee - abandon, ne pas reessayer")
        time.sleep(0.002)
    wr(Q3_RSP, 0); wr(Q3_ARG, arg); wr(Q3_ARG + 4, 0); wr(Q3_CMD, msg)
    end = time.monotonic() + budget
    while time.monotonic() < end:
        st = rd(Q3_RSP)
        if st in DONE: return st, rd(Q3_ARG)
        time.sleep(0.002)
    raise RuntimeError("delai depasse - abandon, ne pas reessayer")

def main():
    global fd
    log = open(sys.argv[1], "a")
    addrs = [int(a, 16) for a in sys.argv[2:]]
    for a in addrs:
        if a == 0 or a & 3 or any(lo <= a < hi for lo, hi in DENY):
            sys.exit(f"adresse refusee : {a:#010x}")
    fd = os.open(CFG, os.O_RDWR)
    try:
        for a in addrs:
            log.write(f"{time.strftime('%H:%M:%S')} Q3-AVANT {a:#010x}\n"); log.flush(); os.fsync(log.fileno()); os.sync()
            st, v = send(MSG_SMN_READ, a)
            line = f"{a:#010x} = {v:#010x}" + ("" if st == 0x01 else f"  (statut {st:#04x})")
            print(line, flush=True)
            log.write(f"{time.strftime('%H:%M:%S')} Q3 {line}\n"); log.flush(); os.fsync(log.fileno())
    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
