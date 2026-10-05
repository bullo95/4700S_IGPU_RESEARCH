#!/usr/bin/env python3
"""Minimal AMD PSP/BIOS directory walker: lists every entry of every $PSP/$PL2/$BHD/$BL2
directory in a 16 MiB flash image, with a sha256 of each blob.
usage: pspdir.py image.bin [--dump outdir]"""
import hashlib, struct, sys, os

NAMES = {0x00: "AMD_PUB_KEY", 0x01: "PSP_BOOTLOADER", 0x02: "PSP_SECURE_OS", 0x03: "PSP_RECOVERY_BL",
         0x04: "PSP_NV_DATA", 0x08: "SMU_FW", 0x09: "SEC_DBG_KEY", 0x0A: "OEM_PSP_PUB_KEY",
         0x0B: "SOFT_FUSE_CHAIN", 0x0C: "PSP_TRUSTLETS", 0x0D: "TRUSTLET_KEY", 0x12: "SMU_FW2",
         0x13: "PSP_EARLY_UNLOCK", 0x20: "IP_DISCOVERY", 0x21: "WRAPPED_IKEK", 0x22: "TOKEN_UNLOCK",
         0x24: "SEC_GASKET", 0x25: "MP2_FW", 0x28: "DRIVER_ENTRIES", 0x2D: "S0I3_DRIVER",
         0x30: "ABL0", 0x31: "ABL1", 0x32: "ABL2", 0x33: "ABL3", 0x34: "ABL4", 0x35: "ABL5",
         0x36: "ABL6", 0x37: "ABL7", 0x3A: "FW_PSP_WHITELIST", 0x40: "PL2_DIR", 0x42: "DXIO_PHY_FW",
         0x44: "USB_PHY", 0x45: "TOS_SEC_POLICY", 0x47: "DRTM_TA", 0x49: "BIOS_L2_DIR_PTR",
         0x50: "KEY_DB", 0x51: "KEY_DB_TOS", 0x55: "SPL_TABLE", 0x5A: "MSMU_FW", 0x5C: "SPIROM_CFG",
         0x5D: "MPIO_FW", 0x60: "APCB", 0x61: "APOB", 0x62: "BIOS_BIN", 0x63: "APOB_NV",
         0x64: "PMU_CODE", 0x65: "PMU_DATA", 0x66: "MICROCODE", 0x68: "APCB_BACKUP",
         0x6A: "MP2_CFG", 0x70: "BIOS_L2_DIR"}

def off(addr, size=0x1000000):
    a = addr & 0x3FFFFFFFFFFFFFFF
    return a & (size - 1)

def walk(img):
    out = []
    for magic in (b"$PSP", b"$PL2", b"$BHD", b"$BL2"):
        i = 0
        while (i := img.find(magic, i)) >= 0:
            cnt = struct.unpack_from("<I", img, i + 8)[0]
            if 0 < cnt < 128:
                bios = magic in (b"$BHD", b"$BL2")
                esz = 24 if bios else 16
                for n in range(cnt):
                    e = i + 16 + n * esz
                    if bios:
                        t, rt, fl, sub, size, src, dst = struct.unpack_from("<BBBBIQQ", img, e)
                    else:
                        t, sub, rsv, size, src = struct.unpack_from("<BBHIQ", img, e)
                        rt = 0
                    o = off(src)
                    blob = img[o:o + size] if size and size < 0x1000000 and o + size <= len(img) else b""
                    out.append((magic.decode(), i, t, sub, rt, o, size,
                                hashlib.sha256(blob).hexdigest()[:16] if blob else "-", blob))
            i += 4
    return out

if __name__ == "__main__":
    img = open(sys.argv[1], "rb").read()
    dump = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--dump" else None
    for d, dofs, t, sub, rt, o, size, h, blob in walk(img):
        name = NAMES.get(t, "?")
        print(f"{d}@{dofs:07x} type={t:02x}/{sub:02x} inst={rt:02x} {name:18s} off={o:07x} size={size:#8x} sha={h}")
        if dump and blob:
            os.makedirs(dump, exist_ok=True)
            open(f"{dump}/{d[1:]}_{dofs:07x}_{t:02x}_{sub:02x}_{rt:02x}_{o:07x}.bin", "wb").write(blob)
