"""Tables de messages hote->SMU (toutes les files) d'un PMFW : entrees {mot, fonction} de 8 octets, chaque file commence par TestMessage."""
import struct
def queues(n):
    fw = open(n + ".bin", "rb").read()
    test = struct.unpack_from("<I", fw, 0x7074)[0]
    starts = [a for a in range(0x7000, 0x9000, 4) if struct.unpack_from("<I", fw, a + 4)[0] == test]
    Q = []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else s + 0x300
        tab = {}
        for m in range(1, (end - s) // 8 + 1):
            f = struct.unpack_from("<I", fw, s + 8 * (m - 1) + 4)[0]
            if f and f < len(fw) and fw[f] == 0x36: tab[m] = f
        Q.append((s, tab))
    return Q
