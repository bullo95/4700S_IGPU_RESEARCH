#!/usr/bin/env python3
import os, struct, time

CFG = "/sys/bus/pci/devices/0000:00:00.0/config"
M2_CMD, M2_RSP, M2_ARG = 0x03B10528, 0x03B10564, 0x03B10998
DONE = {0x01, 0xFF, 0xFE, 0xFD, 0xFC}

fd = os.open(CFG, os.O_RDWR)

def rd(reg):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    return struct.unpack("<I", os.pread(fd, 4, 0xBC))[0]

def wr(reg, val):
    os.pwrite(fd, struct.pack("<I", reg), 0xB8)
    os.pwrite(fd, struct.pack("<I", val), 0xBC)

def send_multi(msg, args, budget=2.0):
    end = time.monotonic() + budget
    while rd(M2_RSP) not in DONE:
        if time.monotonic() > end:
            return -1, []
        time.sleep(0.002)
    wr(M2_RSP, 0)
    for i, a in enumerate(args):
        wr(M2_ARG + i * 4, a)
    wr(M2_CMD, msg)
    end = time.monotonic() + budget
    while time.monotonic() < end:
        st = rd(M2_RSP)
        if st in DONE:
            results = [rd(M2_ARG + i * 4) for i in range(6)]
            return st, results
        time.sleep(0.002)
    return -2, []

def fmt(vals):
    return " ".join("%#010x" % v for v in vals)

# Test 1: baseline
print("=== Test 1: tous args = 0 ===")
st, vals = send_multi(0x0A, [0, 0, 0, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

# Test 2: ARG[0]=0, ARG[1]=0x7B3C
print("=== Test 2: ARG[1]=0x7B3C ===")
st, vals = send_multi(0x0A, [0, 0x7B3C, 0, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

# Test 3: ARG[0]=0, ARG[1]=0x7B20
print("=== Test 3: ARG[1]=0x7B20 ===")
st, vals = send_multi(0x0A, [0, 0x7B20, 0, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

# Test 4: ARG[0]=0, ARG[1]=0x7000 (table mbox)
print("=== Test 4: ARG[1]=0x7000 ===")
st, vals = send_multi(0x0A, [0, 0x7000, 0, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

# Test 5: ARG[0]=0, ARG[1]=0x0000 (debut SRAM = debut firmware)
print("=== Test 5: ARG[1]=0x0000 ===")
st, vals = send_multi(0x0A, [0, 0x0000, 0, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

# Test 6: adresse dans ARG[2]
print("=== Test 6: ARG[2]=0x7B3C ===")
st, vals = send_multi(0x0A, [0, 0, 0x7B3C, 0, 0, 0])
print("  st=%#04x  ARG=%s" % (st, fmt(vals)))

os.close(fd)
