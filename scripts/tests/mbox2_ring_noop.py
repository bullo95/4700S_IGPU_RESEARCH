#!/usr/bin/env python3
"""Test NO-OP du ring buffer via mbox 2 msg 0x23.
Envoie une entree avec mask=0 : le consommateur fera read-modify-write
sans modifier aucun bit (new = current & ~0 | 0 = current).
LECTURE SEULE en pratique : aucun registre n'est modifie.

ARG[0] = 0          (offset adresse, dans la limite 0x1FFFFF)
ARG[1] = 0          (mask = 0 → no-op)
ARG[2] = 0          (data = 0)
ARG[3] = 0x01000001 (command_type=1, sub_index=0, slot=1)
"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
M2_CMD, M2_RSP, M2_ARG = 0x03B10528, 0x03B10564, 0x03B10998
MSG_RING = 0x23
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
    log = open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/mbox2_ring.log", "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        rsp = rd(M2_RSP)
        print("mbox 2 RSP = %#010x" % rsp)
        if rsp not in DONE:
            print("mbox 2 pas prete (RSP=%#x), abandon" % rsp)
            return

        args = [
            0x00000000,  # ARG[0] = offset 0
            0x00000000,  # ARG[1] = mask 0 (no-op)
            0x00000000,  # ARG[2] = data 0
            0x01000001,  # ARG[3] = type=1, sub=0, slot=1
        ]

        log.write("%s RING-NOOP AVANT msg 0x23 args=%s\n" % (
            time.strftime("%H:%M:%S"),
            " ".join("%#010x" % a for a in args)))
        log.flush(); os.fsync(log.fileno()); os.sync()

        wr(M2_RSP, 0)
        for i, a in enumerate(args):
            wr(M2_ARG + i * 4, a)
        wr(M2_CMD, MSG_RING)

        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            st = rd(M2_RSP)
            if st in DONE:
                result = rd(M2_ARG)
                line = "msg 0x23 : statut=%#04x resultat=%#010x" % (st, result)
                print(line)
                log.write("%s RING-NOOP %s\n" % (time.strftime("%H:%M:%S"), line))
                log.flush(); os.fsync(log.fileno())
                return
            time.sleep(0.002)

        print("TIMEOUT - mbox 2 ne repond pas apres 3s")
        rsp2 = rd(M2_RSP)
        print("RSP apres timeout = %#010x" % rsp2)
        log.write("%s RING-NOOP TIMEOUT RSP=%#010x\n" % (time.strftime("%H:%M:%S"), rsp2))
        log.flush(); os.fsync(log.fileno())
    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
