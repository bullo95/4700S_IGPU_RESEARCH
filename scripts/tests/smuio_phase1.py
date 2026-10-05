#!/usr/bin/env python3
"""Phase 1 de l'allumage GFX : ecritures SMUIO depuis l'hote.
Reproduit la sequence du BC-250 (PMFW 88.6, fonction 0x29e44).

Registres cibles (SMN, via PCI config 0x60/0x64) :
  0x0005A320  SMUIO_PWRMGT    : clear bit 1
  0x0005A334  (non-documente) : set bits 4,5
  0x0005A330  (non-documente) : set bit 0, clear bits 1-3
  -- pause --
  0x0005A32C  PWR_MISC_CNTL   : set bits 0,1,2,4 ; clear bit 3

Verification : relecture apres chaque ecriture + GFX_GAP_PWROK (0x5ABE4).
Aucune ecriture dans la zone 0x09xxxxxx (bloquee).
"""
import os, struct, sys, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
SMN_IDX = 0x60
SMN_DAT = 0x64

fd = None
log = None

def smn_read(addr):
    os.pwrite(fd, struct.pack("<I", addr), SMN_IDX)
    return struct.unpack("<I", os.pread(fd, 4, SMN_DAT))[0]

def smn_write(addr, val):
    os.pwrite(fd, struct.pack("<I", addr), SMN_IDX)
    os.pwrite(fd, struct.pack("<I", val), SMN_DAT)

def log_reg(label, addr, val):
    line = "  %-20s SMN %#010x = %#010x" % (label, addr, val)
    print(line)
    log.write("%s %s\n" % (time.strftime("%H:%M:%S"), line.strip()))

def rmw(addr, label, or_mask, and_mask):
    """Read-modify-write : new = (old | or_mask) & and_mask"""
    old = smn_read(addr)
    new = (old | or_mask) & and_mask
    log_reg(label + " AVANT", addr, old)
    if old == new:
        print("    -> deja a la valeur cible, skip")
        log.write("%s    SKIP (pas de changement)\n" % time.strftime("%H:%M:%S"))
        return old
    smn_write(addr, new)
    time.sleep(0.001)
    readback = smn_read(addr)
    log_reg(label + " APRES", addr, readback)
    if readback != new:
        print("    *** READBACK DIFFER (attendu %#010x) ***" % new)
        log.write("%s    READBACK DIFFER attendu=%#010x\n" % (time.strftime("%H:%M:%S"), new))
    return readback

def read_status():
    """Lit les registres indicateurs."""
    print("\n--- Etat courant ---")
    for name, addr in [
        ("SMUIO_PWRMGT",   0x0005A320),
        ("reg_324",        0x0005A324),
        ("reg_328",        0x0005A328),
        ("PWR_MISC_CNTL",  0x0005A32C),
        ("reg_330",        0x0005A330),
        ("reg_334",        0x0005A334),
        ("reg_338",        0x0005A338),
        ("SOC_GAP_PWROK",  0x0005ABE0),
        ("GFX_GAP_PWROK",  0x0005ABE4),
        ("PWROK_GAP_CYC",  0x0005ABE8),
    ]:
        log_reg(name, addr, smn_read(addr))

def main():
    global fd, log
    logpath = sys.argv[1] if len(sys.argv) > 1 else "/tmp/smuio_phase1.log"
    log = open(logpath, "a")
    fd = os.open(CFG, os.O_RDWR)
    try:
        log.write("\n%s === SMUIO Phase 1 START ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        log.flush(); os.fsync(log.fileno()); os.sync()

        read_status()

        print("\n=== Phase 1 : ecritures SMUIO ===\n")

        # Etape 1 : 0x5A320 — clear bit 1 (disable i2c clock gate for power-up)
        print("[1/4] 0x5A320 : clear bit 1")
        rmw(0x0005A320, "SMUIO_PWRMGT", 0x00000000, 0xFFFFFFFD)

        # Etape 2 : 0x5A334 — set bits 4,5
        print("\n[2/4] 0x5A334 : set bits 4,5")
        rmw(0x0005A334, "reg_334", 0x00000030, 0xFFFFFFFF)

        # Etape 3 : 0x5A330 — set bit 0, clear bits 1-3
        print("\n[3/4] 0x5A330 : set bit 0, clear bits 1,2,3")
        rmw(0x0005A330, "reg_330", 0x00000001, 0xFFFFFFF1)

        # Pause (le BC-250 appelle une fonction d'attente avec arg=10)
        print("\n    pause 50 ms...")
        time.sleep(0.050)

        # Etape 4 : 0x5A32C — set bits 0,1,2,4 ; clear bit 3
        print("\n[4/4] 0x5A32C : set bits 0,1,2,4 ; clear bit 3")
        rmw(0x0005A32C, "PWR_MISC_CNTL", 0x00000017, 0xFFFFFFF7)

        # Pause stabilisation
        print("\n    pause 100 ms (stabilisation)...")
        time.sleep(0.100)

        read_status()

        log.write("%s === SMUIO Phase 1 END ===\n" % time.strftime("%H:%M:%S"))
        log.flush(); os.fsync(log.fileno())
        print("\nPhase 1 terminee. Verifier GFX_GAP_PWROK et les registres ci-dessus.")
    finally:
        os.pwrite(fd, struct.pack("<I", 0), SMN_IDX)
        os.close(fd)

if __name__ == "__main__":
    main()
