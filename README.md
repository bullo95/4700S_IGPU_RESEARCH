# 4700S iGPU Research

Reverse engineering and reactivation research for the RDNA2 iGPU on the AMD 4700S Desktop Kit.

## Context

The AMD 4700S Desktop Kit uses the same "Ariel" die as the PS5 (Oberon) and BC-250 mining boards. The iGPU is physically present but disabled by firmware: the Power Management Firmware (PMFW, family 70) lacks GFX power-on handlers, and the GFX power island is shut off.

This project documents attempts to reactivate the iGPU by understanding and manipulating the SMU (System Management Unit) firmware paths.

## Structure

- `4700S-iGPU-journal_1.md` — Main research journal (source of truth)
- `TRAVAUX-2026-09-18.md` — BC-250 BIOS flash test report
- `scripts/` — Live test scripts (run on the 4700S machine via SSH)
  - `smnread.py` — SMN register reader with deny list
  - `smuq3read.py` — SMN reader via SMU msg 0x2A (grande file)
  - `mbox2_probe.py` — Mbox 2 (File 1) message probing
  - `tests/` — Targeted test scripts (ring buffer, msg 0x98, SRAM probe)
- `work/pmfw/` — PMFW analysis tools and disassembly
  - `4700s_c0a.dis`, `bc250_200.dis` — Full Xtensa disassembly (PMFW 70.18 / 88.6)
  - `queues.py` — Message queue table extractor
  - `trace.py` — Execution trace tool
  - `slots.py` — Window/slot mapper
  - `trace_powerup_gfx.txt` — BC-250 GFX power-on register trace
- `work/smutable.py` — SMU message table dumper
- `work/pspdir.py` — PSP directory parser

## Key findings

- PMFW family 70 (4700S) has **no GFX handlers** — all GFX messages return 0xFE
- PMFW family 88 (BC-250) has full GFX power-on sequence via msg 0x1B
- BC-250 BIOS flash on 4700S: writes OK but **no POST** (key chain "RBN" rejected by silicon expecting "CRD")
- SMN range `0x09xxxxxx` (GFX control pages) is **blocked for all initiators** including PMFW SMN windowed access — only reachable via Xtensa local window `0x010xxxxx` (internal bus)
- Host SMN writes to SMUIO registers (`0x0005Axxxx`) are **blocked** (write-protected by SMN fabric initiator filter)
- **SMU windowed writes** to SMUIO registers **work** — confirmed via msg 0x98 (MP1 initiator passes the filter)
- Guard byte analysis: 95 messages have guard=0x00 (always dispatched), 13 have guard=0x02 (blocked by security register)
- I2C path (msg 12/27/28) fully analyzed and closed — controller on MP1 local bus, not usable for VRM control

## Status

Active research. Current focus: exploiting the SMU windowed write path to SMUIO power registers (0x5A320-338) for GFX Phase 1 power-on sequence.

## Warning

These scripts perform low-level hardware manipulation. Incorrect writes can freeze the SMU (requiring power cycle) or potentially damage hardware. The deny lists in the scripts exist for good reasons.

## License

Research documentation and original tools. Firmware disassembly is provided for research purposes under fair use.
