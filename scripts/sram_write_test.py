#!/usr/bin/env python3
"""Test msg 0x98 : écriture NOP dans la SRAM MP1 pour vérifier l'accessibilité SMN côté SMU.
Cible : SRAM 0x122BC (SMN 0x03C122C0), contient déjà 0x000000FF = la valeur que msg 0x98 écrit.
USAGE : sudo python3 sram_write_test.py /tmp/sram-write-test.log
Résultat attendu : statut 0x01, ARG = 0x000000FF (SMU peut atteindre SRAM)
ou ARG = 0xFFFFFFFF (aperture fermée pour le SMU aussi)."""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
Q3_CMD, Q3_RSP, Q3_ARG = 0x03B10A20, 0x03B10A80, 0x03B10A88
MSG_0x98 = 0x98
TARGET = 0x03C122C0  # SRAM 0x122BC = MP1_SRAM(0x03C00004) + 0x122BC
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}

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
        if time.monotonic() > end:
            raise RuntimeError("file 3 occupée — abandon")
        time.sleep(0.002)
    wr(Q3_RSP, 0)
    wr(Q3_ARG, arg)
    wr(Q3_ARG + 4, 0)
    wr(Q3_CMD, msg)
    end = time.monotonic() + budget
    while time.monotonic() < end:
        st = rd(Q3_RSP)
        if st in DONE:
            return st, rd(Q3_ARG)
        time.sleep(0.002)
    raise RuntimeError("délai dépassé — abandon")

def main():
    global fd
    if len(sys.argv) < 2:
        sys.exit("usage: sudo python3 sram_write_test.py <journal.log>")
    log = open(sys.argv[1], "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        line = f"{time.strftime('%H:%M:%S')} SRAM-WRITE-TEST msg=0x{MSG_0x98:02X} target={TARGET:#010x}"
        print(line, flush=True)
        log.write(line + "\n"); log.flush(); os.fsync(log.fileno()); os.sync()

        st, val = send(MSG_0x98, TARGET)

        line = f"{time.strftime('%H:%M:%S')} RÉSULTAT statut={st:#04x} ARG={val:#010x}"
        if st == 0x01 and val == 0x000000FF:
            line += "  → SMU PEUT atteindre SRAM via SMN"
        elif st == 0x01 and val == 0xFFFFFFFF:
            line += "  → aperture fermée AUSSI pour le SMU"
        elif st != 0x01:
            line += f"  → msg 0x98 refusé (statut {st:#04x})"
        else:
            line += f"  → valeur inattendue, à analyser"
        print(line, flush=True)
        log.write(line + "\n"); log.flush(); os.fsync(log.fileno())
    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
