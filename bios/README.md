# Images BIOS — AMD 4700S Desktop Kit

Images BIOS utilisées dans le cadre de la recherche sur la réactivation de l'iGPU RDNA2 (die « Ariel »).
Puce SPI : Winbond W25Q128.V (16 Mo). Flash avec `flashrom -p internal`.

## Images

### 4700S_pre_flash_read_20260918.bin

**Dump original** lu sur la carte avant toute modification (18/09/2026).
Sert de baseline et de point de restauration.

- BIOS révision **C0A**, PMFW 70.16.0
- `IgpuControl=0` (iGPU masquée, device PCI = dummy `1022:145a`)
- UMA = 0 (pas de VRAM réservée)
- APCB : CBSG flag=1, param=0x0002 (UMA 2 Mo par défaut)
- SHA256 : `3f2455d33e481b693ac4bcbfa4e7a990e4877d6a02d3ef8b4d52cbac06f840b7`

### 4700S_dump_igpu_Bbis.bin

**Image B-bis** — modification intermédiaire historique.

- `IgpuControl=1` (iGPU exposée comme `1002:13fd`)
- SHA256 : `089072ad21338387efb650840b161f271c3cf169149fbd02bdbdfc12600b6aec`

### 4700S_dump_igpu_D_cbsuma512.bin

**Image D** — la configuration de référence stable.

- `IgpuControl=1` → iGPU visible en PCI comme `1002:13fd` (class VGA 0x0300)
- UMA 512 Mo réservés (visibles dans `RCC_CONFIG_MEMSIZE`)
- Boot stable, amdgpu détecte RDNA2 (8 blocs IP dont SMU)
- L'init échoue à `gmc_v10_0` : l'îlot GFX est hors tension
- Seule modification par rapport au dump original : PCD `IgpuControl` dans le NVRAM UEFI (pas dans l'APCB)
- SHA256 : `6985a3ef42f13e015d77c39ea940aef2485abe2aa222812f712460c3369e159d`

### 4700s_imgE_apcb_gnb.bin

**Image E** — Image D + tokens APCB alignés sur les valeurs BC-250.

Base : image D. Modifications APCB (offset BIOS 0xAB1000, bloc primaire) :

| Offset APCB | Avant | Après | Token |
|---|---|---|---|
| +0x010 | 0xBF | 0x5F | Checksum (byte-sum mod 256 = 0) |
| +0x221 | 0x00 | 0x01 | MEMG type 0x07 — flag activation |
| +0x223 | 0x00 | 0x20 | MEMG type 0x07 — paramètre |
| +0x2CD | 0x00 | 0x01 | MEMG type 0x08 — flag activation |
| +0x2CF | 0x00 | 0x20 | MEMG type 0x08 — paramètre |
| +0x462 | 0x02 | 0x20 | CBSG type 0x0D — paramètre GNB (LE16) |

**Résultat du test (06/10/2026)** : POST OK, iGPU visible, mais registres SMUIO power identiques à image D — l'îlot GFX reste éteint. Les tokens APCB (MEMG/CBSG) n'influencent pas les registres power. Le verrou est à 100% dans le PMFW signé (RSA-2048, chaîne CRD fusée).

- SHA256 : `cbbc30e71241bebc24f827aa5a7e2cef7cf4dcff5066035dc696b1adb98410a5`

### now_20261004.bin

**Snapshot** du contenu SPI au 04/10/2026, après que la carte ait été remise sous BIOS officiel par l'utilisateur.

- Révision BIOS différente de l'original (2,3 M octets diffèrent du dump pré-flash)
- APCB entièrement à zéro (UMA=0, MEMG=0, CBSG=0)
- `IgpuControl=0` → pas d'iGPU
- SHA256 : `15730a30a0f7a0419ff140a7f28645c7d9a6e471600cc1d87b0f3e252b110898`

## Puce SPI

| Propriété | Valeur |
|---|---|
| Modèle | Winbond W25Q128.V |
| Taille | 16 Mo (128 Mbit) |
| Interface | SPI |
| Protection écriture | Désactivée |
| Backup externe | CH341A (filet de sécurité) |

## Avertissement

Ces images sont spécifiques à cette carte AMD 4700S Desktop Kit. Ne les flasher sur aucune autre machine. Un flash incorrect peut bricker la carte — un programmeur SPI externe (CH341A) est indispensable comme filet de sécurité.
