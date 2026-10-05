#!/usr/bin/env python3
"""Sonde la boite aux lettres 2 du PMFW (File 1) en lecture seule.
Etape 1 : lit le registre RSP de mbox 2 via PCI config 0x60/0x64 pour verifier qu'elle repond.
Etape 2 (si --msg0a) : envoie msg 0x0A (telemetrie/SRAM reader) avec ARG=0 pour tester la communication.
Etape 3 (si --sram ADDR) : envoie msg 0x0A pour lire la SRAM a l'adresse donnee.

Boite aux lettres mbox 2 (File 1, handler ring buffer + SRAM reader) :
  CMD = SMN 0x03B10528, RSP = SMN 0x03B10564, ARG = SMN 0x03B10998
  Acces hote par config PCI 00:00.0 0xB8/0xBC (MP1_SMN_EXT_ACCESS).

La lecture RSP est un acces SMN direct (hote→SMN, PAS par le SMU), sans risque de gel recursif.

usage: sudo python3 mbox2_probe.py journal.log [--msg0a] [--sram 0xADDR]
       rmmod k10temp avant si necessaire (conflit sur 0x60/0x64, pas sur 0xB8/0xBC)."""
import argparse, os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
M2_CMD = 0x03B10528
M2_RSP = 0x03B10564
M2_ARG = 0x03B10998
MSG_SRAM_READ = 0x0A
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}
DENY_SRAM = [(0x03B00000, 0x04000000)]

fd = None

def rd(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def send_m2(msg, args, budget=2.0):
    end = time.monotonic() + budget
    while rd(M2_RSP) not in DONE:
        if time.monotonic() > end:
            raise RuntimeError("mbox 2 occupee - abandon")
        time.sleep(0.002)
    wr(M2_RSP, 0)
    for i, a in enumerate(args):
        wr(M2_ARG + i * 4, a)
    wr(M2_CMD, msg)
    end = time.monotonic() + budget
    while time.monotonic() < end:
        st = rd(M2_RSP)
        if st in DONE:
            return st, rd(M2_ARG)
        time.sleep(0.002)
    raise RuntimeError("delai depasse - mbox 2 ne repond pas")

def main():
    global fd
    p = argparse.ArgumentParser()
    p.add_argument("journal", help="fichier journal (append)")
    p.add_argument("--msg0a", action="store_true", help="envoyer msg 0x0A (telemetrie) avec ARG=0")
    p.add_argument("--sram", type=lambda x: int(x, 16), help="adresse SRAM a lire via msg 0x0A (hex)")
    args = p.parse_args()

    log = open(args.journal, "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        log.write(f"{time.strftime('%H:%M:%S')} MBOX2-PROBE debut\n")
        log.flush(); os.fsync(log.fileno())

        rsp = rd(M2_RSP)
        line = f"mbox 2 RSP ({M2_RSP:#010x}) = {rsp:#010x}"
        print(line, flush=True)
        log.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        log.flush(); os.fsync(log.fileno())

        if rsp == 0xFFFFFFFF:
            print("ATTENTION : RSP = 0xFFFFFFFF — mbox 2 peut etre inaccessible ou le SMU est gele.")
            return

        if rsp not in DONE and rsp != 0:
            print(f"ATTENTION : RSP inattendu ({rsp:#010x}), mbox 2 peut etre en cours de traitement.")

        if args.msg0a or args.sram is not None:
            sram_addr = args.sram if args.sram is not None else 0
            log.write(f"{time.strftime('%H:%M:%S')} MBOX2-AVANT msg 0x0A ARG={sram_addr:#010x}\n")
            log.flush(); os.fsync(log.fileno()); os.sync()
            st, val = send_m2(MSG_SRAM_READ, [sram_addr])
            line = f"msg 0x0A (ARG={sram_addr:#010x}) : statut={st:#04x}, resultat={val:#010x}"
            print(line, flush=True)
            log.write(f"{time.strftime('%H:%M:%S')} MBOX2 {line}\n")
            log.flush(); os.fsync(log.fileno())
    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
