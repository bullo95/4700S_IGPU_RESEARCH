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

### Écriture SMN depuis l'hôte : SMUIO protégé

Test neutre (05/10/2026 session 2) : écriture de la valeur courante (0x00) dans SMN `0x0005A338` → relecture identique. **Faux positif** : la valeur écrite était déjà celle en place. Test réel (05/10/2026 session 3, `scripts/tests/smuio_phase1.py`) : 4 écritures RMW avec valeurs différentes → **toutes ignorées**, readback = valeurs originales. Les registres SMUIO `0x5A320-338` sont protégés en écriture côté hôte (le fabric SMN filtre par initiateur). L'écriture SMN hôte fonctionne mécaniquement (pas de bus hang) mais ces registres spécifiques refusent les écritures hôte.

### Bilan : chemins d'écriture disponibles

| Cible | Depuis l'hôte (0x60/0x64) | msg 0x98 (0xFF fixe) | msg 0x23 ring buf | msgs 0x2B/0x2C | msg 12 I2C | msg 20 DPM |
|---|---|---|---|---|---|---|
| SMUIO `0x5A320-338` (power) | **NON** ✗ (protégé) | **OUI probable** (à tester) | Non | Bloqué | Non | Non |
| SMUIO `0x5A818-870` (GPIO) | Lecture OUI | **OUI** ✓ (0x5A868 confirmé) | Non | Bloqué | Non | Non |
| Page 0x0B `0x0900Bxxx` | **Non** (fige) | Non (fige SMU) | Non | Bloqué | Non | Non |
| CLK `0x16C/16Exxxxx` | Lecture OUI, écriture ? | Oui mais 0xFF | Consumer inactif | Bloqué | Non | OUI (fixe) |
| SRAM `0x03C0xxxx` | Non (verrouillé) | Non (fige SMU) | Non | Bloqué | Non | Non |
| I2C contrôleur MP1 | Non (bus local) | Non | Non | Non | Via PMFW | Non |

### Pistes mises à jour (post-tests live)

1. ~~msg 0x0A pour lire SRAM~~ → retourne toujours 0x05, fermé.
2. ~~Ring buffer pour CLK~~ → consumer inactif (GFX éteint), fermé pour l'instant.
3. ~~Écriture SMUIO depuis l'hôte~~ → **FERMÉ (05/10/2026)** : testé les 4 écritures Phase 1 (0x5A320 `&~2`, 0x5A334 `|0x30`, 0x5A330 `|1 &~0xE`, 0x5A32C `|0x17 &~8`) via PCI config 0x60/0x64. **Résultat : toutes ignorées silencieusement.** Readback = valeurs originales inchangées. Les registres SMUIO `0x5A320-338` sont **protégés en écriture côté hôte** (le fabric SMN filtre par initiateur). Le BC-250 utilise la fenêtre Xtensa 0x011xxxxx (bus interne direct, pas le fabric SMN). Script : `scripts/tests/smuio_phase1.py`.
4. ~~msg 0x98 sur SMN 0x0900B034~~ → **FERMÉ (05/10/2026)** : testé msg 0x98 sur 0x0900B100 (zone vide page 0x0B). **Résultat : GEL SMU** (timeout, mbox 2 et Q3 mortes, machine OK mais SMU figé → power cycle). Le chemin SMN vers `0x09xxxxxx` est fermé pour TOUS les initiateurs, y compris le SMU via son fenêtrage (0x02Cxxxxx → slot 0x03220038). Seule la fenêtre Xtensa locale (0x010xxxxx = bus interne, pas SMN) fonctionne. Deny list smnread.py déjà à jour. **Le SMU ne peut PAS écrire à SMN 0x09xxxxxx par msg 0x98.**
5. **Écriture CLK depuis l'hôte** — les registres CLK (`0x16C/0x16E`) sont accessibles en lecture. Écriture probablement protégée aussi (même mécanisme SMN), à vérifier.
6. **Identifier base SMN de la fenêtre 0x010** — la table à SRAM 0x1B25C n'est pas lisible. Chercher dans le PSP ou dans le code BIOS.
7. ~~Cartographier les 42 handlers mbox 2~~ → **FAIT (05/10/2026 session 3)**. Résultat : **aucun handler ne permet d'écrire à une adresse SMN arbitraire**. L'adresse cible vient toujours d'une constante (literal pool) ou d'un champ SRAM interne, jamais de ARG[0]. La seule callsite de la fonction d'écriture SMN (0x2a74c) est dans le sous-système fan/thermique (timers périodiques + msg 39). Handlers notables :
   - **msg 12 (0x24734)** : programmation I2C/SMBus (sub-cmd 3/4/5). Écrit à un contrôleur I2C via MMIO. Pourrait piloter un VRM GFX via I2C (SVI2/SVI3).
   - **msg 20/21** : enable/disable GFX DPM (registres fixes, bases SRAM 0x17408/0x17410).
   - **msg 22/32** : init horloge GFX/SOC (dizaines d'écritures CLK fixes). Risque de hang si GFX éteint.
   - **msg 39** : set fréquence GFX, appelle SMN write — valeur=ARG, adresse=structure fan (non modifiable).
8. ~~Explorer msg 12 / I2C VRM~~ → **FERMÉ (05/10/2026 session 4)**. Voir analyse détaillée ci-dessous.
9. **CORRECTION** : le PMFW 4700S a **13 références au SMUIO** (via literal pool 0x17108 = Xtensa 0x0115A600 → SMN 0x5A600). L'affirmation antérieure « aucune référence SMUIO » était fausse (recherche directe 0x0115A dans le code ne trouve rien, il faut suivre les indirections literal pool). Mais ces 13 refs accèdent aux registres GPIO/status (0x5A818-0x5A870), **PAS aux registres power 0x5A320-338**. Voir section dédiée.
10. ~~Test msg 0x98 sur SMUIO~~ → **CONFIRMÉ (05/10/2026 session 4)**. Le chemin SMU windowed (msg 0x98 via 0x02Cxxxxx → slot 0x03220038) **a accès en écriture aux registres SMUIO**. Test : 0x5A868 passé de 0x01 à 0xFF (écriture confirmée), 0x5A874 resté à 0x00 (registre RAZ/non-implémenté). **Le fabric SMN laisse passer l'initiateur MP1 (SMU) vers SMUIO, contrairement à l'hôte.** Script : `scripts/tests/msg98_smuio_test.py`. Power cycle effectué après le test (0x5A868 modifié, registre utilisé par le PMFW en RMW).
11. **PRIORITAIRE : exploiter le chemin SMU windowed vers SMUIO power (0x5A320-338)**. msg 0x98 écrit toujours 0xFF → inadapté pour les écritures Phase 1 (qui nécessitent des RMW précis). Deux sous-pistes :
    - **11a** : tester msg 0x98 sur 0x5A334 (actuellement 0x0F, Phase 1 veut 0x3F, 0xFF inclut les bits voulus mais en set plus). Risque : bits parasites dans un registre power.
    - **11b** : chercher dans la grande file un message capable d'écrire une **valeur paramétrable** via le même chemin SMU windowed. Réexaminer les 95+ handlers guard=0x00 de la grande file.

### Test msg 0x98 sur SMUIO (session 4, 05/10/2026)

**But** : vérifier si le chemin d'écriture SMN du SMU (fenêtrage interne 0x02Cxxxxx) passe le filtre du fabric SMN vers les registres SMUIO, alors que l'hôte est bloqué.

**Protocole** : msg 0x98 (grande file mbox 3, guard=0x00) écrit 0xFF à SMN[ARG]. Lecture hôte avant/après via PCI 0x60/0x64.

**Résultats** :

| Registre | Rôle | Avant | Après msg 0x98 | Verdict |
|---|---|---|---|---|
| `0x5A874` | Hors-PMFW (non-référencé) | `0x00000000` | `0x00000000` | RAZ ou non-implémenté |
| `0x5A868` | RMW par PMFW | `0x00000001` | **`0x000000FF`** | **ÉCRITURE CONFIRMÉE** |

**Conclusion** : le fabric SMN **autorise l'initiateur MP1** (SMU) à écrire dans le bloc SMUIO, y compris les registres du bloc smuio_pwr (0x5A800+). L'hôte est filtré, mais le SMU passe. Ceci ouvre potentiellement l'accès aux registres power Phase 1 (0x5A320-338) via le même mécanisme. **Le problème restant : msg 0x98 écrit toujours 0xFF, pas une valeur paramétrable.**

#### Valeurs SMUIO GPIO lues depuis l'hôte (pour référence)

| SMN | Valeur | Description |
|---|---|---|
| `0x5A800` | `0x00000002` | |
| `0x5A818` | `0x0000FFFE` | GPIO data (R/W par PMFW) |
| `0x5A81C` | `0x00000013` | Readback (R par PMFW) |
| `0x5A820` | `0x49140890` | |
| `0x5A824` | `0x80000000` | |
| `0x5A828` | `0x48140880` | |
| `0x5A82C` | `0x80000000` | |
| `0x5A830` | `0x47140870` | |
| `0x5A834` | `0x80000000` | |
| `0x5A838` | `0x46540864` | |
| `0x5A83C` | `0x80000000` | |
| `0x5A840` | `0x45940858` | |
| `0x5A844` | `0x80000000` | |
| `0x5A848` | `0x44940A5A` | |
| `0x5A84C` | `0x80000000` | |
| `0x5A850` | `0x43940E62` | |
| `0x5A854` | `0x80000000` | |
| `0x5A858` | `0x42141658` | |
| `0x5A85C` | `0x80000000` | |
| `0x5A864` | `0x0000283F` | Config (W par PMFW) |
| `0x5A868` | `0x00000001` | RMW par PMFW |
| `0x5A86C` | `0x00840F70` | Status/ctrl (R/W par PMFW) |
| `0x5A870` | `0x000000FF` | Status 8-bit (R par PMFW) |
| `0x5A880` | `0x003C2082` | |

### Analyse I2C — msg 12, 27, 28 (session 4, 05/10/2026)

#### Architecture I2C du PMFW

Le PMFW utilise un contrôleur I2C **interne au MP1**, distinct des blocs SMUIO I2C :

| Composant | Adresse Xtensa | SMN estimé | Accès hôte |
|---|---|---|---|
| Contrôleur I2C MP1 (transfert) | `0x0327FE00` | `~0x0327FE00` | Non (bus local) |
| Contrôleur I2C MP1 (scanner) | `0x01C1D600` | `~0x01C1D600` | Non (bus local) |
| SMUIO I2C0 (CKSVII2C) | — | `0x0005A100` | `0xFFFFFFFF` (dark) |
| SMUIO I2C1 (CKSVII2C1) | — | `0x0005A200` | `0xFFFFFFFF` (dark) |

Registres du contrôleur I2C MP1 (offsets depuis base 0x0327FE00) :

| Offset | Rôle |
|---|---|
| +0x200 | IC_CON / mode (cmd) |
| +0x204 | IC_TAR / adresse cible (slave) |
| +0x208 | Trigger / status (bit 30 = done) |
| +0x20C | Config (masque+mode) |
| +0x210 | Longueur data |
| +0x218 | Data lecture (si cmd bit 0-2 = 0) |
| +0x21C | Data écriture (si cmd bit 0-2 ≠ 0) |

#### Struct I2C — SRAM 0x15300

Pointée par le literal pool 0x17958 (valeur = 0x00015300). Seulement 5 références dans tout le PMFW, toutes dans les handlers I2C.

| Offset | Valeur initiale (SRAM) | Écrit par | Lu par |
|---|---|---|---|
| +0 | 0x00000000 | msg 27 (flags) | msg 27, msg 28 |
| +4 | 0x0000FFFD | msg 27 (slave addr) | sub-cmd 3/4/5 |
| +8 | 0xFC000404 | msg 28 (commande) | sub-cmd 3/4/5 |
| +12 | 0x00002C00 | **personne** | sub-cmd 3 |
| +16 | 0x00003000 | **personne** | sub-cmd 4 |
| +20 | 0x00003400 | **personne** | sub-cmd 5 |

**Les champs data (+12/+16/+20) ne sont écrits par aucun handler ni aucune fonction d'init. Ils gardent leurs valeurs binaires initiales.**

#### msg 27 — set slave addr (handler 0x24790)

- `get_arg(ctx)` → ARG
- Si ARG == 0 : struct[4] = 0, flags |= 1, retour 1 (succès)
- Si ARG ≠ 0 : flags = 0, retour 255 (erreur)
- **Limitation : ne peut mettre que slave addr = 0 (appel général I2C)**

#### msg 28 — set command byte (handler 0x247C0)

- `get_arg(ctx)` → ARG
- Si ARG ≥ 0 (signé, i.e. bit 31 clair) : erreur
- Puis si ARG > 0xBFFFFFFD (non-signé) : erreur
- Sinon (0x80000000 ≤ ARG ≤ 0xBFFFFFFD) : struct[8] = ARG, flags |= 2, succès
- **Plage restreinte et inhabituelle pour un « command byte » I2C**

#### msg 12 — I2C transaction (handler 0x24734)

- `get_arg(ctx)` → ARG, extrait les 16 bits bas
- Sub-commande 3/4/5 valides, sinon erreur 255
- Pas de vérification du flag struct[0] — exécute directement

Sub-cmd 3 (0x2465c) : appelle `i2c_channel_init()` (0x1ea98), scanne 8 canaux, puis `i2c_transaction(slave=struct[4], cmd=struct[8], data=struct[12] | scan_result)`

Sub-cmd 4 (0x24704) : `i2c_transaction(slave=struct[4], cmd=struct[8], data=struct[16] | 1)`

Sub-cmd 5 (0x2471c) : `i2c_transaction(slave=struct[4], cmd=struct[8], data=struct[20] | 1)`

#### Fonctions utilitaires identifiées

| Adresse | Rôle | Signature |
|---|---|---|
| `0x00000FA8` | `set_response(ctx, status)` | a10=ctx, a11=status |
| `0x00000FE4` | `set_resp_data(ctx, value)` | a10=ctx, a11=value |
| `0x00000FFC` | `get_arg(ctx)` → ARG | a10=ctx → retour a10 |
| `0x000248F0` | `i2c_transaction(slave, cmd, data)` | a10=slave, a11=cmd, a12=data |
| `0x0001EA98` | `i2c_channel_init()` | (pas d'args significatifs) |

#### Conclusion I2C

Le chemin I2C msg 12 est **inutilisable pour piloter un VRM GFX** :
- On ne peut pas choisir l'adresse esclave (msg 27 n'accepte que 0)
- On ne peut pas choisir les data (figées dans la SRAM binaire)
- Le contrôleur I2C est sur le bus local MP1, inaccessible depuis l'hôte
- Les blocs SMUIO I2C (0x5A100/0x5A200) sont dark (0xFFFFFFFF)

### Correction SMUIO — le PMFW 4700S accède au SMUIO (session 4, 05/10/2026)

**CORRECTION** de l'analyse piste 7 : le literal pool 0x17108 contient **0x0115A600** (Xtensa H2 → SMN 0x0005A600 = SMUIO base + 0x600, soit le bloc smuio_pwr). 13 callsites dans le PMFW accèdent à 6 registres distincts :

| SMN | Offset depuis base 0x5A600 | Accès | Callsites |
|---|---|---|---|
| `0x5A818` | +0x218 | R/W | 4 sites (GPIO/data write) |
| `0x5A81C` | +0x21C | R | 2 sites (readback) |
| `0x5A864` | +0x264 | W | 1 site |
| `0x5A868` | +0x268 | RMW | 2 sites |
| `0x5A86C` | +0x26C | R/W | 4 sites |
| `0x5A870` | +0x270 | R | 2 sites (status 8 bits) |

Ces registres sont dans le bloc **smuio_pwr** (base 0x5A800), la même zone que SOC_GAP_PWROK (0x5ABE0) et GFX_GAP_PWROK (0x5ABE4). Ils servent probablement au contrôle GPIO et à la surveillance thermique/alimentation.

**Les registres power Phase 1 (0x5A320-0x5A338, bloc smuio base 0x5A000) ne sont référencés nulle part dans le PMFW 4700S.** La séquence d'allumage GFX n'existe pas.

### Analyse msg 20/21 — GFX DPM (session 4)

msg 20 (0x290D4) = enable GFX DPM, msg 21 (0x29104) = disable. Même structure :
- ARG bits 0-1 doivent être non-nuls
- Bit 0 → appelle 0x28F00 (DPM domaine 1)
- Bit 1 → appelle 0x28F4C (DPM domaine 2)

Fonction 0x28F4C (enable DPM domaine 2) :
- Base = pool 0x17410 = **0x0257FE00** (Xtensa CLK1 window → SMN ~0x16F7FE00)
- Lit status à [base+0x308] bits 8-9 ; si 3 = déjà activé, sort
- RMW [base+0x21C] : set bits 0,1
- Appelle subroutine 0x29040 (activation DPM proprement dite)
- Set [base+0x350] bit 0 sur succès

Fonction 0x28F00 : similaire, base = pool 0x17408 = **0x0217FE00** (CLK0 window)

**msg 20/21 contrôlent l'espace CLK (fréquences/tensions dynamiques), PAS l'alimentation SMUIO. Le DPM présuppose le GFX déjà sous tension.**

### Literal pool — constantes I2C (pour référence)

| Pool addr | Valeur | Rôle |
|---|---|---|
| `0x17958` | `0x00015300` | Pointeur struct I2C en SRAM |
| `0x1795C` | `0xBFFFFFFD` | Borne haute msg 28 (range check) |
| `0x17960` | `0x0327FE00` | Base contrôleur I2C (transfert) |
| `0x17964` | `0xFF000000` | Masque AND (clear bas 24 bits) |
| `0x17968` | `0x00010004` | Config I2C (mode 1, flags 4) |
| `0x1796C` | `0x20000200` | Trigger I2C sub-cmd 3 |
| `0x17970` | `0xDFFFFFFF` | Masque clear bit 29 |
| `0x17974` | `0x30000200` | Trigger I2C sub-cmd 4/5 |
| `0x17978` | `0x00010006` | Config I2C alternative |
| `0x17108` | `0x0115A600` | Base SMUIO (Xtensa H2 → SMN 0x5A600) |
| `0x17408` | `0x0217FE00` | Base CLK0 DPM (Xtensa CLK window) |
| `0x17410` | `0x0257FE00` | Base CLK1 DPM (Xtensa CLK window) |

### Dispatch function complète — 0xEBC (boot area, session 5, 05/10/2026)

La fonction de dispatch est dans la zone de boot (adresse 0xEBC, en dessous de 0x1014, hors du fichier .dis). Désassemblée via radare2 sur le binaire brut. Format des entrées de la table des handlers : `[func_addr(4), flags_word(4)]` — 8 octets par entrée.

```
0xEBC: entry a1, 32
0xEBF: mov.n a10, a2                    ; a10 = queue_num
0xEC1: call8 0xF90                       ; read CMD → returns msg_id
0xEC4: l32r a8, [0xB84] = 0x7980        ; per-queue metadata
0xEC7: l32r a13, [0xB88] = 0x7860       ; per-queue data
0xECA: addx2 a8, a2, a8                 ; a8 = queue*2 + 0x7980
0xECD: l16ui a8, a8, 252                ; a8 = handler_count
0xED0: addx4 a11, a2, a13              ; a11 = queue*4 + 0x7860
0xED3: l32i a11, a11, 0x1FC            ; a11 = handler_table_base
0xED6: bltu a10, a8, 0xEE3             ; bounds check (msg_id < count)
0xEDB-0xEDE: error RSP=0xFE (out of range)
0xEE3: addx8 a11, a10, a11             ; entry = msg_id*8 + table_base
0xEE6: l32i.n a9, a11, 0              ; a9 = func_addr
0xEE8: movi.n a15, -3                  ; a15 = ~2 = 0xFFFFFFFD
0xEEA: l8ui a12, a11, 5               ; a12 = guard_byte (byte 1 of flags_word)
0xEED: bnez.n a9, 0xEF9               ; if func → guard check
0xEEF-0xEF7: error RSP=0xFE (no handler)
```

#### Guard check (0xEF9-0xF2F)

```
0xEF9: l32r a14, [0xB8C] = 0x7AA8      ; global state base
0xEFC: l32i a10, a13, 0x240            ; a10 = state from [0x7AA0]
0xEFF: extui a12, a12, 0, 7            ; guard_mask (7 bits bas)
0xF02: l32i a14, a14, 100              ; security_flag = [0x7B0C]
0xF05: and a10, a10, a15              ; clear bit 1 of state
0xF08: s32i a10, a13, 0x240           ; store back
0xF0B: beqz.n a14, 0xF1C              ; if flag==0 → locked path (skip set)
0xF0D: l32r a8, [0xB94] = 0x320FE00   ; security register MMIO base
0xF10: l32r a9, [0xB90] = 0x80000000  ; expected value
0xF13: memw
0xF16: l32i a8, a8, 0x264             ; read [0x03210064]
0xF19: bne a8, a9, 0xF24              ; if ≠ 0x80000000 → skip locked
0xF1C: movi.n a9, 2                    ; LOCKED: set bit 1
0xF1E: or a10, a10, a9
0xF21: s32i a10, a13, 0x240
0xF24: ball a10, a12, 0xF31           ; ALL guard bits in state → dispatch
0xF27-0xF2F: RSP=0xFD (access denied)
0xF31: l8ui a10, a11, 5               ; reload guard byte
0xF34: l32i.n a12, a11, 0             ; func_addr
0xF36: bbci a10, 7, 0xF40             ; bit 7 → task mode
0xF39: mov.n a10, a2
0xF3B: callx8 a12                      ; CALL handler
0xF3E: retw.n
0xF40-0xF4D: enqueue as task
```

#### Logique du guard check

Le state variable `[0x7AA0]` (= `[0x7860+0x240]`) a son **bit 1 effacé** à chaque dispatch, puis **conditionnellement re-armé** :

1. Si `security_flag` (`[0x7B0C]`) == 0 → bit 1 NON ré-armé → handlers avec guard bit 1 = **bloqués**
2. Si `security_flag` != 0 → lit le registre matériel `[0x03210064]` :
   - Si == `0x80000000` → bit 1 ré-armé → handlers avec guard bit 1 = **autorisés**
   - Si != `0x80000000` → bit 1 NON ré-armé → handlers avec guard bit 1 = **bloqués**

Sur la 4700S : le registre `[0x03210064]` lit `0xFFFFFFFF` (domaine verrouillé par le PSP). `0xFFFFFFFF` ≠ `0x80000000` → bit 1 jamais ré-armé → **tous les handlers avec guard bit 1 sont bloqués** (RSP=0xFD).

#### Initialisation du security_flag (0x1B024-0x1B059)

```
0x1B044: l32r a8, [0x17024] = 0x0120FE00   ; security register MMIO base (init)
0x1B047: l32r a10, [0x1701C] = 0x00080000  ; mask = bit 19
0x1B04A: l32r a9, [0x17020] = 0x7AA8       ; global state base
0x1B04D: memw
0x1B050: l32i a8, a8, 0x3C0                ; read [0x012101C0]
0x1B053: and a8, a8, a10                    ; mask bit 19
0x1B056: extui a8, a8, 19, 13              ; shift → 0 or 1
0x1B059: s32i a8, a9, 100                  ; [0x7B0C] = security_flag
```

Le `security_flag` est 0 ou 1, dérivé du bit 19 du registre matériel à l'adresse Xtensa `0x012101C0`. Ces registres (`0x0121xxxx` et `0x0321xxxx`) sont **internes au processeur Xtensa du SMU** — ils n'ont pas d'équivalent SMN accessible depuis l'hôte.

### Tables de dispatch par file

| File | table_base | count | handlers guard=0x00 | handlers guard≠0x00 |
|---|---|---|---|---|
| Queue 0 | 0x706C | 55 | ~55 | ~0 |
| Queue 1 | 0x7224 | 17 | ~17 | ~0 |
| Queue 2 | 0x72AC | 49 | 49 (tous) | 0 |
| Queue 3 | 0x7434 | 169 | ~95 | ~74 |
| Queue 4 | 0x7434 | 169 | (=Q3) | (=Q3) |

### Queue 2 — handlers msg 0x2B-0x2D analysés et éliminés

Les entrées Q2 pour msg 0x2B-0x2D ont guard=0x00 (accessibles) mais ce ne sont **PAS** des primitives SMN write :

| Q2 msg | Handler | Fonction réelle |
|---|---|---|
| 0x2B | `0x2DD78` | Conversion flottante (DPM utility) |
| 0x2C | `0x2DD9C` | Conversion flottante (DPM utility) |
| 0x2D | `0x2DDC0` | Conversion flottante (DPM utility) |

Les vrais handlers SMN write (0x2B/0x2C) sont en **Queue 3** avec guard=0x02 (bit 1 conditionnel → bloqués).

### Scan exhaustif Q3 — aucun autre handler non-gardé n'atteint SMN_write

Analyse des ~95 handlers Q3 avec guard=0x00, en suivant les chaînes d'appels jusqu'à 2 niveaux d'indirection. **Seul msg 0x98 appelle la fonction SMN_write (0x2A74).** Et msg 0x98 écrit toujours la valeur **fixe 0xFF** (`movi.n a12, 0xFF` hardcodé dans le handler 0x27134).

### Bus hang 0x01210BC0 (05/10/2026)

Tentative de lecture SMN 0x01210BC0 depuis l'hôte (PCI 0x60/0x64) → **bus hang immédiat**, machine figée. Le journal smnread montre "AVANT 0x01210bc0" sans ligne de résultat.

**Note :** l'adresse visée était **fausse** (erreur de calcul). L'adresse correcte du registre d'init est `0x0120FE00 + 0x3C0 = 0x012101C0`. Mais toute la plage `0x0121xxxx` est dangereuse depuis l'hôte — ajoutée au deny list (`0x01210000-0x01220000`). La plage `0x0321xxxx` (registre dispatch) est également ajoutée par précaution (`0x03210000-0x03220000`).

### Piste 2 — FERMÉE (05/10/2026)

**Verdict : le guard check est verrouillé matériellement.** Le security_flag est initialisé depuis un registre interne SMU (`0x012101C0`) au boot du PMFW. Le registre de sécurité dispatch (`0x03210064`) est vérifié à chaque dispatch. Les deux registres sont **internes au processeur Xtensa** (adresses `0x012xxxxx` et `0x032xxxxx`), inaccessibles depuis l'hôte par quelque chemin que ce soit.

Impossible de :
- Modifier le security_flag `[0x7B0C]` (SRAM verrouillée par le PSP)
- Modifier le registre matériel `[0x03210064]` (bus interne Xtensa, pas de chemin SMN)
- Modifier le registre d'init `[0x012101C0]` (idem)
- Forcer le re-armement du bit 1 du state variable `[0x7AA0]` (SRAM verrouillée)

**Msgs 0x2B/0x2C (SMN write paramétré) restent inaccessibles sur la 4700S.**

### Piste 1 — msg 0x98 (0xFF fixe) vers SMUIO power : seul chemin viable

msg 0x98 est le **seul handler non-gardé** capable d'écrire via le fenêtrage SMN du SMU. Le fabric SMN autorise l'initiateur MP1 (confirmé par le test 0x5A868). Contrainte : la valeur est toujours 0xFF.

Registres SMUIO Phase 1 et compatibilité 0xFF :

| Registre | Valeur actuelle | Valeur cible Phase 1 | 0xFF compatible ? | Risque |
|---|---|---|---|---|
| `0x5A334` (PWRMGT) | `0x0000000F` | `0x0000003F` (set bits 4-5) | **Incertain** — 0xFF set bits 6-7 en plus, potentiellement réservés | Moyen |
| `0x5A868` (GPIO RMW) | `0x00000001` | — (test seulement) | **OUI** — test déjà confirmé | Aucun |

**Prochaine étape** : analyser les registres SMUIO 0x5A320-0x5A338 individuellement pour déterminer si 0xFF est une valeur acceptable pour chacun d'eux, en comparant avec la séquence d'allumage BC-250 et les spécifications connues du bloc SMUIO.

### Analyse PMFW C08 70.17 — BIOS C08 = FERMÉE (05/10/2026)

**Contexte** : la puce BC-250 est parfois reconnue comme « AMD 4700S C08 ». Un BIOS C08 existe (`4700S_c08_amd.bin`, 16 Mo). Hypothèse testée : le PMFW C08 (70.17.0) a peut-être un masque de sécurité différent (0x00000000 comme on le croyait de la BC-250) → flasher le BIOS C08 désactiverait la porte de sécurité.

**Extraction** : PMFW C08 extrait du BIOS par recherche du pattern de dispatch (signature à 0xEBC). Taille : 222 272 octets (0x36440), sauvé dans `work/pmfw/4700s_c08.bin`.

**Correction d'erreur majeure** : l'analyse précédente des pools BC-250 était **fausse**. Le masque BC-250 rapporté comme `0x00000000` résultait d'une lecture aux adresses de pools *C0A* dans le binaire *BC-250* — les `l32r` Xtensa pointent vers des adresses différentes dans chaque PMFW (les pools "glissent" d'un build à l'autre).

**Décodage corrigé des l32r** (formule correcte : `pool = (sign(imm16) << 2) + ((PC+3) & ~3)`) :

| PMFW | Masque (a10) | Reg base (a8) | State base (a9) | security_flag |
|---|---|---|---|---|
| **C0A 70.18** | `0x00080000` ← [0x1701C] | `0x0120FE00` ← [0x17024] | `0x7AA8` ← [0x17020] | `[0x7B0C]` |
| **C08 70.17** | `0x00080000` ← [0x1700C] | `0x0120FE00` ← [0x17014] | `0x7AA0` ← [0x17010] | `[0x7B04]` |
| **BC-250 88.6** | `0x00080000` ← [0x1704C] | `0x0120FE00` ← [0x17054] | `0x7AD8` ← [0x17050] | `[0x7B3C]` |

**Les trois PMFW ont un code de sécurité identique** : même masque `0x00080000`, même registre source `[0x012101C0]`, même extraction bit 19. Le code à l'offset `0x1B044-0x1B059` est rigoureusement le même (AND+EXTUI+S32I). Seules les adresses de pools littéraux changent d'un build à l'autre (les pools "glissent").

**Conclusion** : la sécurité PMFW est contrôlée par un **fusible matériel** (bit 19 de `[0x012101C0]`), pas par le firmware. Sur BC-250, le PSP ou un fusible physique met bit 19 = 0 → sécurité désactivée. Sur 4700S (C0A *et* C08), bit 19 = 1 → sécurité activée. **Flasher le BIOS C08 ne changera rien.** Le seul scénario restant (très improbable) serait que le PSP du C08 configure `[0x012101C0]` avec bit 19 = 0, mais rien ne le suggère — le BIOS C08 est aussi un BIOS 4700S.

**Piste BIOS C08 : FERMÉE.**

### Comparaison APCB 4700S vs BC-250 (05/10/2026)

**Contexte** : le bloc APCB (AMD Platform Customization Block) à l'offset BIOS `0xAB1000` contient les paramètres OEM lus par AGESA au POST. Comparé entre le BIOS 4700S courant (`now_20261004.bin`) et le BIOS BC-250 (`bc250_2.00.bin`). Taille APCB : 0x488 octets. Second bloc APCB (backup, +0x488) identique dans les deux.

**Résultat** : seulement **11 octets** diffèrent, répartis en 5 zones :

| Zone | Groupe | Type | Description | 4700S | BC-250 |
|---|---|---|---|---|---|
| 1 | Header | — | UniqueID / ParamCount | 0x24ED / 94 | 0x2144 / 133 |
| 2 | PSPG 0x1701 | 0x02 | Version AGESA embarquée | 0x08110000 | 0x21110900 |
| 3 | MEMG 0x1704 | 0x07 | Token mémoire (instance 0) | 00, 0000 | 01, 0020 |
| 4 | MEMG 0x1704 | 0x08 | Token mémoire (instance 1) | 00, 0000 | 01, 0020 |
| 5 | **CBSG 0x1707** | **0x0D** | **CBS_CMN_GNB** | **00, 0000** | **01, 0020** |

**Structure décodée** : chaque groupe contient un répertoire de tokens (4 octets/token : instance, ID, type, padding) suivi des valeurs. Le motif est identique dans les 3 zones fonctionnelles (3-5) : un octet 0→1 (flag d'activation) et un octet à +2 qui passe de 0→0x20.

**Zones 1-2 (métadonnées)** : UniqueID = checksum OEM. ParamCount = nombre de paramètres (plus élevé sur BC-250). Version AGESA = référence du firmware PSP intégrée dans la config. Aucun levier.

**Zones 3-4 (MEMG type 0x07/0x08)** : tokens dans le groupe Mémoire (0x1704), dupliqués dans deux instances identiques. Probablement liés à l'allocation UMA (framebuffer iGPU). Sur 4700S, le flag est à 0 (pas d'UMA pour iGPU) ; sur BC-250, à 1 avec paramètre 0x20.

**Zone 5 (CBSG type 0x0D = CBS_CMN_GNB)** : tokens dans le groupe CBS (0x1707), sous-type 0x0D = Graphics North Bridge. Token 5 (1 octet) passe de 0 à 1 (activation GNB/iGPU). Token 6 (2 octets) passe de 0x0000 à 0x0020 (paramètre GNB associé).

**Impact** : ces tokens CBS sont lus par AGESA au POST. Les modifier dans le BIOS 4700S amènerait AGESA à tenter d'initialiser le chemin GNB/iGPU. **Cependant** : le fusible matériel (bit 19 de `[0x012101C0]`) reste à 1 → le PMFW bloquera l'allumage GFX quand même. C'est un **verrou complémentaire** (nécessaire mais pas suffisant). Note : `IgpuControl` (token 0x4B, dans un APCB CBS plus grand, déjà patché à 1) couvre le masquage PCI côté x86 ; les tokens CBSG type 0x0D couvrent la config AGESA côté GNB/mémoire — ce sont deux couches différentes.

**Piste APCB : OUVERTE pour compléter la piste 1** (msg 0x98 vers SMUIO). Modifier ces 6 octets pourrait préparer le terrain AGESA (UMA allouée, GNB initialisé) avant qu'on tente l'allumage GFX via msg 0x98. Sans effet seul.

### Piste 1 : analyse complète msg 0x98 → SMUIO (05/10/2026)

#### Rappel : msg 0x98 (handler 0x27134, garde=0x00)

Écrit la valeur **fixe 0xFF** (`movi a12, 255`) à SMN[ARG] via le chemin SMN interne du SMU (fenêtrage 0x02Cxxxxx → slot 0x03220038). Accès SMUIO confirmé par test (0x5A868 : 0x01 → 0xFF). La valeur n'est PAS paramétrable.

#### Phase 1 SMUIO : compatibilité 0xFF

La séquence Phase 1 du BC-250 (PC 0x29E9A-0x29F5B) fait 5 opérations RMW sur les registres SMUIO (base Xtensa 0x0115A200 → SMN 0x0005A200) :

| # | Registre | SMN | Opération BC-250 | Valeur cible | 0xFF | Verdict |
|---|----------|-----|-------------------|-------------|------|---------|
| 1 | +0x120 | 0x5A320 | AND ~2 → clear bit 1 | bit 1 = 0 (power gate OFF) | bit 1 = 1 | **BLOQUANT** : 0xFF renforce le gate |
| 2 | +0x134 | 0x5A334 | OR 0x30 → set bits 4-5 | 0x3F (clock enable) | 0xFF | Incertain — bits 6-7 en trop |
| 3 | +0x130 | 0x5A330 | OR 1, AND ~0xE → set 0, clear 1-3 | 0x01 (reset deassert) | 0xFF | **BLOQUANT** : bits 1-3 doivent être 0 |
| 4 | +0x12C | 0x5A32C | OR 0x17, AND ~8 → set 0,1,2,4, clear 3 | 0x17 (domain ctrl) | 0xFF | **BLOQUANT** : bit 3 doit être 0 |
| 5 | +0x138 | 0x5A338 | OR 1 (conditionnel, après init GFX page) | 0x01 (handshake) | 0xFF | Acceptable — surensemble |

**Résultat : 0xFF est incompatible avec 3 registres sur 5.** Le registre critique est 0x5A320 (power gate) : écrire 0xFF maintient bit 1 = 1, l'îlot GFX reste éteint.

#### Registre 0x5A328 : pas un compagnon CLR

Hypothèse testée : 0x5A328 pourrait être un registre « write-1-to-clear » associé à 0x5A320. Code analysé dans les deux PMFW :
- C0A (PC 0x2D944-0x2D96F) : `l32i a5, base, 0x128 ; and a5, ~1 ; or a5, bit ; s32i`
- BC-250 (PC 0x31CA3-0x31CCB) : identique

Les deux font un RMW standard (read/AND/OR/write). Un registre CLR ne nécessiterait pas de lecture préalable. **0x5A328 est un registre indépendant avec sa propre logique de contrôle bit 0.**

#### Exclusivité de msg 0x98

Analyse exhaustive : **26 fonctions** appellent `smn_write` (0x2A74) dans le PMFW C0A. Seul msg 0x98 est accessible depuis un handler non gardé. Les 25 autres sont :
- Dans des handlers avec guard=0x02 (ex: Q3 msg 0x2C handler 0x26E10 — écrit ARG comme valeur, mais bloqué)
- Dans des fonctions internes non atteignables depuis aucun handler non gardé
- Vérification : chaîne d'appels sur 2 niveaux, 4 files × tous les handlers non gardés (95+ handlers)

Le handler le plus prometteur, Q3 msg 0x2C (0x26E10), appelle `smn_write(slot=0, addr=[pool], value=ARG, width=2)` — écriture paramétrable ! — mais son guard=0x02 le verrouille.

#### Phase 3 : page GFX inaccessible

La page GFX (registres à SMN 0x0900Bxxx) est accédée par le BC-250 via le bus local Xtensa (0x0100Bxxx). msg 0x98 utilise le chemin SMN fenêtré (0x02Cxxxxx). **Testé** : écriture msg 0x98 vers SMN 0x0900B100 → gel SMU (bus hang, coupure secteur). Le PSP bloque l'accès SMN 0x09xxxxxx pour tous les initiateurs sauf le bus local Xtensa.

Même si 0xFF était acceptable pour Phase 1, Phase 3 (handshake GFX, diviseurs CLK, écriture B034 bit 0) est structurellement hors de portée de msg 0x98.

#### Bypass du flag de sécurité (SRAM 0x7B0C)

Si on pouvait écrire 0 à l'adresse SRAM 0x7B0C (security_flag initialisé depuis le fusible bit 19), les msgs 0x2B/0x2C (guard=0x02) seraient débloqués, offrant une écriture SMN paramétrable.

Analyse des 95+ handlers non gardés pour ARG-as-store-address :
- **Q0 msg 0x33** (handler 0x261AC) : stocke une valeur MMIO à l'adresse tirée d'une table de pointeurs (pool [0x17C10] = 0x10C90). Table décodée : 112 pointeurs dans la plage 0x107xx-0x10Bxx. **Aucun ne pointe vers 0x7B0C.**
- **Q3 msg 0x4F** (handler 0x26F88) : stocke ARG[15:0] signé à l'adresse `base + idx×964 + 0x3B8` (base = pool [0x17174] = 0xCF50). Adresse minimum = 0xD308, maximum = 0x10B84. **0x7B0C est en-dessous de la plage.**
- **Sub 0x26494** (appelée par Q2 msg 0x2A, Q3 msg 0x20/0x77/0x8B) : stocke une constante de pool à [paramètre+4]. Le paramètre est un pointeur de struct passé par l'appelant, pas ARG. **Valeur non contrôlable.**

Seule la fonction d'init 0x1B024 (exécutée au boot, pas un handler) écrit à 0x7B0C.

**Piste 1 : FERMÉE.**

Raisons cumulées :
1. Valeur 0xFF fixe, incompatible avec 3/5 registres Phase 1
2. Pas de registres CLR dans le bloc SMUIO power
3. Aucun autre smn_write accessible (25 appelants bloqués ou inaccessibles)
4. Phase 3 (page GFX SMN 0x09xxxxxx) inaccessible via msg 0x98
5. Bypass security_flag impossible (aucun handler non gardé ne peut écrire à 0x7B0C)

---

### Exploration exhaustive Q2 / mbox 2 (05/10/2026, session 7 suite)

42 messages, **tous guard=0x00** (accès libre). Registres : CMD=0x03B10528, RSP=0x03B10564, ARG=0x03B10998.

**Résultat : aucun levier caché.**

Répartition fonctionnelle :
- ~30 handlers triviaux (8-20 insns) : lisent ARG, stockent dans SRAM → paramètres DPM (courbes V/F, limites thermiques, ventilation).
- **msg 0x1E** : seul handler avec écriture MMIO. Appelle sub 0x26028 qui fait 3 RMW sur SMUIO 0x5A094 (clear bits 1, 4, 16). Séquence fixe, pas de paramètre ARG. Registre 0x5A094 = config SMUIO, pas power domain.
- **msg 0x0A** : retourne 0x05 (constante). Appelle sub 0x280C4 = lecteur de bit status à SMU register 0x032000E8.
- **msg 0x09** : appelle sub 0x3555C = prédicat (retourne 1 si octet[11]==3, sinon 0). 7 instructions, aucune écriture.
- **msg 0x05/0x06** : chemin le plus profond. Appellent 0x1D438 (dispatcher DPM avec table de pointeurs de fonction à SRAM 0xCB68). Le dispatcher itère sur un bitmap et appelle des callbacks.
  - 4 callbacks (0x29F64, 0x29FC4, 0x2A064, 0x2A0B0) atteignent smn_write via sub 0x237DC.
  - **Sub 0x237DC** : switch sur un index (0-8), écrit dans NBIO (0x11180460, 0x1118018C), CLK (0x0116xxxx), MMHUB (0x01F3A200). **Toutes les adresses sont des constantes de pool.** Aucune ne cible les registres SMUIO power 0x5A320-338. ARG ne parvient pas jusqu'aux paramètres de smn_write.
- **msg 0x17** : appelle 0x29DC4, stocke ARG dans SRAM 0x156DC.
- **msg 0x1D** : appelle 0x1B1E4, stocke ARG dans SRAM 0xC700.
- **msg 0x2C (Q2)** : appelle 0x2DD7C = conversion flottante DPM. Pas de smn_write.
- **msg 0x27/0x28** : I2C (déjà fermé session 4).
- **msg 0x30** : appelle 0x1CECC (validateur de bornes, retourne 0/1) et 0x01014 (table lookup read-only).
- **msg 0x0B** : appelle 0x01014 (table lookup). Aucune écriture.
- **msg 0x1B/0x1C** : config I2C dans SRAM 0x15300 (enable/disable + valeur). Non pertinent.

Sous-fonctions analysées :
| Adresse | Rôle | Écritures |
|---------|------|-----------|
| 0x3555C | prédicat (byte==3?) | aucune |
| 0x01014 | table lookup stride 12 | aucune (read-only) |
| 0x1CECC | validateur de bornes | aucune (retourne 0/1) |
| 0x1D438 | dispatcher DPM bitmap | indirectes via callx8 |
| 0x237DC | enable features DPM | smn_write → NBIO/MMHUB (fixe) |
| 0x26028 | disable SMUIO 0x5A094 | RMW clear bits 1,4,16 (fixe) |
| 0x280C4 | lecteur bit status | aucune (read-only) |
| 0x29DC4 | SRAM store | SRAM 0x156DC |
| 0x1B1E4 | SRAM store | SRAM 0xC700 |
| 0x2DD7C | conversion float DPM | SRAM (paramètres) |

---

### Bilan : surface d'attaque logicielle épuisée (05/10/2026)

Les **4 files de messages** du PMFW 4700S C0A sont entièrement cartographiées :

| File | Msgs | Guard=0 | Résultat |
|------|-------|---------|----------|
| Q0 (mbox 0) | 55 | 55 | copie table MMIO (msg 0x33), aucun primitif utile |
| Q2 (mbox 2) | 42 | 42 | DPM params, 1 MMIO write (0x5A094, fixe), smn_write via DPM → NBIO (fixe) |
| Q3 file 2 (mbox 3/4) | 169 | 95 | msg 0x98 = seul smn_write non gardé, **valeur fixe 0xFF** |
| Q3 file 3 (mbox 5) | ? | ? | sous-ensemble Q3 |

**Aucun chemin logiciel ne permet d'écrire une valeur choisie aux registres SMUIO power 0x5A320-338 ni à la page GFX 0x09xxxxxx.**

Raisons structurelles :
1. Le PMFW 4700S n'a **aucune référence** aux registres SMUIO power (0x5A320-338) dans son literal pool — le code GFX a été supprimé.
2. Le seul smn_write non gardé (msg 0x98) écrit une constante 0xFF.
3. Le smn_write paramétrable (Q3 msg 0x2C) est verrouillé par guard=0x02 (fusible matériel).
4. La page GFX (SMN 0x09xxxxxx) est inaccessible via le windowed path — gel SMU.
5. Le security_flag (SRAM 0x7B0C) est écrit uniquement à l'init par un fusible matériel.

**Piste PMFW patch — FERMÉE (06/10/2026)** : analyse PSPTool confirme RSA-2048 sur le body entier (256 Ko), clé racine fusée (chaîne CRD, clé B6F9). `encrypted=False` (lisible mais non modifiable). 1 seul bit changé → SHA-256 invalide → rejet PSP → no-POST. Aucun PMFW modifié n'a jamais booté publiquement. Seul bypass connu : voltage glitch (Buhren et al., CCS 2021).

**Pistes restantes (toutes matérielles) :**
- **SPI Flash MitM (FPGA)** : intercepter les lectures SPI pendant le boot PSP pour présenter un PMFW modifié. Nécessite de contourner la signature PSP (TOCTOU, fault injection).
- **Fault injection PSP** : glitching voltage/clock pendant la vérification de signature. Approche avancée.

---

### Image E : APCB tokens GNB/MEMG (06/10/2026)

**Base** : image D (IgpuControl=1, UMA 512 Mo, boot stable).

**Modifications APCB** (offset BIOS 0xAB1000, bloc primaire uniquement, backup=0xFF) :

| Offset APCB | Offset BIOS | Avant | Après | Token |
|---|---|---|---|---|
| +0x010 | 0xAB1010 | 0xBF | 0x5F | Checksum (byte-sum mod 256 = 0) |
| +0x221 | 0xAB1221 | 0x00 | 0x01 | MEMG 0x1704 type 0x07 — flag activation |
| +0x223 | 0xAB1223 | 0x00 | 0x20 | MEMG 0x1704 type 0x07 — paramètre |
| +0x2CD | 0xAB12CD | 0x00 | 0x01 | MEMG 0x1704 type 0x08 — flag activation |
| +0x2CF | 0xAB12CF | 0x00 | 0x20 | MEMG 0x1704 type 0x08 — paramètre |
| +0x462 | 0xAB1462 | 0x02 | 0x20 | CBSG 0x1707 type 0x0D — paramètre GNB (LE16: 0x0002→0x0020) |

Fichier : `work/bios/4700s_imgE_apcb_gnb.bin`
SHA256 : `cbbc30e71241bebc24f827aa5a7e2cef7cf4dcff5066035dc696b1adb98410a5`

**Effet attendu** : AGESA lit les tokens MEMG (config mémoire iGPU) et CBSG (init GNB complet) au POST. Le PMFW reçoit EnableSmuFeatures avec bit 6 (GFX DPM) via mbox 2 msg 0x05. L'ABL pourrait envoyer des messages SMU supplémentaires.

**Ce que ça ne fait PAS** : allumer l'îlot GFX — le PMFW 70.x n'a pas le code. Mais le rail VRM GFX est alimenté (0,83 V, Badcaps) et un effet de bord ABL/AGESA sur les registres SMUIO power n'est pas exclu.

**Plan de test** :
1. Flasher : `sudo flashrom -p internal -w work/bios/4700s_imgE_apcb_gnb.bin`
2. Booter, vérifier POST
3. `lspci -nn | grep -i vga` (device ID, subsystem)
4. `dmesg | grep -iE 'uma|igpu|gnb|gfx|amdgpu'`
5. Lecture SMUIO : `sudo python3 scripts/smnread.py /tmp/smnlog_imgE.log 0x5A320 0x5A32C 0x5A330 0x5A334 0x5A338`
6. Comparer les valeurs SMUIO avec l'état « GFX off » connu (image D)
7. Si changement → analyser et documenter
8. Si identique → APCB seul ne suffit pas, confirme que le verrou est 100% dans le PMFW signé

**Repli** : si no-POST, flasher image D (`4700S_dump_igpu_D_cbsuma512.bin`) ou image B-bis avec CH341A.

### Résultat image E (06/10/2026)

**POST** : OK — ventilateur à fond 2 s puis régulation normale (identique à image D).

**lspci** : iGPU visible `01:00.0 VGA [0300]: 1002:13fd`. Le BIOS la désigne comme boot VGA device (`vgaarb: setting as boot VGA device`).

**PCI détail** :

| BAR | Adresse | Taille | État |
|---|---|---|---|
| 0 (framebuffer) | 0xC0000000 | 256 Mo | disabled |
| 2 (doorbell) | 0xD0000000 | 2 Mo | disabled |
| 4 (I/O) | 0xE000 | 256 o | disabled |
| 5 (MMIO) | 0xFD400000 | 512 Ko | disabled |

- `Control: Mem- BusMaster-` → device non activé
- `Status: >TAbort+` → accès MMIO rejeté (îlot GFX éteint)
- `LnkCap/Sta: 16GT/s x16` (Gen4, lien interne SoC) mais `DLActive-` → data link down

**SMUIO power** :

| Registre | Valeur | Comparaison image D |
|---|---|---|
| 0x5A328 | 0x00000000 | identique |
| 0x5A32C | 0x00000008 | identique |
| 0x5A330 | 0x0000000E | identique |
| 0x5A334 | 0x0000000F | identique |
| 0x5A338 | 0x00000000 | identique |

**e820** : 8 Go réservés `0x270000000-0x46FFFFFFF` (moitié GPU du GDDR6). Mémoire système : ~7,7 Go / 8 Go.

**Conclusion** : les tokens APCB (MEMG + CBSG GNB) n'ont **aucun effet** sur les registres SMUIO power. L'îlot GFX reste éteint. Le verrou est confirmé à **100% dans le PMFW signé** — ni l'APCB, ni IgpuControl, ni les tokens AGESA ne peuvent allumer le GFX. La prise de courant AGESA/ABL est en amont du PMFW mais ne touche pas aux registres power.

**Piste APCB — FERMÉE.**

Toutes les approches logicielles et de configuration sont épuisées. Les seules pistes restantes sont **matérielles** : SPI MitM (FPGA) ou fault injection PSP.
