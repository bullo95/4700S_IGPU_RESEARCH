#!/usr/bin/env python3
"""Test msg 0x98 sur registres SMUIO pour verifier l'acces ecriture SMU windowed.

msg 0x98 (grande file, guard=0x00) ecrit 0xFF a SMN[ARG] via le fenetrage
SMU interne (0x02Cxxxxx -> slot 0x03220038). Initiateur = MP1 (SMU),
different de l'hote dont les ecritures SMUIO sont rejetees.

Cibles :
  1. 0x5A874 — registre non-reference par le PMFW, valeur courante 0x00
  2. 0x5A868 — registre RMW par le PMFW, valeur courante 0x01

Si readback change -> le SMU windowed a acces ecriture SMUIO.
Si readback inchange -> meme le SMU est bloque (seul le bus local
Xtensa 0x011xxxxx fonctionne).

Mbox 3 : CMD=0x03B10A20 RSP=0x03B10A80 ARG=0x03B10A88
Acces via PCI config 0xB8/0xBC (MP1_SMN_EXT_ACCESS).
"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
Q3_CMD = 0x03B10A20
Q3_RSP = 0x03B10A80
Q3_ARG = 0x03B10A88
MSG_98 = 0x98
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}

fd = None
log = None

def rd(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def smn_read(addr):
    os.pwrite(fd, struct.pack("<I", addr), 0x60)
    return struct.unpack("<I", os.pread(fd, 4, 0x64))[0]

def emit(msg):
    print(msg)
    log.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))

def send_msg98(target_smn, label):
    """Envoie msg 0x98 avec ARG=target_smn. Retourne (statut, arg_retour)."""
    emit("")
    emit("--- %s : msg 0x98 -> SMN 0x%05X ---" % (label, target_smn))

    before = smn_read(target_smn)
    emit("  AVANT (lecture hote) : 0x%08X" % before)

    rsp = rd(Q3_RSP)
    if rsp not in DONE:
        emit("  Q3 pas prete (RSP=0x%08X), abandon" % rsp)
        return None, None

    log.flush(); os.fsync(log.fileno()); os.sync()

    wr(Q3_RSP, 0)
    wr(Q3_ARG, target_smn)
    wr(Q3_CMD, MSG_98)

    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        st = rd(Q3_RSP)
        if st in DONE:
            result = rd(Q3_ARG)
            emit("  Statut = 0x%02X, ARG retour = 0x%08X" % (st, result))
            time.sleep(0.010)
            after = smn_read(target_smn)
            emit("  APRES (lecture hote) : 0x%08X" % after)
            if after != before:
                emit("  *** ECRITURE CONFIRMEE (0x%08X -> 0x%08X) ***" % (before, after))
            else:
                emit("  Inchange (ecriture ignoree ou registre RAZ)")
            return st, after
        time.sleep(0.002)

    emit("  TIMEOUT 3s — probable gel SMU !")
    rsp2 = rd(Q3_RSP)
    emit("  RSP apres timeout = 0x%08X" % rsp2)
    return None, None

def main():
    global fd, log
    logpath = sys.argv[1] if len(sys.argv) > 1 else "/tmp/msg98_smuio.log"
    log = open(logpath, "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        log.write("\n%s === msg 0x98 SMUIO TEST START ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))

        emit("Verification Q3 :")
        rsp = rd(Q3_RSP)
        emit("  Q3 RSP = 0x%08X" % rsp)
        if rsp not in DONE:
            emit("Q3 pas prete, abandon")
            return

        # Test 1 : registre hors-PMFW (0x5A874, actuellement 0x00)
        st1, _ = send_msg98(0x0005A874, "Test 1 (hors-PMFW)")

        if st1 is None:
            emit("\nTest 1 en timeout, arret. Verifier si SMU est fige.")
            return

        # Test 2 : registre ref-PMFW (0x5A868, actuellement 0x01)
        st2, _ = send_msg98(0x0005A868, "Test 2 (ref-PMFW)")

        emit("")
        emit("=== RESUME ===")
        emit("  0x5A874 : statut 0x%02X" % (st1 or 0))
        emit("  0x5A868 : statut 0x%02X" % (st2 or 0))

        log.write("%s === msg 0x98 SMUIO TEST END ===\n" % time.strftime("%H:%M:%S"))
        log.flush(); os.fsync(log.fileno())
    finally:
        os.pwrite(fd, struct.pack("<I", 0), 0x60)
        os.close(fd)

if __name__ == "__main__":
    main()
