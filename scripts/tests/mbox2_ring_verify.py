#!/usr/bin/env python3
"""Verification du ring buffer : ecriture d'une valeur connue dans un registre
CLK0 a zero (SMN 0x16C00100, offset 0x100), puis relecture pour confirmer.
Restauration immediate apres le test.

ATTENTION : ecrit 0xCAFE0001 dans le registre 0x16C00100 puis le remet a 0.
"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
M2_CMD, M2_RSP, M2_ARG = 0x03B10528, 0x03B10564, 0x03B10998
SMN_IDX, SMN_DAT = 0x60, 0x64
MSG_RING = 0x23
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}
TARGET_OFFSET = 0x100
TARGET_SMN = 0x16C00000 + TARGET_OFFSET
TEST_VALUE = 0xCAFE0001

fd = None

def rd_ext(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr_ext(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def smn_read(addr):
    os.pwrite(fd, struct.pack("<I", addr), SMN_IDX)
    return struct.unpack("<I", os.pread(fd, 4, SMN_DAT))[0]

def send_ring(offset, mask, data, sub=0, slot=1, budget=3.0):
    end = time.monotonic() + budget
    while rd_ext(M2_RSP) not in DONE:
        if time.monotonic() > end:
            raise RuntimeError("mbox 2 occupee")
        time.sleep(0.002)
    arg3 = (1 << 24) | (sub << 20) | slot
    wr_ext(M2_RSP, 0)
    wr_ext(M2_ARG, offset)
    wr_ext(M2_ARG + 4, mask)
    wr_ext(M2_ARG + 8, data)
    wr_ext(M2_ARG + 12, arg3)
    wr_ext(M2_CMD, MSG_RING)
    end = time.monotonic() + budget
    while time.monotonic() < end:
        st = rd_ext(M2_RSP)
        if st in DONE:
            return st
        time.sleep(0.002)
    raise RuntimeError("timeout ring buffer")

def main():
    global fd
    log = open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/mbox2_ring.log", "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        before = smn_read(TARGET_SMN)
        print("AVANT : SMN %#010x = %#010x" % (TARGET_SMN, before))
        log.write("%s VERIFY AVANT %#010x = %#010x\n" % (time.strftime("%H:%M:%S"), TARGET_SMN, before))
        log.flush(); os.fsync(log.fileno()); os.sync()

        if before != 0:
            print("ATTENTION : registre pas a zero, abandon par securite")
            return

        st = send_ring(TARGET_OFFSET, 0xFFFFFFFF, TEST_VALUE)
        print("ring write : statut=%#04x" % st)

        time.sleep(0.05)

        after = smn_read(TARGET_SMN)
        print("APRES : SMN %#010x = %#010x" % (TARGET_SMN, after))
        log.write("%s VERIFY APRES %#010x = %#010x\n" % (time.strftime("%H:%M:%S"), TARGET_SMN, after))

        if after == TEST_VALUE:
            print("*** RING BUFFER FONCTIONNE : ecriture verifiee ***")
            log.write("%s VERIFY SUCCES ring buffer confirme\n" % time.strftime("%H:%M:%S"))
        elif after == 0:
            print("Registre inchange — consommateur inactif ou registre non mappable")
            log.write("%s VERIFY ECHEC registre inchange\n" % time.strftime("%H:%M:%S"))
        else:
            print("Valeur inattendue : %#010x (ni 0 ni %#010x)" % (after, TEST_VALUE))
            log.write("%s VERIFY INATTENDU %#010x\n" % (time.strftime("%H:%M:%S"), after))

        if after != 0:
            print("Restauration...")
            st2 = send_ring(TARGET_OFFSET, 0xFFFFFFFF, 0)
            time.sleep(0.05)
            restored = smn_read(TARGET_SMN)
            print("RESTAURE : SMN %#010x = %#010x (st=%#04x)" % (TARGET_SMN, restored, st2))
            log.write("%s VERIFY RESTAURE %#010x\n" % (time.strftime("%H:%M:%S"), restored))

        log.flush(); os.fsync(log.fileno())
    finally:
        os.pwrite(fd, struct.pack("<I", 0), SMN_IDX)
        os.close(fd)

if __name__ == "__main__":
    main()
