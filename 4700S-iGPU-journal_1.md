# Réactivation de l'iGPU RDNA2 sur AMD 4700S Desktop Kit

Journal technique — carte ASRock, silicium « Ariel » (APU PS5 recyclé), même die que la BC-250.

## Objectif

Faire fonctionner l'iGPU RDNA2 de la 4700S, désactivé d'usine, pour en faire une console de salon (rendu sur l'iGPU, sortie vidéo via une carte AMD Polaris dans le slot PCIe, la 4700S n'ayant aucune sortie vidéo native).

## Résultat à ce stade (18/09/2026)

- **Acquis (BIOS)** : l'iGPU n'était pas coupé par fusible mais par un simple strap logiciel. Réactivé via BIOS modifié. Il s'énumère nativement en `1002:13fd`, 512 Mo de VRAM réservés (visibles dans `RCC_CONFIG_MEMSIZE`), amdgpu détecte l'architecture RDNA2 complète (8 blocs IP dont `smu`).
- **Acquis (Linux)** : amdgpu patché se lie à `01:00.0`, charge la VBIOS BC-250 depuis un fichier (`Fetched VBIOS from file`, ATOM BIOS `113-AMDRBN-003`), reconnaît la carte comme `CYAN_SKILLFISH 0x1002:0x13FD`, exécute le post ATOM. L'init échoue à `gmc_v10_0` sw_init.
- **Bloquant actuel** : **l'îlot d'alimentation GPU (GC + MMHUB + IH) est hors tension.** Tous ses registres lisent `0xFFFFFFFF`. Le PMFW (SMU) répond depuis l'hôte mais **n'implémente aucun message GFX** (`0xFE UnknownCmd` sur tout ce qui touche au GFX). Le bridage restant est dans le firmware SMU ou dans la config qui lui est passée (ABL/APCB/fuse).
- **Prochaine étape** : comparer les blobs SMU (`SMU_FW` 0x08, `SMU_FW2` 0x12) et ABL (0x30-0x37) des BIOS 4700S et BC-250 avec psptool (voir « Ensuite »).

## Matériel

| Élément | Détail |
|---|---|
| Carte | AMD 4700S Desktop Kit, ASRock, SoC « Ariel » |
| Puce BIOS | Winbond **W25Q128.V** (16 Mo, SPI), **non protégée** en écriture |
| GPU d'affichage actuel | GTX 1650 (slot PCIe, bus 03, nouveau) |
| GPU d'affichage cible | vieille carte AMD Polaris (à confirmer) |
| OS | Debian 13, noyau `6.12.107+deb13-amd64` (précédemment ZimaOS, abandonné) |
| Programmeur SPI | CH341A (filet de sécurité ; devient **prérequis** si transplantation de firmware PSP) |
| PMFW (SMU) | version **70.16.0** (`GetSmuVersion` → `0x00461000`), DriverIf v8 |

## Diagnostic initial

- La 4700S et la BC-250 partagent le die « Ariel ». La BC-250 garde le GPU (24-40 CU) et sacrifie des cœurs CPU ; la 4700S fait l'inverse (GPU désactivé).
- Sur la 4700S d'origine, `01:00.0` remonte comme **Dummy Function `1022:145a`** : le GPU est masqué au niveau PCI, remplacé par un bouche-trou.
- Le plafond **PCIe 2.0 x4** du slot est **matériel** (le slot pend derrière le southbridge FCH A77E, LnkCap = 5GT/s x4). Non contournable. Sans impact pour une console : ne ralentit que le chargement, pas le rendu.
- **amdgpu ne connaît pas `0x13FD`** : la table PCI liste `13F9, 13FA, 13FB, 13FC, 13FE, 143F` en Cyan Skillfish — seul l'ID de la 4700S manque. Retrait volontaire d'AMD.

## Analyse BIOS (reverse engineering)

Comparaison du BIOS 4700S (dump réel + image C09 AMD) avec deux BIOS BC-250 récupérés sur GitHub, désassemblés avec PSPTool, UEFIExtract, IFRExtractor et Capstone.

Constats clés :
- L'iGPU est masqué **par le BIOS x86**, pas par le PSP. Le code d'init GPU (`AmdNbioGfxARI`) est présent et identique à la BC-250.
- L'activation dépend d'un PCD interne **`IgpuControl`** (token 0x4B) : défaut **0** sur la 4700S (désactivé), **1** sur la BC-250. Aucun menu BIOS pour le changer (le menu « GFX Configuration » a été vidé).
- Quand `IgpuControl=0`, `AmdNbioBaseARIPei` applique une table de straps NBIF : device ID forcé à `145a`, fonction GFX masquée.
- La réserve **UMA** (VRAM) est pilotée par l'ABL (code PSP ARM, **signé mais lisible**) via une surcharge dans une petite table CBS de l'APCB (entrées 5 et 6 = UmaMode / UmaSize), **verrouillée à 0** sur la 4700S.
- Rien de tout cela n'est signé côté APCB/PCD : modifiable.
- Ce qui reste **physique** : la FPU des cœurs Zen 2 est réduite (2 ports au lieu de 4, visible sur le die). Sans rapport avec le GPU.
- **Nouveau (18/09)** : `IgpuControl=1` suffit à exposer le GPU sur PCI et à faire passer l'UMA, mais **ne met pas l'îlot GPU sous tension**. Sur la BC-250, quelque chose (x86 `AmdNbioGfxARI` via message SMU, ou ABL → PMFW) allume l'îlot au boot. Ce « quelque chose » manque ou est court-circuité sur la 4700S.

## Chronologie des modifications BIOS

Toutes construites sur le **dump réel** de la carte (sha256 d'origine `c766a860…afc3`, sauvegardé sur le cloud en double). Flashées avec un `flashrom` statique compilé pour l'occasion (`flashrom -p internal`).

| Image | Modifs | Résultat |
|---|---|---|
| **B** | IgpuControl=1 + UMA 8 Go (mauvaise interprétation du champ) | GPU exposé en `13fd`, mais **pas de VRAM** (8 Go injectables impossible sous 4 Go) ; boucle de redémarrages au boot froid |
| **B-bis** | IgpuControl=1 seul, APCB d'origine | Boot stable du 1er coup, GPU en `13fd`, pas de VRAM. Image « sûre » de repli |
| **D** ✅ | IgpuControl=1 + surcharge CBS UMA = 512 Mo (bons offsets) | **VRAM 512 Mo réservée** (plage e820 `0x450000000-0x46FFFFFFF`), boot stable. **Image actuellement en puce** |

Octets modifiés par l'image D (vs dump d'origine) :
- `0xE6A258-59`, `0xE6A587` : IgpuControl → 1
- `0xAB1460` : UmaMode → 1 ; `0xAB1462` : UmaSize → 0x200 (512 Mo)
- `0xAB1010` : checksum APCB
- sha256 image D : `6985a3ef…f5a9`

## État côté Linux (Debian 13)

amdgpu tente de se lier à `01:00.0`. Chaque étape franchie débloque la suivante :

1. `invalid ip discovery binary signature` → **résolu** en fournissant `ip_discovery.bin` (extrait de la BC-250, checksum validé) dans `/lib/firmware/amdgpu/`. amdgpu détecte alors les blocs : `nv_common, gmc_v10_0, navi10_ih, psp, smu, dm, gfx_v10_0, sdma_v5_0`.
2. `Unable to locate a BIOS ROM` → **résolu** par patch du module (lecture de `/lib/firmware/amdgpu/vbios.bin`). Log : `Fetched VBIOS from file` / `ATOM BIOS: 113-AMDRBN-003`.
3. `BUG: kernel NULL pointer dereference` dans `psp_early_init+0xfc` → **résolu**. Cause : `0x13FD` absent de la table PCI, la carte tombait dans le fallback générique `CHIP_IP_DISCOVERY`, le flag `AMD_APU_IS_CYAN_SKILLFISH2` n'était pas posé, `psp->funcs` restait NULL. Correctif : ajout de `0x13FD` dans la table PCI (`amdgpu_drv.c`) et dans le test du flag (`amdgpu_device.c`).
4. `Unable to set WC memtype for the aperture base` → `sw_init of IP block <gmc_v10_0> failed -22` → **en cours, bloquant**. Cause identifiée : `GCMC_VM_FB_LOCATION_BASE`, `GCMC_VM_FB_OFFSET`, `GRBM_STATUS` lisent tous `0xFFFFFFFF` (îlot GPU éteint). amdgpu en déduit une base VRAM `0xFFFFFF000000` et une adresse physique d'aperture absurde. Log révélateur : `VRAM: 512M 0x0000FFFFFF000000 - 0x000100001EFFFFFF`.

Voies VBIOS tentées et écartées avant le patch :
- **Écriture directe en VRAM** (BAR0) : impossible, la VRAM n'est pas initialisée tant qu'amdgpu n'a pas la VBIOS (œuf/poule).
- **Injection VFCT via ACPI override (initramfs)** : le noyau lit bien le fichier mais **rejette la signature** (`ACPI OVERRIDE: Unknown signature`) — VFCT n'est pas une table ACPI standard remplaçable.

## Patch amdgpu (fonctionnel)

Sources : `apt source linux` → `~/linux-6.12.107/`. Build **hors arbre contre les headers Debian** (obligatoire : vermagic `6.12.107+deb13-amd64` et CRC `modversions` du noyau distribué — un build dans l'arbre source donne un vermagic `6.12.107` refusé au chargement).

### Fichiers modifiés (`drivers/gpu/drm/amd/amdgpu/`)

| Fichier | Modification | Rôle |
|---|---|---|
| `amdgpu_bios.c` | `#include <linux/firmware.h>` ; fonction `amdgpu_read_bios_from_file()` (`request_firmware("amdgpu/vbios.bin")`, `kmemdup`, `check_atom_bios(adev->bios, adev->bios_size)`) ; appel en tête de `amdgpu_get_bios_apu()` | VBIOS depuis fichier (approche communauté BC-250) |
| `amdgpu_drv.c` | ligne `{0x1002, 0x13FD, PCI_ANY_ID, PCI_ANY_ID, 0, 0, CHIP_CYAN_SKILLFISH\|AMD_IS_APU},` après l'entrée `0x13FE` | Reconnaissance de la 4700S comme Cyan Skillfish |
| `amdgpu_device.c` (≈ l. 2022) | `(adev->pdev->device == 0x13FD) \|\|` ajouté au test qui pose `AMD_APU_IS_CYAN_SKILLFISH2` | Sélection des fonctions PSP v11.0.8, SMU 11.8 |
| `amdgpu_trace.h` | `#define TRACE_INCLUDE_PATH .` (au lieu de `../../drivers/gpu/drm/amd/amdgpu`) | Build hors arbre |
| `Makefile` | `CFLAGS_amdgpu_trace_points.o += -I$(src)` (fin de fichier) | Build hors arbre |
| `gfxhub_v2_0.c` | `dev_info(... "4700S dbg GC: FB_BASE=... FB_TOP=... FB_OFFSET=... GRBM_STATUS=...")` avant `base &= GCMC_VM_FB_LOCATION_BASE__FB_BASE_MASK;` | **Debug temporaire**, à retirer |

Pièges rencontrés et corrigés :
- Prototype réel `check_atom_bios(uint8_t*, size_t)` ; lire `fw->size` **avant** `release_firmware`.
- Le `-I` global vers `include/trace` de l'arbre source ne suffit pas pour `TRACE_INCLUDE_PATH` ; il faut le fix canonique ci-dessus.
- `-j$(nproc)` (16 threads) fait exploser la RAM sur les fichiers `display/dc/dml*` → **`-j4 -l6`** obligatoire (15-20 min).
- GNOME met la machine en veille après 20 min d'inactivité pendant le build : `gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'`.
- Le noyau refuse de décompresser un `.ko.xz` produit par `xz -T0` (`decompression failed with status 6`, même avec `--check=crc32 --lzma2=dict=1MiB`). **Installer le `.ko` non compressé** (29 Mo après `strip --strip-debug`), kmod et l'initramfs l'acceptent.
- Un shell rouvert perd les variables (`$D` vide → `install … /` a posé le module à la racine et laissé l'ancien `.xz` en place). Chemins en dur ou re-déclarer les variables.
- `modinfo` est dans `/usr/sbin` (hors PATH utilisateur).

### Procédure de build/install

```bash
cd ~/linux-6.12.107
make -C /lib/modules/$(uname -r)/build M=$PWD/drivers/gpu/drm/amd/amdgpu -j4 -l6 modules 2>&1 | tee ~/build-amdgpu.log | grep -E 'error|Error|amdgpu\.ko'
strip --strip-debug drivers/gpu/drm/amd/amdgpu/amdgpu.ko
M=/lib/modules/$(uname -r)/kernel/drivers/gpu/drm/amd/amdgpu
sudo rm -f $M/amdgpu.ko*
sudo install -m 644 drivers/gpu/drm/amd/amdgpu/amdgpu.ko $M/
sudo depmod -a && sudo update-initramfs -u
sudo modprobe -r amdgpu; sudo modprobe amdgpu
```

État système :
- Module d'origine sauvegardé : `/root/amdgpu-orig/amdgpu.ko.xz`.
- `/etc/modprobe.d/amdgpu-blacklist.conf` : `blacklist amdgpu` — chargement **manuel uniquement** (`sudo modprobe amdgpu`) tant que l'init n'aboutit pas. Option existante `discovery=2` dans modprobe.d.
- Le module se charge « out-of-tree, unsigned » (taint `OE`), Secure Boot désactivé. Un probe qui échoue proprement (`-22`) se décharge avec `modprobe -r` ; un oops nécessite un reboot.

## Diagnostic de l'îlot GPU (18/09)

### Cartographie MMIO depuis l'espace utilisateur

Lecture directe du BAR5 (registres, `0xFD400000`, 512 Ko) via `/dev/mem`, amdgpu déchargé, `COMMAND=0003`. Offsets **en octets** dans le BAR (bases SOC15 Navi1x, segment 0 ; certains offsets restent à valider — voir remarque).

| Bloc | Registre | Offset BAR | Valeur lue | Verdict |
|---|---|---|---|---|
| NBIF | (offset supposé `RCC_CONFIG_MEMSIZE`) | `0x37F8` | `0x00400000` | répond (offset à vérifier, amdgpu lit 512M par sa propre voie) |
| IH (OSSSYS) | `IH_RB_BASE` | `0x4280` | `0xFFFFFFFF` | **mort** |
| GC | `GRBM_STATUS` | `0x8010` | `0xFFFFFFFF` | **mort** |
| GC | `GCMC_VM_FB_LOCATION_BASE` | `0x6A70` | `0xFFFFFFFF` | **mort** |
| DF | `DramBaseAddress0` | `0x1C110` | `0x0000001F` | répond |
| MP0 (PSP) | `C2PMSG_35` (offset supposé) | `0x5818C` | `0xFFFFFFFF` | offset probablement faux |
| MP0 (PSP) | `C2PMSG_81` | `0x58244` | `0x004FA6EC` | répond |
| MP1 (SMU) | `C2PMSG_66` (msg) | `0x58A08` | `0x00000000` | répond |
| MP1 (SMU) | `C2PMSG_82` (arg) | `0x58A48` | `0x00000000` | répond |
| MP1 (SMU) | `C2PMSG_90` (resp) | `0x58A68` | `0x00000001` | répond, idle, dernier msg OK |
| THM | `TCON_CUR_TMP` | `0x59800` | `0x6CBB0FEF` | répond (température plausible) |
| MMHUB | `MMMC_VM_FB_LOCATION_BASE` | `0x6A040` | `0xFFFFFFFF` | **mort** |

Conclusion : PSP, SMU, DF, THM, NBIF vivants ; **GC + MMHUB + IH morts** = îlot d'alimentation GPU complet hors tension (pas un simple GFXOFF, qui laisserait MMHUB et IH accessibles). Ni BAR, ni décodage PCI, ni strap : c'est le PMFW qui n'a pas allumé l'îlot.

### Dialogue SMU depuis l'hôte

Protocole SMU11 : écrire 0 dans `C2PMSG_90`, l'argument dans `C2PMSG_82`, l'ID dans `C2PMSG_66`, poller `C2PMSG_90` (≠0). Réponses : `0x01` OK, `0xFC` occupé, `0xFD` prérequis manquant, `0xFE` **commande inconnue**, `0xFF` échec. Retour dans `C2PMSG_82`.

Script utilisé : `smu(msg, arg)` en Python sur le mmap `/dev/mem` du BAR5 (offsets ci-dessus).

| Message (ID `smu_v11_8_ppsmc.h`) | Arg | Réponse | Retour | Lecture |
|---|---|---|---|---|
| `TestMessage` 0x01 | `0x12345678` | `0x01` | `0x12345679` | canal OK (arg+1 attendu) |
| `GetSmuVersion` 0x02 | 0 | `0x01` | `0x00461000` | PMFW **70.16.0** |
| `GetDriverIfVersion` 0x03 | 0 | `0x01` | `0x8` | DriverIf v8 |
| `GetEnabledSmuFeatures` 0x3D | 0 / 1 | `0xFE` | — | inconnu du firmware |
| `QueryGfxclk` 0x0F | 0 | `0xFE` | — | **inconnu** |
| `GetGfxFrequency` 0x37 | 0 | `0xFE` | — | **inconnu** |
| `GetGfxVid` 0x38 | 0 | `0xFE` | — | **inconnu** |
| `QueryActiveWgp` 0x1E | 0 | `0xFE` | — | **inconnu** |
| `QueryCorePstate` 0x0C | 0 | `0x01` | `0x0` | CPU OK |
| `QueryDfPstate` 0x13 | 0 | `0x01` | `0x3` | DF P-state 3 |
| `QueryVddcrSocClock` 0x11 | 0 | `0x01` | `0x4E6` | SOC clk 1254 MHz |

Conclusion : **le PMFW 70.16.0 de la 4700S ne connaît aucun message GFX**, alors que les messages CPU/DF/SoC de la même table fonctionnent. Deux explications possibles, à départager :
- **build PMFW différent** de la BC-250 (GFX compilé hors) → transplantation des entrées SMU du BIOS BC-250 ;
- **même binaire, gestionnaires GFX désactivés au boot** d'après un fuse ou un paramètre passé par l'ABL (APCB) → travail sur l'ABL/APCB.

Table `smu_v11_8_ppsmc.h` du noyau 6.12 : IDs **`Rsvd1/2/3` = 0x0A, 0x0D, 0x14** et trous (0x08-0x09, 0x10, 0x12, 0x15, 0x1F-0x2B, 0x2D, 0x32-0x33) — candidats pour des messages réservés au BIOS (mise sous tension de l'îlot ?). `RequestActiveWgp`/`QueryActiveWgp` (0x18/0x1E) : le nombre de WGP actifs se négocie avec le SMU — c'est là qu'on saura combien de CU le die accepte. **Ne pas envoyer les IDs réservés en aveugle** (un vrai message BIOS avec un mauvais argument peut geler le SoC) ; les identifier d'abord par désassemblage.

## Comparaison PSP / SMU / x86 4700S vs BC-250 (18/09, fait)

Images : dump D (4700S), C09 AMD (4700S), BC-250 `Robin5.00` (MrrZed0/bc-250-bios) et `BC250_2.00.bin` (kenavru/BC-250). Outils dans `work/` du dépôt : `pspdir.py` (parseur PSP maison, psptool pip plante sur l'image 4700S), `smucalls2.py` (messages SMU envoyés par un module UEFI), `pcddb.py` (base PCD EDK2 v6), extraction UEFI via `uefi-firmware-parser`.

**Firmwares PSP : deux familles et deux chaînes de clés distinctes.**

| Entrée | 4700S (D / C09) | BC-250 (2.00 / Robin5) |
|---|---|---|
| SMU_FW / SMU_FW2 | **70.16.0** / 70.17.0 | **88.6.0** / 88.7.1 |
| Clé de signature SMU | `b6f9ac22…` | `8b8df41e…` |
| ABL (0x30-0x34) | 33.5.38 / 34.2.9, clé `c551a330…` | 33.17.9 / 34.4.6, clé `663ca522…` |
| PSP_SECURE_OS | 0.32.0.10, clé `8c77cdf9…`, tag **« CRD »** (Cardinal) | 0.28.0.x, clé `5a3587b5…`, tag **« RBN »** (Robin) |
| PSP_BOOTLOADER (0x01) | **« dummy binary »** (12 octets) → bootloader en ROM on-chip | 44 Ko réels en flash |

- Même base de code SMU (chaînes initiales identiques, nom produit embarqué), mais le build 4700S fait **~19 Ko de moins** (0x36439 vs 0x3add9) : cohérent avec un PMFW compilé **sans GFX** (confirme l'hypothèse « build PMFW différent »).
- SMU_FW2 : aucune chaîne lisible (compressé ou chiffré), non analysable statiquement.
- **Transplanter seulement SMU_FW/SMU_FW2 : écarté.** Signé par une clé que la chaîne CRD ne connaît pas → rejet quasi certain → pas de POST.

**Côté x86 (AGESA).** Mailbox BIOS→SMU = SMN `0x3B10528` (ID), `0x3B10564` (réponse), `0x3B10998-9AC` (args), service `NbioSmuServiceRequestV10`. Messages envoyés par `AmdNbioSmuV10Dxe` (BC-250 = build debug avec chaînes) :
- `0x05` EnableSmuFeatures (masques PCD, 4700S tokens 0x120:0x121, BC-250 0x152:0x106 — **les deux à 0**, jamais écrits : pas un levier) ; bit 6 effacé si IgpuControl=0 (déjà levé par l'image D).
- `0x2A` SetCoreTCtlMax, `0x17` DcBtc CPU : présents des deux côtés.
- **`0x2B` SetGfxTCtlMax et `0x18` DcBtc GFX : BC-250 seulement.** Messages de configuration, pas d'allumage.
- Aucun module x86 n'allume l'îlot GFX : sur la BC-250, c'est le PMFW 88.x qui le fait seul. Sur la 4700S, le PMFW 70.x ne le fait pas. **Le verrou est dans un firmware signé, pas dans quelque chose de patchable côté x86/PCD/APCB.**
- Tailles : `AmdNbioGfxARIPei` 6,7 Ko (4700S) vs 87 Ko (BC-250, debug) ; module GFX PEI BC-250 = UMA seulement.

**Matériel.** Le rail `APU_VDDCR_GFX_RUN` existe et est alimenté sur la carte 4700S (0,83 V mesurés, forum Badcaps) : le VRM GFX est bien monté.

**Communauté.** jwagnervaz (juil. 2026) : aucune image 4700S ne boote sur BC-250 (ABL/SMU différents). Un rapport **non confirmé** (mrfrakes) : 4700S C08 aurait booté sur BC-250 avec GPU externe. S'il est vrai, le silicium accepte les deux chaînes, et l'inverse (BIOS BC-250 complet sur 4700S) devient plausible.

**Test fait le 18/09 : flash de `Robin5.00` (BIOS BC-250 complet) → écriture VERIFIED, mais aucun POST.** Prouvé par l'historique des boots (journal persistant) : aucun boot avec ce BIOS. Carte remise sous C0A par l'utilisateur le 04/10. Détails et méthode : [TRAVAUX-2026-09-18.md](TRAVAUX-2026-09-18.md). Le silicium refuse la chaîne RBN.

**Piste restante : flasher un BIOS BC-250 complet (testé, échec)** (chaîne RBN entière, PMFW 88.x avec GFX). Risque réel de non-POST (clés, entraînement GDDR6, différences de carte) → **CH341A + pince SOIC-8 obligatoires avant**, dump d'origine à portée.

## Ensuite

1. ~~**Comparer les blobs PSP des deux BIOS**~~ (fait, voir section précédente) (`psptool`, venv : `~/.local/share/pipx/venvs/psptool/bin/psptool`) : entrées **`0x08` SMU_FW**, **`0x12` SMU_FW2**, **`0x30-0x37` ABL**. Extraction (`-X -d <dir> -e <entry> -o …`), `sha256sum`, `strings` pour les versions. Les images BIOS ne sont pas sur la Debian (`~/Bios/` ne contient que `ip_discovery.bin`) : faire cette étape sur la machine de reverse ou rapatrier les images.
   - Blobs SMU **différents** → transplanter SMU_FW + SMU_FW2 de la BC-250 dans l'image D (signés AMD pour le même die ; vérifier que la version n'est pas antérieure — anti-rollback). Risque de non-POST réel : **CH341A prêt et dump d'origine à portée avant de flasher**.
   - Blobs SMU **identiques** → comparer les ABL, puis chercher dans l'APCB (à côté de UmaMode/UmaSize) un token « GFX disable » passé au PMFW.
2. **Trouver le message d'allumage dans le BIOS BC-250** : le code x86 écrit l'ID dans `MP1_SMN_C2PMSG_66`, SMN **`0x03B10A08`** (arg `0x03B10A48`, réponse `0x03B10A68`). Dans `AmdNbioGfxARI*`, `AmdNbioBaseARI*`, `AmdNbioSmuV*` extraits : chercher `08 0A B1 03`, ou la routine `SmuServiceRequest` unique, lister ses appelants et les immédiats chargés avant l'appel. Les IDs présents dans le module Gfx et pas ailleurs (0x0A/0x0D/0x14 ?) sont les candidats. Même exercice sur le dump 4700S pour voir ce qui court-circuite l'appel.
3. Une fois l'îlot allumé (depuis l'hôte via `/dev/mem`, puis intégré dans `nv_common_early_init` si nécessaire à chaque boot) : recharger amdgpu, viser `PSP is resuming`/`sos fw ok` → `ring gfx_0.0.0` → `Initialized amdgpu`. Retirer le `dev_info` de debug de `gfxhub_v2_0.c`. Rendre permanent (DKMS ou remplacement du `.ko` à chaque MAJ noyau).
4. Reverse PRIME AMD→AMD (rendu iGPU → sortie carte Polaris).
5. Config console (Bazzite ou équivalent).

## Fichiers de référence (conservés)

| Fichier | sha256 / emplacement | Rôle |
|---|---|---|
| `dump1.bin` | `c766a860…afc3` | BIOS d'origine — **voie de retour**, sur le cloud |
| `4700S_dump_igpu_D_cbsuma512.bin` | `6985a3ef…f5a9` | Image en puce (iGPU + 512 Mo VRAM) |
| `4700S_dump_igpu_Bbis.bin` | `089072ad…6aec` | Image de repli (iGPU sans VRAM) |
| `ip_discovery.bin` | `9fa33a91…1360`, installé dans `/lib/firmware/amdgpu/` (copie `~/Bios/`) | Table IP Discovery (BC-250) |
| `vbios_cyan_skillfish_bc250.rom` | `89ec00c3…87d1`, installé en `/lib/firmware/amdgpu/vbios.bin` | VBIOS Cyan Skillfish (BC-250) |
| `flashrom-static-x86_64` | — | flashrom statique compilé (programmer internal) |
| `~/linux-6.12.107/` | sources Debian patchées (voir tableau des fichiers modifiés) | Arbre de build amdgpu |
| `amdgpu.ko` patché | `/lib/modules/6.12.107+deb13-amd64/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko` (non compressé) | Module en service |
| `amdgpu.ko.xz` d'origine | `/root/amdgpu-orig/` | Retour au module Debian |
| `~/build-amdgpu.log` | — | Dernier log de build |

## Points de prudence

- Ne jamais flasher sans le dump d'origine accessible hors machine (fait : double copie cloud).
- Un flash raté = carte qui ne POST plus → CH341A obligatoire pour réécrire. Le risque est faible tant qu'on ne touche que PCD/APCB (flashrom vérifie), **il devient sérieux si on transplante des entrées PSP** (rejet de signature ou anti-rollback = pas de POST).
- La sortie vidéo passe obligatoirement par une carte dans le slot : la 4700S n'a aucun connecteur d'affichage natif.
- Reverse PRIME vers NVIDIA = fragile ; vers une carte AMD/Intel = fiable. D'où le choix de la Polaris.
- Écritures MMIO depuis `/dev/mem` : se limiter aux trois registres C2PMSG et aux messages SMU identifiés. Pas de fuzzing des IDs réservés.
- Build amdgpu : jamais `-j$(nproc)` sur cette machine (OOM), désactiver la mise en veille.
- Après une modification qui peut planter le probe, garder le `blacklist amdgpu` et charger à la main.

## Note

Aucune trace publique (GitHub, forums, communauté BC-250 indexée) d'une réactivation de l'iGPU sur une 4700S. Démarche a priori inédite. Le point d'achoppement actuel — un PMFW sans gestionnaires GFX — est aussi la première indication qu'AMD a bridé la 4700S à trois niveaux indépendants : straps NBIF (x86, levé), UMA (ABL/APCB, levé), et alimentation de l'îlot GPU (PMFW/ABL, en cours).

## Reprise du 04/10/2026 : toutes les révisions officielles 4700S examinées

Carte revenue sous **C0A officiel** (PMFW 70.18.0), boot OK, GPU de nouveau masqué en `1022:145a`. Lecture de la puce sauvegardée : `work/bios/now_20261004.bin` (sha `15730a30…`).

**Révisions BIOS AMD récupérées** (`drivers.amd.com/drivers/c0X.zip`, rangées dans `work/bios/amd/`) :

| BIOS | SMU_FW | ABL0 | Taille utile SMU_FW |
|---|---|---|---|
| C06 | 70.16.0 | 33.5.38 | 0x36440 |
| C07 / C08 | 70.17.0 | 33.5.38 | 0x36440 |
| C09 | 70.17.0 | 34.2.9 | 0x36440 |
| C0A | 70.18.0 | 34.4.6 | 0x36700 |
| BC-250 (réf.) | 88.6 / 88.7.1 | — | 0x3ae00 |

Toutes signées par la même clé SMU `b6f9ac22…` (chaîne CRD). Aucune n'a la taille d'un build avec GFX.

**Table des messages hôte → SMU, lue statiquement** (`work/smutable.py`, heuristique reprise de bc250-collective/amd_smu_reverse_engineering). La table de la file 0 est à la même adresse (`0x7070`) dans les deux familles :

| Message | 4700S 70.16 / 70.18 | BC-250 88.x |
|---|---|---|
| Core/DF/SoC (0x0B, 0x0C, 0x11, 0x13) | présents | présents |
| GFX (0x0E, 0x0F, 0x18, 0x19, 0x1A, 0x1E, 0x2F, 0x37-0x3C) | **absents (pointeur nul)** | présents |
| GetEnabledSmuFeatures 0x3D | absent | présent |

La lecture statique colle exactement aux réponses `0xFE` mesurées le 18/09 : la méthode est validée. **Les gestionnaires GFX ne sont pas bloqués par un drapeau, ils ne sont pas compilés dans le PMFW 4700S.** Il n'existe donc rien à « réveiller » depuis l'hôte dans ce firmware.

**Conclusion.** Piste 1 de la reprise (« un PMFW famille 70 avec GFX ») : fermée pour toutes les révisions publiques C06 à C0A. Le seul firmware qui sait gérer l'îlot GPU est le PMFW 88.x, signé pour la chaîne RBN que ce silicium refuse. Par voie logicielle et avec des firmwares signés acceptés par la puce, l'iGPU de la 4700S n'est pas activable en l'état des connaissances.

Pistes encore ouvertes, toutes hors de portée immédiate :
- un PMFW famille 70 non public (échantillon d'ingénierie, autre produit Ariel) qui contiendrait le GFX ;
- une évolution de la communauté BC-250/4700S sur ce sujet précis (surveiller : bc250-collective, rapport non confirmé de mrfrakes).

## Firmwares PS5 et séquence d'allumage GFX du PMFW 88.6 (04/10/2026, analyse statique)

**PS5 (« Oberon », PUP, `oberon_sec_ldr_c0.bin`) : écarté.** La chaîne de clés Sony est encore plus éloignée de CRD que RBN, donc rien n'est transplantable. Le chargeur sécurisé PS5 appartient à l'architecture de sécurité Sony, pas à l'arborescence PSP d'un BIOS PC. Les PUP sont chiffrés, et les binaires qui circulent viennent de consoles piratées ou de fuites (contournement de mesures techniques, sources douteuses). Le PMFW 88.x de la BC-250 sert de référence à la place : même die, firmware lisible, BIOS publics.

**Méthode.** Outils dans `work/pmfw/` : radare2 6.0.8 (Xtensa), SMU_FW extraits sans l'en-tête de 0x100 octets, base 0.
- `redis.py` désassemble fonction par fonction (ENTRY alignés sur 4) : le balayage linéaire se désynchronise sur les octets d'alignement.
- `access.py` relève les accès MMIO (base l32r + offset), `queues.py` lit toutes les tables de messages, `funcs.py` apparie les fonctions par signature, `trace.py` produit la trace ordonnée d'une fonction et de ses appelées.
- Images : BC-250 2.00 (PMFW 88.6.0) et puce actuelle C0A (70.18.0).

**Files de messages.** Le PMFW a plusieurs files, toutes lancées par TestMessage. Huit boîtes aux lettres C2PMSG apparaissent dans les deux firmwares, liste identique à `0x7008` : adresses locales `0x0301xxxx` = SMN `0x03B1xxxx`.

| File | BC-250 88.6 | 4700S 70.18 | Remarque |
|---|---|---|---|
| pilote (amdgpu, SMN 0x3B10A08) | `0x7070`, 36 gestionnaires | `0x7070`, 34 | GFX absent côté 4700S (déjà vu) |
| 4 gestionnaires (0x08, 0x10) | `0x7260` | **absente** | écrit dans le bloc `0x0113A0xx` ; peut-être l'interface RLC↔SMU |
| BIOS x86 (SMN 0x3B10528) | `0x72e8` | `0x72b0` | **0x18 DcBtc GFX et 0x2B SetGfxTCtlMax : BC-250 seulement**, ce qui recoupe `AmdNbioSmuV10Dxe` : identification confirmée |
| grande file (ID jusqu'à 0xA8) | `0x7468` | `0x7438` | **0x1A, 0x1B, 0x1C : BC-250 seulement**, plus environ 35 autres ID GFX |

Expéditeur de la grande file : non identifié (hypothèse : boîte aux lettres SMN 0x3B10A20/0x3B10A80/0x3B10A88).

**Allumage GFX = message 0x1B de la grande file** → `0x2a618` → `0x29e44`. **0x1A** (`0x29d04`) est l'extinction : sauvegarde des registres, coupure. Déroulé de `0x29e44` (trace complète : `work/pmfw/trace_powerup_gfx.txt`) :
1. État GFX lu en `[0x12f14+2]` : sort si déjà à 2 (allumé), sinon passe à 1 (transition).
2. Séquence partagée avec la 4700S (registres touchés aussi par le PMFW 70.18) :
   - RMW de `0x02210000`, puis de `0x0115A320`, `0x0115A334`, `0x0115A330`, attente de 10 unités, RMW de `0x0115A32C` ;
   - `0x01D80814` |= 2 ;
   - programmation de la table `0x0115F800-0x0115F974`.
3. **Partie propre au GFX (le PMFW 70.x n'écrit jamais ces registres)** :
   - `0x0100B00C` ← 0x7576_7570 (temporisation) ;
   - `0x0100B034` bit 0 = 1, **attente du bit 1** : poignée de main requête/accusé, très probablement l'interrupteur d'alimentation de l'îlot ;
   - `0x0100B004` ← 1, `0x0100B008` ← 1, `0x0100B2E0` ← 0xF ;
   - `0x0115A338` bit 0 = 1.
4. `0x2a004` restaure environ 95 registres (`0x01109C04-0x0110ABE8`, `0x01130800`, `0x01133000-0x01133128`) que `0x2a34c` avait sauvegardés à l'extinction. C'est le contexte de l'îlot, à réécrire après chaque mise sous tension.
5. État = 2.

Le bloc `0x0100B000` est vivant sur la 4700S : le PMFW 70.18 y écrit `B01C`, `B020`, `B034` (autre usage) et `B018` via des fonctions identiques à celles de la BC-250. Rien n'indique que le bloc d'alimentation GFX soit retiré du silicium. Seul le code qui le pilote manque.

**Traduction en SMN : hypothèse H1, non vérifiée.** H1 dit que les adresses locales `0x01xxxxxx` du SMU sont des adresses SMN telles quelles. Arguments :
- le PMFW lit `0x0115A870` ;
- le projet Keshas-dev/AMD-BC-250-Windows-Driver lit depuis l'hôte **SMN** `0x0115A870` et obtient le masque de cœurs (0xFF).

En revanche, la plage `0x03xxxxxx` n'est **pas** une identité (`0x0301xxxx` ↔ SMN `0x03B1xxxx`). Le microcode règle dynamiquement une fenêtre en `0x03220038` (pas de 1 Mo, adresse SMN >> 20, même schéma que les « slots » SMN du PSP). Les autres fenêtres sont probablement fixées avant le démarrage du SMU.

**Prochaine étape (matériel, non faite) : lecture seule depuis l'hôte**, via l'index/data SMN du pont racine. Ordre :
1. Valider H1 sur `0x0115A870` (attendu : le masque des 8 cœurs).
2. Lire `0x0100B000-0x0100B040`, `0x0100B2E0`, `0x0115A338`, `0x01108008`, et comparer aux valeurs attendues « GFX éteint ».

**Prudence** : Keshas-dev signale des lectures SMN qui figent le SMU (`0x3D64` RLC_PG, bloc `0x03B1xxxx` via la file 3). Une lecture peut donc exiger une coupure secteur, mais ne touche pas la flash. Aucune écriture tant que les lectures ne sont pas comprises. Si l'hôte peut écrire `0x0100B034`, on pourrait rejouer l'étape 3 à la main. La restauration de contexte (étape 4) exigerait les valeurs par défaut de ces ~95 registres, que le firmware tire de sa propre RAM.

### Lectures SMN depuis l'hôte (04/10/2026, lecture seule, C0A)

Outil : `scripts/smnread.py` (copie sur la machine dans `~/smn/`). Il passe par la paire index/data du pont racine (config PCI 00:00.0, 0x60/0x64) et n'écrit que dans le registre d'index. Il refuse le bloc MP1 `0x03Bxxxxx` et `0x3D64`, exige que k10temp soit déchargé, et synchronise le journal avant chaque lecture. Journal brut : `work/pmfw/smn_20261004.log`. 54 lectures, aucun gel, machine intacte.

| SMN | Valeur | Lecture |
|---|---|---|
| `0x00059800` (THM_TCON_CUR_TMP) | `0x673B0FEF` | 54 °C : le mécanisme fonctionne |
| `0x0115A870` / `0x0005A870` | `0xFF` / `0xFF` | masque des 8 cœurs, deux alias |
| `0x0005A320` = `0x0115A320` | `0x2` | identiques |
| `0x0115A32C / 330 / 334 / 338` | `0x8 / 0xE / 0xF / 0x0` | **exactement l'inverse de ce qu'écrit l'allumage BC-250** (`&~2`, `\|=0x17 &~8`, `\|=1 &~0xE`, `\|=0x30`, bit 0) : état « GFX éteint », registres accessibles |
| `0x01159800` | `0xE` | ≠ THM : **H1 fausse en général** |
| `0x01117000`, `0x0115F800`, `0x01133000` | `0xE` | valeur de remplissage, pas des registres |
| `0x0100B000-0x0100B040`, `0x0100B2E0`, `0x0100B780`, `0x01004008`, `0x01018218` | `0xFFFFFFFF` | toute la plage SMN `0x0100xxxx` est vide |

**Correction de la traduction : H2 remplace H1.** H2 : la fenêtre locale `0x011xxxxx` du SMU = SMN `0x000xxxxx`.
- THM : local `0x01159800` = SMN `0x00059800`.
- SMUIO : local `0x0115Axxx` = SMN `0x0005Axxx`.
- Le `0x0115A870` de Keshas-dev ne marchait que parce que SMN `0x0115Axxx` est un alias de `0x0005Axxx`.

`0x0005A320` = `mmSMUIO_GFX_MISC_CNTL` dans `smuio_12_0_0` (Renoir), dont amdgpu tire l'état GFXOFF (bits 2:1). Mais c'est `mmSMUIO_PWRMGT` dans `smuio_11_0_0` : le nom reste à confirmer pour Ariel. La plage `0x0005A32C-0x0005A338` contient donc les commandes d'alimentation GFX côté SMUIO, et elles sont lisibles depuis l'hôte.

**Hors de portée pour l'instant :**
- **Fenêtre locale `0x010xxxxx`**, celle de la poignée de main `0x0100B034` : base SMN inconnue. Ce n'est ni une identité, ni une base 0 évidente. Le PMFW 4700S écrit l'offset `0x230` dans 13 blocs `0x0100_0000-0x0103_1000` de pas 0x1000 : une piste pour l'identifier.
- **Status `0x00008008` et ~95 registres de contexte `0x00009C04-0x0000ABE8`** (H2) : **non lus volontairement**. Ils sont dans la même zone SMN basse que `0x3D64` (RLC_PG), qui fige le SMU selon Keshas-dev. Probablement des registres GC/RLC, illisibles tant que l'îlot est éteint.
- **`0x00033000`, `0x0003A084`** : `0xFFFFFFFF`. (La lecture `0x0113A084 = 0x41` d'avant correction ne veut rien dire.)

**Suite possible.**
1. Identifier la base SMN de la fenêtre `0x010` : désassembler la routine du PMFW qui écrit les 13 blocs, ou trouver la configuration des fenêtres (« slots ») du MP1 côté PSP.
2. Puis lire `0x0100B034` à sa vraie adresse.

Toute **écriture** dans `0x0005A32C-338` ou dans l'interrupteur `0x0100B034` reste exclue tant que la séquence n'est pas reproduite à l'identique, conditions comprises. Une demande d'alimentation sans le reste (horloges, contexte, état PMFW) peut geler le SoC, voire stresser le rail GFX.

### Fenêtre locale 0x010 : pages par IP, page 0x0B = GFX (04/10/2026, statique)

Routine désassemblée : 4700S `0x2d0fc`, BC-250 `0x31434`. Elle fait partie d'une série activer(1)/désactiver(0) avec `0x2ce08`, `0x2ce2c`, `0x2cfbc`, `0x2d448` et `0x2d944`, typique de l'activation du clock gating. Outil : `work/pmfw/blocks.py`.
- Elle écrit **45 pages de 4 Ko**, entre `0x01000000` et `0x010AB000` (et non 13 : le comptage d'avant venait d'un découpage de fonction erroné).
- Chaque page reçoit, à l'offset `0x230`, **0 ou 0x7FF** (11 bits) selon un bit d'un mot de configuration, avec un bit par IP.
- La fenêtre `0x010xxxxx` est donc un espace de **pages de contrôle par IP**, à disposition uniforme : le numéro de page désigne l'IP.

**Page 0x0B = GFX.** La liste BC-250 contient `0x0100B230` (bit 17 du second mot). La liste 4700S est identique à deux pages près, et **c'est précisément `0x0100B` qui manque**. Cela recoupe la séquence d'allumage : `B004`, `B008`, `B00C`, `B034` et `B2E0` sont dans cette même page.

**Sur la 4700S, la page 0x0B sert encore**, via `0x29b88` → `0x29a90` / `0x29ae4` (équivalents BC-250 : `0x2ddd0` / `0x2de24`) :
- `0x29a90` est un port indirect : index `0xFFF00009` / `0xFFF0000A` dans `B01C`, donnée (6 bits puis 1 bit, tirés du même argument) dans `B020`, déclenchement par **le bit 2 de `B034`** ;
- `0x29ae4` écrit 12 bits dans `B018`.
Ces valeurs ressemblent à des diviseurs d'horloge (DID). Le bloc de la page 0x0B existe et répond au SMU sur ce silicium.

**Révision de l'interprétation de `B034`.** Sur la 4700S, le bit 2 de `B034` déclenche le port indirect ; sur la BC-250, la séquence d'allumage utilise les bits 0 (requête) et 1 (accusé). `B034` est donc le registre de commande de la page GFX. Ses bits 0/1 peuvent être l'interrupteur d'alimentation, mais aussi le démarrage d'une horloge (DFLL/PLL) : **« interrupteur d'alimentation » n'est plus qu'une hypothèse**.

**Traduction SMN : toujours inconnue, et l'accès depuis l'hôte est probablement impossible.** Rien de la fenêtre n'apparaît en SMN `0x0100xxxx` (tout à `0xFFFFFFFF`). La disposition « une page de 4 Ko par IP » ressemble à un espace privé du MP1, de type RSMU, plus qu'à une plage du SMN global. Je n'ai fait aucune lecture SMN « à l'aveugle » pour chercher ces pages : des lectures non ciblées peuvent figer le SMU. La voie « rejouer la séquence depuis l'hôte » est **bloquée en l'état**, faute d'adresse pour la page 0x0B. Les commandes SMUIO (`0x0005A32C-338`) sont lisibles, mais elles ne suffisent pas sans la page GFX ni la restauration de contexte.

### Table des fenêtres SMN du MP1 trouvée ; la lecture de 0x09xxxxxx fige la machine (04/10/2026)

**Source : le PMFW lui-même**, pas le PSP. Côté PSP :
- les pilotes (entrée 0x28) mappent le SMN par appel système (`svc 0x7d`, adresse + taille) ;
- les ABL (zlib, en clair) ne contiennent aucune adresse MP1 ;
- le bootloader BC-250 est chiffré, celui de la 4700S est en ROM.

La fonction `0x1b25c` du PMFW (même adresse dans 88.6 et 70.18) écrit des paires de bases 16 bits (SMN >> 20) dans `0x03220000 + 4k`. La fenêtre locale n vaut `0x01000000 + n` Mo. Décodage : `work/pmfw/slots.py`, résultats `slots_bc250.txt` / `slots_4700s.txt`, **identiques dans les deux firmwares** :

| Fenêtre locale | SMN | | Fenêtre locale | SMN |
|---|---|---|---|---|
| `0x010` | **`0x090`** | | `0x01E` | `0x001` |
| `0x011` | `0x000` (confirme H2) | | `0x01F` | `0x101` |
| `0x012` | `0x038` | | `0x020-0x021` | `0x16C-0x16D` |
| `0x014-0x01B` | `0x200-0x207` | | `0x022` | `0x014` |
| `0x01D` | `0x02F` | | `0x023` | `0x13B` |
| `0x013`, `0x01C`, `0x026-0x029` | `0x000` | | `0x024-0x025` | `0x16E-0x16F` |

(Bases en Mo, adresses à multiplier par 0x100000.)

Les pages de contrôle par IP sont donc en **SMN `0x09000000 + page × 0x1000`**. La page GFX est en **`0x0900B000`**, l'interrupteur supposé en `0x0900B034`, et les commandes SMUIO en `0x0005A32C-338`.

**Incident.** Première lecture de vérification : SMN `0x0900E230`, la page clock gating d'une IP active, que le PMFW 4700S écrit au démarrage. **La machine s'est figée** : plus de ping, ni de SSH. La plage `0x09xxxxxx` est probablement réservée au MP1 ou à l'accès sécurisé, et une lecture depuis l'hôte bloque le bus. **Plage ajoutée à la liste noire de `smnread.py`.** Remise en route : coupure secteur. Vérifié après redémarrage (12:45) : dernière ligne de `~/smn/smn.log` = `12:39:50 AVANT 0x0900e230`, sans résultat. Le journal système du boot précédent s'arrête net à 12:39:50, sur l'appel sudo, sans oops ni message noyau : gel matériel du bus. BIOS toujours C0A (04/26/2022), script à jour sur la machine (refuse `0x0900E230`), lecture THM de contrôle OK.

**Conséquence.** On connaît maintenant l'adresse de la page GFX, mais l'hôte ne peut pas l'atteindre par l'index/data SMN du pont racine. Le pilotage de l'îlot GPU depuis Linux reste fermé par cette voie. Seuls le SMU, et peut-être le PSP, y ont accès, et ils n'exécutent que du firmware signé.

### Levier trouvé : le SMU 4700S lit et écrit le SMN pour l'hôte (file 3, messages 0x2A / 0x2B / 0x2C) (04/10/2026, statique)

Fonctions génériques du PMFW, à des adresses identiques dans 70.18 et 88.6 :
- `0x29f8` = lecture SMN (hi, lo, largeur) ;
- `0x2a74` = écriture SMN.
Toutes deux passent par la fenêtre dynamique 28 (`0x03220038`). Appelants côté gestionnaires de messages, **dans la grande file** (`@0x7438` sur 4700S, `@0x7468` sur BC-250, appelée « Q3 » par la communauté BC-250) :

| Msg | 4700S 70.18 | BC-250 88.6 | Rôle |
|---|---|---|---|
| 0x2A | `0x26dd4` | `0x27cf8` | lit SMN[arg] et renvoie la valeur dans arg |
| 0x2B | `0x26df8` | — (identique) | mémorise arg (valeur à écrire) en `[0x8ad8+4]` |
| 0x2C | `0x26e10` | `0x27d34` | écrit la valeur mémorisée à SMN[arg] |
| 0x98 | `0x27134` | `0x280e0` | écrit 0xFF à SMN[arg] (utilisé pour débloquer les cœurs de la BC-250) |

**Aucun filtrage d'adresse** dans ces gestionnaires. Boîte aux lettres de la file 3 : commande SMN `0x03B10A20`, réponse `0x03B10A80`, argument `0x03B10A88`, accès hôte par config PCI 00:00.0 `0xB8/0xBC`.
- Source : rw-r-r-0644/bc250-core-unlock, qui l'utilise en production sur BC-250.
- Recoupements : l'hypothèse tirée de la table `0x7008` ; Keshas-dev (« Q3 0x2A secure SMN read », « Q3 0x98 core unlock »).

**Portée.** Le SMU accède avec ses propres privilèges à des plages que l'hôte ne peut pas lire, dont la page GFX en SMN `0x0900B000`, que la lecture directe depuis l'hôte a figée. **La séquence d'allumage BC-250 est donc, en principe, rejouable depuis l'hôte par 0x2B/0x2C**, sans firmware modifié ni signature. Ce serait la première voie qui contourne la chaîne de clés.

**Précautions :**
- ne jamais lire le bloc MP1 `0x03B1xxxx` par 0x2A : cela fige le SMU, coupure secteur obligatoire (Keshas-dev) ;
- lecture seule d'abord (`scripts/smuq3read.py`, qui n'envoie que 0x2A) ;
- aucune écriture tant que l'état complet n'est pas relevé et que la séquence n'est pas reproduite avec ses conditions (horloges, contexte de ~95 registres, état PMFW). La valeur à écrire passe par 0x2B, puis 0x2C l'écrit : une adresse fausse écrit n'importe où dans le SoC.

**Zen 2 « classiques » (Renoir, Lucienne, Van Gogh) :**
- PSP/SMU signés par d'autres chaînes : rien n'est flashable ;
- pour la séquence elle-même, la BC-250 (même die) fait mieux.
Seul usage possible : Van Gogh (Steam Deck, Zen 2 + RDNA2, BIOS publics Valve), pour recouper les noms et le sens des registres SMUIO/GFX.

### Test file 3 depuis l'hôte : lecture SMN 0x2A REFUSÉE par une porte de sécurité (04/10/2026, matériel)

`scripts/smuq3read.py`, lecture de contrôle SMN `0x0005A870` (masque de cœurs, valeur connue 0xFF par l'accès direct) :
```
0x0005a870 = 0x0005a870  (statut 0xfd)
```
Le SMU répond (pas de gel), mais **statut 0xFD, pas 0x01** : l'argument n'est pas modifié (il reste l'adresse envoyée). Le gestionnaire n'a pas été exécuté.

**Cause, par désassemblage du répartiteur (`0xebc`, confirmé dans 70.18 et 88.6).** Chaque message a un octet de garde (offset 5 de son entrée de 8 octets dans la table de file) ; le répartiteur fait `ball gate, garde` et renvoie **0xFD** (`movi a11, 253`) si les bits de la garde ne sont pas tous présents dans un registre de porte en SRAM.

~~| Messages | Octet de garde | Bits requis dans la porte |~~
~~|---|---|---|~~
~~| 0x02, 0x22, 0x50, **0x98** | 0x06 | bits 1,2 = marche normale (posés au boot, PSP vivant) |~~
~~| **0x27-0x2F**, dont **0x2A (lecture SMN)** et **0x2C (écriture SMN)** | 0x01 | **bit 0 = déverrouillage sécurisé** |~~

**⚠ Le tableau ci-dessus (04/10) était faux : l'octet de garde avait été lu au mauvais offset (0 au lieu de 5).** La correction (05/10) suit.

### ⚠ Correction : octet de garde au bon offset, msg 0x98 accessible (05/10/2026, statique)

L'analyse initiale du 04/10 lisait l'octet de garde à l'**offset 0** de chaque entrée de 8 octets. Le répartiteur à `0xebc` lit en réalité à l'**offset 5** (`l8ui a12, a11, 5`). Les valeurs de garde étaient toutes fausses. Correction, confirmée sur les deux firmwares (70.18 et 88.6) :

| Garde (offset 5) | Nb | Messages (extraits) | Signification |
|---|---|---|---|
| **0x00** | 95 | 0x01 TestMessage, 0x02 GetSmuVersion, 0x22, 0x23, 0x49, 0x50, **0x96, 0x98, 0x99**, … | **aucun bit requis** → `ball` passe toujours (vrai vide) → **toujours dispatché** |
| **0x02** | 13 | **0x27-0x2F** (dont 0x2A lecture SMN, 0x2C écriture SMN), 0x71, 0x72, 0xA7, 0xA8 | bit 1 requis dans la porte → **conditionnel** |

La distribution est **identique** entre les deux firmwares. Aucun message n'a garde 0x01 ni 0x06 — ces valeurs étaient des artefacts du mauvais offset.

**Mécanisme de la porte pour garde=0x02.** Le répartiteur :
1. lit la porte (`gate`) en SRAM à `[0x7860 + 0x240]` = `[0x7AA0]` ;
2. efface le bit 1 de gate ;
3. vérifie un registre MMIO à l'adresse locale `0x03210064` : si sa valeur vaut `0x80000000`, le bit 1 est restauré dans gate ;
4. `ball gate, guard` : si tous les bits de guard sont dans gate → dispatch ; sinon → 0xFD.

Sur la 4700S, le registre `0x03210064` ne vaut pas `0x80000000` → le bit 1 n'est jamais restauré → les 13 messages à garde 0x02 sont **fermés** (statut 0xFD). Le message 0x2A en fait partie : cela explique le résultat observé.

**Conséquence pour msg 0x98.** Garde = **0x00** → **aucun bit requis** → le répartiteur le dispatche sans condition. Le gestionnaire est appelé, il écrit 0xFF à SMN[ARG] sans validation d'adresse. **Msg 0x98 est opérationnel sur la 4700S.**

**Aucune écriture tentée.** La porte étant par-message et non par-adresse, inutile de réessayer 0x2A sur d'autres adresses : toutes seraient refusées de la même façon. Machine intacte.

### Analyse statique : la « vulnérabilité ring-corruption » (bc250-smu-unlock) existe dans PMFW 70.x (05/10/2026)

**Question posée.** Le dépôt `bc250-smu-unlock` (GabriWar) exploite des messages Q3 du PMFW BC-250 pour contourner la porte de sécurité. Ces messages et ces gestionnaires existent-ils dans le PMFW 4700S, et sont-ils exploitables ?

**Méthode.** Comparaison instruction par instruction des firmwares `bc250_200.bin` (PMFW 88.6.0) et `4700s_c0a.bin` (PMFW 70.18.0), avec les outils de `work/pmfw/` et désassemblage r2 (Xtensa). Registres de la grande file : CMD SMN `0x03B10A20`, RSP `0x03B10A80`, ARG `0x03B10A88`.

**Répartiteur (dispatcher) Q3 à `0x0ebc`.** Fonction commune aux deux firmwares, dans la zone basse non couverte par la passe de désassemblage initiale (début à `0x1014`). Désassemblée à la main pour cette analyse. Elle :
1. lit CMD → extrait msg_id ;
2. vérifie `msg_id < max` (169 pour la grande file), sinon 0xFE ;
3. calcule `entry = queue_start + msg_id × 8` ;
4. charge `handler = entry[0:3]` (mot 0) et `guard = entry[5]` (octet 5, 7 bits bas) ;
5. si handler == 0 → 0xFE ;
6. vérifie `ball gate, guard` → si échec → 0xFD ;
7. si bit 7 de guard : appel synchrone (`callx8 handler`) ; sinon enfile par `0x26b4` pour traitement différé.

Queue start (répartiteur) : **0x7434** (4700S), **0x7464** (BC-250) — décalé de 4 octets par rapport à la valeur de `queues.py` (0x7438 / 0x7468) car `queues.py` cherche la première occurrence de TestMessage à l'offset +4, pas le début réel de la table.

Les boîtes aux lettres 3 et 4 partagent la même grande file (même queue_start et max_msg = 169 dans les deux firmwares).

**Msg 0x98 — primitive d'écriture SMN `0xFF`, IDENTIQUE entre firmwares.**

| | 4700S 70.18 | BC-250 88.6 |
|---|---|---|
| Guard (offset 5) | **0x00** | **0x00** |
| Handler | `0x27134` | `0x280e0` |
| Code | **identique** | **identique** |

Le gestionnaire (13 instructions) :
1. `call8 0xffc` → lit ARG = adresse SMN cible ;
2. si ARG == 0 : retourne succès sans rien écrire ;
3. si ARG ≠ 0 : `call8 0x2a74` (écriture SMN) avec **window=0, addr=ARG, value=0xFF, mode=2** ;
4. relit la valeur (vérification), écrit le résultat dans ARG, retourne succès.

**Aucune validation d'adresse.** La valeur 0xFF est codée en dur (`movi a12, 255`). C'est la même fonction que bc250-core-unlock utilise pour écrire `0xFF` à SMN `0x0115A870` (masque de cœurs CPU). Le PMFW 70.x contient le même code, au même guard=0x00.

**Msg 0x23 — ring buffer, accessible (guard=0x00).**

| | 4700S 70.18 | BC-250 88.6 |
|---|---|---|
| Guard (offset 5) | **0x00** | **0x00** |
| Handler (grande file) | `0x1c35c` | `0x1c2f0` |
| bounds_limit | `0x001FFFFF` | `0x001FFFFF` |
| SMN offsets | `0x16E00000`, `0x16C00000` | idem |

Les gestionnaires sont structurellement identiques (mêmes instructions, différences limitées aux constantes d'adresse dues au layout binaire). Msg 0x23 écrit dans un ring buffer dont les entrées contiennent adresse SMN + données — la base de l'exploitation « ring-corruption ».

**Hash table (`0x8470` / `0x84a0`) : sans rapport.** Ni msg 0x98 ni msg 0x2A ne figurent dans la hash table. Celle-ci sert au dispatch interne par interruption (timers, événements), pas aux messages hôte→SMU. Tous les messages Q3 passent par le répartiteur `0xebc` et la table de file.

**Structure `guard_struct` (`0x12c08` sur 4700S).** Le handler de msg 0x30 (guard=0x00, accessible) lit les offsets 92-94 de cette structure et renvoie l'état de sécurité. Le handler de msg 0x49 (guard=0x00, accessible) écrit à l'offset 108. Ces offsets sont **distincts** de la porte du répartiteur (`0x7AA0`) et du drapeau spécial (`0x7b0c`). `guard_struct` sert au reporting interne, pas au contrôle de dispatch Q3.

Le code à `0x294ce` (boot PMFW, partie allumage GFX, BC-250 seulement) écrit `guard_struct[92] = 1`, `[93] = 0`, `[94] = 0` — confirmant que l'offset 92 marque le passage en mode « sécurisé » après l'allumage GFX. Cette branche n'est jamais exécutée sur le PMFW 4700S (pas de code GFX).

**Conclusion : la vulnérabilité existe et est exploitable sur la 4700S.**

1. **Msg 0x98 est accessible** (guard=0x00, identique à TestMessage) et exécute une écriture SMN[ARG] = 0xFF sans aucune validation.
2. **Msg 0x23 est accessible** (guard=0x00) et offre un mécanisme de ring buffer potentiellement exploitable pour des écritures de valeurs arbitraires.
3. Le code des gestionnaires est **fonctionnellement identique** entre les deux firmwares.
4. La porte de sécurité (guard=0x02) ne bloque que les 13 messages 0x27-0x2F, 0x71, 0x72, 0xA7, 0xA8 — **pas msg 0x98 ni msg 0x23**.

**Analyse détaillée msg 0x23 (05/10/2026).** Le handler grande file (4700S `0x1bb34`, BC-250 `0x1bafc`) n'est **pas** un simple ring buffer direct. C'est un répartiteur à sous-commandes qui dispatch via une table de structures en SRAM.

Fonctionnement :
1. Lit ARG, extrait `sub_cmd = ARG & 0xF` ;
2. Accepte sub_cmd=0 ou sub_cmd=2 uniquement (autres → 0xFF) ;
3. Charge un pointeur de structure (`0xCA10` sur 4700S, `0xCA38` sur BC-250) ;
4. Calcule l'entrée : `entry = sub_cmd * 36 + base - 16` (stride 36 octets) ;
5. Vérifie un bitmap à `entry+84` : si `bit[mbox_index]` est mis, dispatch ; sinon 0xFF ;
6. Appel indirect via le pointeur de fonction à `entry+68`.

Table de routage msg 0x23 (4700S) :

| mbox | sub_cmd | fn_ptr (SRAM) | bitmap | Résultat |
|------|---------|---------------|--------|----------|
| 3 (Q3) | 2 | 0xCA8C = **NULL** | 0xCA9C = **0x00** | MORT |
| 3 (Q3) | 0 | — | — | MORT (bnei a2,2 → 0xFF) |
| 2 | 0 | 0xCA44 = **0x1BBF4** | 0xCA54 = **0x04** | VIVANT (bit 2 = mbox 2) |

La seule route vivante est **mbox 2, sub_cmd 0**, qui appelle la fonction consommateur `0x1BBF4`. Cette fonction est un **chargeur de table de puissance GPU** :
- Verrouille un sémaphore (arg=8) ;
- Copie 1180 octets depuis la structure vers un buffer à `0x7FC0` ;
- Appelle `0x1BC94` (validation stricte : fréquences 80-160, tensions 8-48, checksum non nul) ;
- Copie les données validées vers le buffer actif `0x7B24` ;
- Applique via `0x214DC`.

Registres de la boîte mbox 2 (trouvés dans la table à SRAM 0x7000, stride 12) :
- CMD = `0x03B10528`, RSP = `0x03B10564`, ARG = `0x03B10998`
- Accessibles depuis l'hôte par config PCI 0xB8/0xBC.

**Conclusion msg 0x23 :** l'exploitation par corruption de la table de dispatch (écrire un bitmap ou fn_ptr non nul pour sub_cmd=2 via Q3) est **fermée** — la SRAM n'est pas accessible par SMN (test du 05/10). La route vivante mbox 2 / sub_cmd 0 reste le chemin viable, si le buffer peut être rempli autrement qu'en écrivant en SRAM par SMN.

---

**MP1_SRAM = SMN `0x03C00004` (05/10/2026).** Trouvé dans le driver Linux amdgpu (`smu_v11_0.h` ligne 44, `smu9_smumgr.c` ligne 35). Constante universelle SMU v11.0 — le driver l'utilise comme `addr_start` pour le chargement firmware.

**Mapping : SRAM[X] → SMN `0x03C00004 + X`.**

La plage `0x03C0xxxx` est **hors de toutes les deny lists** (smnread.py bloque `[0x03B00000, 0x03C00000)`, la SRAM commence au-dessus). Msg 0x98 n'a aucune restriction d'adresse.

**~~La SRAM n'est pas accessible par SMN~~** — **RE-CORRIGÉ (05/10/2026 test) : la SRAM N'EST PAS accessible par SMN, même depuis le SMU.** Test msg 0x98 → SMN `0x03C122C0` (SRAM `0x122BC`, valeur NOP `0x000000FF`) : le SMU gèle (Q3 RSP reste à 0, coupure secteur nécessaire). L'aperture SRAM est verrouillée par le PSP après le chargement firmware, pour TOUS les demandeurs SMN y compris le SMU lui-même. Écrire vers `0x03C0xxxx` via SMN provoque un bus hang identique au gel `0x09xxxxxx`. **La piste corruption SRAM via msg 0x98 est FERMÉE.**

Cibles clés SRAM → SMN :

| Cible | SRAM | SMN | Valeur FW |
|---|---|---|---|
| Fn ptr sub0 msg 0x23 | 0xCA44 | 0x03C0CA48 | 0x0001BBF4 |
| Fn ptr sub2 msg 0x23 (NULL) | 0xCA8C | 0x03C0CA90 | 0x00000000 |
| Bitmap sub0 | 0xCA54 | 0x03C0CA58 | 0x00000004 |
| Bitmap sub2 (morte) | 0xCA9C | 0x03C0CAA0 | 0x00000000 |
| Dispatch gate | 0x7AA0 | 0x03C07AA4 | 0x00000000 |
| Ring buffer | 0x7FC0 | 0x03C07FC4 | 0x00000000 |

Vérification (lecture seule, sans risque) : `sudo smnread.py log 0x03C00004` → attendu `0x00461200` (= fw[0:4]).

**Limites pour l'activation de l'iGPU.**
- Msg 0x98 ne peut écrire que **0xFF** (valeur codée en dur). Ce n'est pas suffisant pour la séquence d'allumage GFX qui exige des valeurs précises dans les registres SMUIO et la page GFX.
- ~~La SRAM du PMFW n'est pas accessible par SMN~~ → **CONFIRMÉ par test (05/10/2026)** : écriture vers `0x03C0xxxx` gèle le SMU (bus hang). Aperture verrouillée par le PSP pour tous les demandeurs.
- Le registre de sécurité à `0x03210064` (qui contrôle la porte pour guard=0x02) est dans l'espace interne du MP1 ; son accessibilité par SMN est inconnue (mais le risque de gel est réel si la zone est protégée comme la SRAM).

**Pistes ouvertes (mises à jour 05/10/2026 — post-test SRAM).**
1. ~~Msg 0x98 pour débloquer msgs 0x2A-0x2F via 0x03210064~~ — **FERMÉE** (comparaison exige `0x80000000`).
2. ~~Msg 0x98 → corruption SRAM~~ — **FERMÉE** (aperture verrouillée, gel SMU).
3. ~~Msg 0x98 → corruption fn_ptr SRAM~~ — **FERMÉE** (même raison).
4. **Mbox 2 directe** (la route msg 0x23/sub0 vivante) : les registres mbox 2 (CMD `0x03B10528`, RSP `0x03B10564`, ARG `0x03B10998`) sont accessibles par config PCI 0xB8/0xBC. La fonction consommateur `0x1BBF4` charge une power table GPU depuis un buffer SRAM (`0x7FC0`). **Problème :** le buffer doit être rempli au préalable, et l'écriture SRAM par SMN est impossible. Il faut trouver un message (parmi les 95 guard=0x00) qui copie des données de ARG vers la SRAM — ou un mécanisme DMA.
5. **Msg 0x98 pour écrire 0xFF dans les registres SMUIO** (`0x0005A32C-338`, via SMN) — ces registres ne sont PAS en SRAM, pas de risque de gel aperture. Pourrait modifier l'état d'alimentation GPU, mais 0xFF n'est probablement pas la bonne valeur.
6. ~~Ring buffer msg 0x23 Q3 (handler `0x1c35c`)~~ — **CORRIGÉ (05/10/2026)** : `0x1c35c` est le handler de **msg 0x24** (stub de 5 instructions), pas msg 0x23. Le vrai ring buffer est msg 0x23 sur **File 1 / mbox 2** (handler `0x292b0`). Voir section dédiée ci-dessous.
7. **Chercher un message « écriture mémoire locale »** dans les 95 handlers guard=0x00 : un handler qui fait `s32i` (store) vers une adresse passée en ARG, écrivant directement en SRAM sans passer par SMN.
8. **Surveiller bc250-smu-unlock** (GabriWar) pour l'évolution de l'exploit ring-corruption.

Sources consultées :
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) (msg 0x98 en production)
- [bc250-smu-unlock-bios5](https://github.com/GabriWar/bc250-smu-unlock-bios5) (ring-corruption)
- [bc250-notes](https://github.com/lorek123/bc250-notes) (documentation Q3)
- [amd-bc250-bios-unlock](https://github.com/kalpakprod/amd-bc250-bios-unlock) (unlock BIOS)
- [8 Core CPU Unlock](https://elektricm.github.io/amd-bc250-docs/system/8core-unlock/) (documentation msg 0x98)

---

## Analyse complète du ring buffer et mapping mbox→queue (05/10/2026, session 2)

### Correction msg 0x23 vs 0x24

Le handler `0x1c35c` (grande file, File 2) est **msg 0x24** (pas msg 0x23). C'est un stub de 5 instructions qui écrit 1 dans ARG et retourne succès — sans effet.

Le vrai handler ring buffer est sur **File 1** (pas File 2) :

| | 4700S (File 1) | BC-250 (File 2) |
|---|---|---|
| msg_id (hôte) | **0x23** | **0x23** |
| handler | `0x292b0` | `0x2d2e0` |
| guard | **0x00** | **0x00** |
| queue (mbox) | **mbox 2** | mbox 2 equiv |

### Table mbox → queue (SRAM 0x7A5C, stride 4, 6 entrées)

```
Mbox 0 → File 0 (base 0x7070, 34 msgs) — registres standard driver
Mbox 1 → 0x7228 (queue VIDE, 0 msgs)
Mbox 2 → File 1 (base 0x72B0, 42 msgs) — RING BUFFER + SRAM reader
Mbox 3 → File 2 (base 0x7438, 108 msgs) — grande file (Q3)
Mbox 4 → File 2 (mêmes registres que mbox 3)
Mbox 5 → File 3 (base 0x7980, 16 msgs)
```

### Registres mbox 2

| Registre | Adresse locale | Adresse SMN | PCI config |
|---|---|---|---|
| ARG | 0x03010998 | **0x03B10998** | 0xB8/0xBC |
| RSP | 0x03010564 | **0x03B10564** | 0xB8/0xBC |
| CMD | 0x03010528 | **0x03B10528** | 0xB8/0xBC |

ARG multi-registre : ARG[n] = SMN `0x03B10998 + n*4` (vérifié par la fonction arg_read à `0xF78`).

Accès hôte identique à Q3 : PCI 0xB8/0xBC (MP1_SMN_EXT_ACCESS). **Lire RSP mbox 2 depuis l'hôte ne passe PAS par le SMU** (accès SMN direct), donc pas de risque de gel récursif.

### File 1 / mbox 2 : 38 messages, TOUS guard=0x00

Aucun message de File 1 n'est bloqué par le guard. Messages clés :

| msg_id | handler | description |
|---|---|---|
| 0x0A | `0x24a1c` | **Lecteur SRAM** (Keshas « Q2 0x0A »). Détecte mbox_index==2 → lit 24 octets d'ARG. Appelle `0x31d48` pour traiter. |
| 0x23 | `0x292b0` | **Ring buffer** (producteur). Lit 4 ARG, valide bornes, écrit entrées 16 octets. |

### Ring buffer : producteur (0x292B0) et consommateur (0x29170)

**Producteur** (handler msg 0x23 File 1) :

```
ARG[0] = offset adresse (≤ 0x1FFFFF)
ARG[1] = masque (mask)
ARG[2] = donnée (data)
ARG[3] = type (bits 24-31) | sub_index (bits 20-23) | slot (bits 0-3, doit être 1-4)
```

Routage par `command_type` (ARG[3] >> 24) :
- `command_type == 1` → chemin principal
- `sub_index` (bits 20-23 de ARG[3]) sélectionne la base SMN :
  - sub_index=0 → `0x16C00000` (CLK0, probable GFXCLK)
  - sub_index=1 → `0x16E00000` (CLK1, probable SOCCLK)

Entrée ring (16 octets) :
```
entry[0]  = ARG[0] + SMN_base    (adresse complète)
entry[4]  = ARG[2]               (donnée)
entry[8]  = ARG[1]               (masque)
entry[12] = command_type          (= 1)
```

Structure ring : base `0x18500`, stride `0x794` par slot, 4 anneaux de 30 entrées (16 octets/entrée), compteur à `slot + 0x780 + ring_id*4`.

**Consommateur** (0x29170) — READ-MODIFY-WRITE sur MMIO local :

```
sub_index=0 : adresse locale = 0x02000000 + ARG[0]
sub_index=1 : adresse locale = 0x02400000 + ARG[0]
```

Opération : `new = (current & ~mask) | (data & mask)` — écriture masquée dans les registres CLK du SoC.

Littéraux du consommateur :
```
sub=0 : counter=0x18A80, offset=0xEB3FFE00, entries=0x18320
sub=1 : counter=0x19214, offset=0xEB5FFE00, entries=0x188BC
```

**Les adresses cibles sont des registres MMIO locaux Xtensa (CLK/PLL), PAS des écritures SMN.** Le consommateur n'utilise pas la fenêtre SMN — il écrit directement dans l'espace d'adresses local du processeur Xtensa. Aucun risque de gel SMN.

### Gate de sécurité (SRAM 0x7B3C)

| Firmware | Valeur initiale |
|---|---|
| 4700S C0A | **0x00000000** |
| BC-250 88.6 | **0x00000000** |

Keshas confirme (README `keshas_README.md`) : « The SMU secure-access gate is already open at boot — SMU[0x7B3C] == 0 ». La chaîne `bc250-smu-unlock` ring-corruption n'a pas été nécessaire sur le BC-250 de Keshas.

### Informations du README de Keshas

- Q2 (= mbox 2) accessible via BAR5/NBIO sur le BC-250
- Q2 msg 0x0A lit la SRAM (msg 0x0A en convention 1-based = handler `0x24a1c` sur 4700S)
- **Ne jamais lire `0x03B1xxxx` via Q3 msg 0x2A** — gel SMU, identique à notre observation
- Le whitelist de `smu-unlock-staged` admet Q2 0x05/0x06, Q2 0x0A, Q3 0x22, Q3 0x2A — PAS les écritures SMN 0x2B/0x2C
- `RequestActiveWgp` (Q0 0x18) est un vestige Van Gogh — accepté (0x01 OK) mais sans effet

### Pistes mises à jour (post-analyse ring buffer)

1. **PRIORITAIRE : mbox 2 msg 0x0A** — lire SRAM pour vérifier l'état runtime du gate `0x7B3C` et d'autres structures. Test en lecture seule, risque nul.
2. **PRIORITAIRE : mbox 2 msg 0x23** — ring buffer vers registres CLK (`0x16C00000` / `0x16E00000`). Écriture masquée dans les PLLs du SoC. Potentiellement la clé pour configurer le GFXCLK.
3. **Msg 0x23 grande file / sub_cmd 0** (mbox 2, handler `0x1BBF4`) — chargeur power table GPU. Le buffer à `0x7FC0` doit être rempli avant appel. Chercher un moyen de remplir ce buffer (msg 0x0A inverse ? DMA ? autre msg File 1 ?).
4. **Identifier les registres CLK** — déterminer lesquels contrôlent GFXCLK vs SOCCLK. Comparer avec les écritures CLK que fait le PMFW BC-250 pendant l'allumage GFX.
5. **Msg 0x98 pour registres non-SRAM** — toujours possible pour SMUIO (`0x0005Axxxx`) et autres registres SMN accessibles.

### Tests live du 05/10/2026 (session 2, après power cycle)

Mbox 2 vivante (RSP=0x01). Q3 aussi récupérée.

**Résultats msg 0x0A (mbox 2, File 1) :**

| ARG envoyé | Statut | Résultat | Note |
|---|---|---|---|
| 0x00000000 | 0x01 | 0x00000005 | Valeur fixe |
| 0x00007B3C | 0x01 | 0x00000005 | Même résultat, ARG ignoré |

msg 0x0A n'est **PAS** un lecteur SRAM paramétré : il retourne toujours 0x05, quelle que soit l'entrée. Probablement un indicateur de version ou de statut interne.

**Résultats ring buffer (msg 0x23, mbox 2) :**

| Test | Statut | Registre avant | Registre après | Résultat |
|---|---|---|---|---|
| NO-OP mask=0, sub=0 | 0x01 | — | — | Accepté |
| Write 0xCAFE0001, offset=0x100, mask=0xFFFF, sub=0 (CLK0) | 0x01 | 0x00000000 | 0x00000000 | **Inchangé** |
| Write 0xBEEF0002, offset=0x100, mask=0xFFFF, sub=1 (CLK1) | 0x01 | 0x00000000 | 0x00000000 | **Inchangé** |
| Write bit 6, offset=0x1C, mask=0x40, sub=0 (CLK0 actif) | 0x01 | 0x0000003F | 0x0000003F | **Inchangé** |

**Conclusion : le consommateur du ring buffer est inactif.** Les entrées sont correctement stockées par le producteur (handler 0x292B0, statut 0x01), mais le consommateur (0x29170) ne les traite pas. Le ring buffer est un mécanisme de **tuning CLK runtime** : il ne tourne que quand le sous-système GFX/CLK est actif. Avec GFX éteint, la boucle de gestion des horloges n'est pas lancée.

**Registres CLK lus :**

| SMN | Valeur | Bloc |
|---|---|---|
| `0x16C00000` | `0x01100020` | CLK0 (GFXCLK ?) |
| `0x16C00004` | `0x03000840` | |
| `0x16C00008` | `0x140000F1` | |
| `0x16C0000C` | `0x0200000A` | |
| `0x16C00010` | `0x0260FFE5` | |
| `0x16C00014` | `0x00000580` | |
| `0x16C00018` | `0x00000460` | |
| `0x16C0001C` | `0x0000003F` | |
| `0x16C00100-0x16C0020C` | `0x00000000` | Zone haute = zéros |
| `0x16E00000` | `0x01100020` | CLK1 (SOCCLK ?) |
| `0x16E00004` | `0x04000840` | |
| `0x16E00008` | `0x140000F1` | |
| `0x16E0000C` | `0x0200000A` | |

### Analyse de msg 0x98 (grande file, handler 0x27134)

msg 0x98 (guard=0x00, accessible) écrit la valeur **fixe 0x000000FF** dans le registre SMN spécifié par ARG[0]. Utilise l'accès SMN fenêtré du PMFW (0x02Cxxxxx → fenêtre 0x03220038). Puis relit la valeur écrite.

`call8 0x2a74(a10=0, a11=ARG, a12=0xFF, a13=2)` → dword write

Mécanisme de la fonction d'écriture SMN (0x2a74) :
- Registre de fenêtre : local `0x03220038` ← ARG >> 20 (sélection page 1 Mo)
- Masque adresse : `0x000FFFFF` (offset dans la page)
- Adresse locale d'écriture : `(ARG & 0xFFFFF) + 0x02C00000`
- Taille selon a5 : 0=byte, 1=half, **2=dword** (cas de msg 0x98)

**msg 0x98 n'est PAS un writer paramétrable.** La valeur écrite est toujours 0xFF.

### Msgs 0x2B/0x2C (SMN write paramétré) : bloqués

guard=0x02 (bit 1 conditionnel). Le registre de sécurité SMN `0x03210064` renvoie `0xFFFFFFFF` depuis l'hôte (domaine verrouillé par le PSP). La condition de gate n'est pas remplie sur la 4700S. **Aucun moyen connu de changer ce registre.**

### Écriture SMN depuis l'hôte : confirmée

Test neutre : écriture de la valeur courante (0x00) dans SMN `0x0005A338` via PCI config 0x60/0x64. Relecture identique. **La voie d'écriture SMN host fonctionne pour les registres SMUIO.**

### Bilan : chemins d'écriture disponibles

| Cible | Depuis l'hôte (0x60/0x64) | msg 0x98 (0xFF fixe) | msg 0x23 ring buf | msgs 0x2B/0x2C |
|---|---|---|---|---|
| SMUIO `0x0005A32C-338` | **OUI** ✓ | Oui mais 0xFF seulement | Non | Bloqué |
| Page 0x0B `0x0900Bxxx` | **Non** (fige) | Risque gel SMN | Non | Bloqué |
| CLK `0x16C/16Exxxxx` | **OUI** ✓ | Oui mais 0xFF | Consumer inactif | Bloqué |
| SRAM `0x03C0xxxx` | Non (verrouillé) | Non (fige SMU) | Non | Bloqué |

### Pistes mises à jour (post-tests live)

1. ~~msg 0x0A pour lire SRAM~~ → retourne toujours 0x05, fermé.
2. ~~Ring buffer pour CLK~~ → consumer inactif (GFX éteint), fermé pour l'instant.
3. **PRIORITAIRE : écriture SMUIO depuis l'hôte** — les 4 registres `0x0005A320/32C/330/334/338` sont les premières étapes de la séquence d'allumage BC-250. L'hôte peut les écrire directement. Cibles (d'après la trace BC-250) :
   - `0x0005A320` : 0x02 → 0x00 (`&~2`)
   - `0x0005A334` : 0x0F → 0x17 (`&~8 | 0x17`)
   - `0x0005A330` : 0x0E → 0x01 (`|1 &~0xE`)
   - `0x0005A32C` : 0x08 → 0x38 (`|0x30`)
   - `0x0005A338` : 0x00 → 0x01 (`bit 0`)
   **Aucune écriture sans accord explicite.** Risque : incohérence entre SMUIO (on) et page 0x0B (off) si la phase 3 n'est pas faite.
4. ~~msg 0x98 sur SMN 0x0900B034~~ → **FERMÉ (05/10/2026)** : testé msg 0x98 sur 0x0900B100 (zone vide page 0x0B). **Résultat : GEL SMU** (timeout, mbox 2 et Q3 mortes, machine OK mais SMU figé → power cycle). Le chemin SMN vers `0x09xxxxxx` est fermé pour TOUS les initiateurs, y compris le SMU via son fenêtrage (0x02Cxxxxx → slot 0x03220038). Seule la fenêtre Xtensa locale (0x010xxxxx = bus interne, pas SMN) fonctionne. Deny list smnread.py déjà à jour. **Le SMU ne peut PAS écrire à SMN 0x09xxxxxx par msg 0x98.**
5. **ALTERNATIVE : écriture CLK depuis l'hôte** — les registres CLK (`0x16C/0x16E`) sont accessibles en lecture. Si l'écriture fonctionne aussi, on pourrait configurer les horloges GFX directement, sans passer par le ring buffer.
6. **Identifier base SMN de la fenêtre 0x010** — la table à SRAM 0x1B25C n'est pas lisible. Chercher dans le PSP ou dans le code BIOS.
