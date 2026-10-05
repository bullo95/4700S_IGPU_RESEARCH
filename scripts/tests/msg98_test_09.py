#!/usr/bin/env python3
"""Test msg 0x98 sur SMN 0x0900B100 (page 0x0B, zone inoccupee).
Envoie via mbox 3 (grande file / File 2).
Si le chemin SMN du PMFW vers 0x09xxxxxx fonctionne : statut 0x01.
Si le chemin est bloque : GEL SMU -> coupure secteur.

Mbox 3 : CMD=0x03B10A20 RSP=0x03B10A80 ARG=0x03B10A88
Acces via PCI config 0xB8/0xBC (MP1_SMN_EXT_ACCESS).
"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
Q3_CMD = 0x03B10A20
Q3_RSP = 0x03B10A80
Q3_ARG = 0x03B10A88
MSG_98 = 0x98
TARGET = 0x0900B100
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}

fd = None

def rd(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def main():
    global fd
    log = open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/msg98_test.log", "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        rsp = rd(Q3_RSP)
        print("Q3 RSP = %#010x" % rsp)
        if rsp not in DONE:
            print("Q3 pas prete, abandon")
            return

        line = "msg 0x98 -> SMN %#010x (page 0x0B zone vide)" % TARGET
        print(line)
        log.write("%s AVANT %s\n" % (time.strftime("%H:%M:%S"), line))
        log.flush(); os.fsync(log.fileno()); os.sync()

        wr(Q3_RSP, 0)
        wr(Q3_ARG, TARGET)
        wr(Q3_CMD, MSG_98)

        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            st = rd(Q3_RSP)
            if st in DONE:
                result = rd(Q3_ARG)
                line2 = "statut=%#04x resultat=%#010x" % (st, result)
                print(line2)
                log.write("%s APRES %s\n" % (time.strftime("%H:%M:%S"), line2))
                log.flush(); os.fsync(log.fileno())
                if st == 0x01:
                    print("*** CHEMIN SMN 0x09xxxxxx OUVERT POUR LE PMFW ***")
                else:
                    print("Refuse (statut %#x)" % st)
                return
            time.sleep(0.002)

        print("TIMEOUT 3s — probable gel SMU")
        rsp2 = rd(Q3_RSP)
        print("RSP apres timeout = %#010x" % rsp2)
        log.write("%s TIMEOUT RSP=%#010x\n" % (time.strftime("%H:%M:%S"), rsp2))
        log.flush(); os.fsync(log.fileno())
    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
