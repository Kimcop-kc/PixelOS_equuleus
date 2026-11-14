# BLOB_EXTRACTION — proprietary files for `equuleus` / `sdm845-common`

Status: **BLOCKED (B-01).** No proprietary binary exists in this package. Nothing
was fabricated, stubbed, or taken from an unverified third-party `vendor/xiaomi`
repository.

**Neither `vendor/xiaomi/equuleus` nor `vendor/xiaomi/sdm845-common` has been
generated.** The OTA was range-read only (first 1 MiB) to verify its format and
`pre-device` assertion; it was not fully downloaded and `extract-files.py` was
never executed, because both require a synced PixelOS tree that does not exist on
the audit host.

> **Round 8 changed the source.** The recommended route is now a **single
> official LineageOS 22.2 equuleus OTA**, not a five-image reconstruction.
> See [`BLOB_SOURCES.md`](BLOB_SOURCES.md) for the verified source record and
> [`blob_sources.json`](blob_sources.json) for the machine-readable version.
>
> ```bash
> scripts/fetch_lineage_ota.sh --dest /data/ota
> scripts/extract_blobs_from_ota.sh /data/pixelos15 \
>     /data/ota/lineage-22.2-20261110-nightly-equuleus-signed.zip
> python3 scripts/verify_blobs.py /data/pixelos15 --strict --json blob-report.json
> ```
>
> Why one OTA suffices: the LineageOS wiki documents that `extract-files.py`
> accepts an installation ZIP, and the download API's dependency list for
> equuleus is **exactly** the four repositories this project pins.

Sections 1 and 2 below document the *historical* provenance recorded inside the
device trees. They remain accurate and remain the fallback if the OTA route
yields gaps — but they are no longer the first thing to attempt.

---

## 1. Historical provenance recorded in the device trees (fallback)

Derived mechanically from the two `proprietary-files.txt` files (the section
comments are the maintainers' own provenance statements). Counts are blob lines,
not comment lines.

### 1.1 `device/xiaomi/equuleus` — 235 blob lines, **one** source

| Group | Lines | Firmware | Version / region | Android | Yield |
| --- | --- | ---: | --- | --- | --- |
| Device proprietary files | **235** | Xiaomi MI 8 Pro | **V12.5.2.0.QECCNXM** CN stable | 10 (Q) | everything device-specific |

`V12.5.2.0.QECCNXM`: `EC` = **equuleus**, `CN` = China, `XM` = Xiaomi. This one
image is sufficient for the whole `equuleus` tree.

### 1.2 `device/xiaomi/sdm845-common` — 627 blob lines, **five** sources

| Group | Lines | Source device | Firmware / build | Notes |
| --- | ---: | --- | --- | --- |
| Common proprietary files | **121** | beryllium (POCO F1) | **V12.0.3.0.QEJMIXM** global stable | the "default" group |
| Display (SDM) | 8 | PNX | **RKQ1.200906.002** | Pixel/PNX-based CAF display |
| Display (HDR) | 1 | PNX | RKQ1.200906.002 | |
| Display postprocessing | 12 | PNX | RKQ1.200906.002 | |
| Graphics (Adreno) | 39 | PNX | RKQ1.200906.002 | |
| Graphics (Vulkan) | 105 | PNX | RKQ1.200906.002 | largest single group |
| OMX | 6 | PNX | RKQ1.200906.002 | |
| VPP | 15 | PNX | RKQ1.200906.002 | |
| WiFi Display (vendor) | 33 | PNX | RKQ1.200906.002 | |
| DPM | 47 | lemonadep (OnePlus 9 Pro) | **TP1A.220624.003** | |
| Power-off alarm | 193 | caymanslm (LG Velvet) | **SKQ1.211103.001** | largest group overall |
| WiFi Display (system) | 46 | lemonadep | **UKQ1.230924.001** | |
| WiFi Display (vendor) | 1 | lemonadep | TP1A.220624.003 | |

**PNX subtotal: 219 lines** · **lemonadep subtotal: 94** · **caymanslm: 193** ·
**beryllium: 121** → 627.

### 1.3 Why this matrix is no longer the primary route

The five-image reconstruction below is still accurate as a record of what the
lists say, but it is now the **fallback**. The official OTA route replaces it
for the reasons in `BLOB_SOURCES.md` §1. Use this matrix only for entries the
OTA demonstrably cannot supply, and record each such file's origin.

This tree was assembled by LineageOS maintainers from several firmware images
over years. The five-image route was the original plan; the official-OTA route
supersedes it. If a specific group turns out to be absent from the OTA, use this
matrix to decide where *that group* came from — do not rebuild the whole set from
it.

Tracked as B-01 (S1). Nothing else in this package is blocked by it.

---

## 2. Legality and provenance rules

1. Extract only from firmware the device owner lawfully possesses (the phone
   itself, or Xiaomi's own package for that exact model/region/version).
2. **Never** redistribute the extracted binaries. They are not licensed for it.
3. **Never** substitute a different version "because it boots". The blob set is
   coupled to `VENDOR_SECURITY_PATCH := 2020-12-01` and to the kernel's
   `CONFIG_FINGERPRINT_GOODIX_TA`; a mismatch produces bootloops that look like
   SELinux denials and are extremely hard to diagnose.

### 2.1 Version verification before extracting

```bash
# on the phone
getprop ro.product.device                  # equuleus
getprop ro.build.version.incremental       # V12.5.2.0.QECCNXM
getprop ro.vendor.build.security_patch     # 2020-12-01

# on an unpacked system/vendor image
grep -R "ro.build.version.incremental" ./system/build.prop ./vendor/build.prop
```

Abort if `ro.product.device` or the incremental version differs.

---

## 3. Prerequisites in a synced tree

| Requirement | PixelOS fifteen | Verified |
| --- | --- | --- |
| `tools/extract-utils` | `LineageOS/android_tools_extract-utils` | present in manifest |
| Soong namespaces for module resolution | see below | present except the output tree |
| 4 GiB+ free for intermediate firmware | — | environment |

`equuleus/extract-files.py` namespace list:
```
hardware/qcom-caf/sdm845   hardware/xiaomi   vendor/qcom/opensource/display
vendor/xiaomi/sdm845-common        # the output — must exist first
```
`sdm845-common/extract-files.py` namespace list:
```
device/xiaomi/sdm845-common   hardware/qcom-caf/sdm845   hardware/qcom-caf/wlan
hardware/xiaomi   vendor/qcom/opensource/commonsys-intf/display
vendor/qcom/opensource/commonsys/display   vendor/qcom/opensource/dataservices
vendor/qcom/opensource/display
```

**Order is mandatory: `sdm845-common` first, then `equuleus`** — `equuleus`
calls `ExtractUtils.device_with_common(module, 'sdm845-common', module.vendor)`.

---

## 4. Extraction commands

```bash
# --- 1. sdm845-common, bulk group only (the 121 beryllium lines) -------------
cd device/xiaomi/sdm845-common
./extract-files.py /path/to/miui-beryllium-V12.0.3.0.QEJMIXM

# --- 2. the four foreign groups, by hand (no automated path exists) ----------
#   PNX          219 lines   RKQ1.200906.002
#   lemonadep     94 lines   TP1A.220624.003 / UKQ1.230924.001
#   caymanslm    193 lines   SKQ1.211103.001
# For each group, copy only the files the list names, preserving the declared
# destination. See §5 for why a naive `cp -r` is wrong.

# --- 3. equuleus (needs sdm845-common to exist already) ----------------------
cd ../../equuleus
./extract-files.py /path/to/miui-equuleus-V12.5.2.0.QECCNXM

# --- 4. regenerate makefiles only (no blob copy) ----------------------------
cd ../sdm845-common && ./setup-makefiles.py
cd ../equuleus      && ./setup-makefiles.py
```

---

## 5. Why basename matching is wrong — the three parse rules

`extract-utils` parses each line with `SEPARATORS = ';:|'`
(`extract_utils/file.py`, verified against upstream source):

| Prefix | Meaning | Example from this tree |
| --- | --- | --- |
| `:` | **destination remap** — the installed path is *not* the source path | `vendor/lib64/hw/fingerprint.goodix_fod.so:vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so` |
| `;` | build/fixup argument (`KEY` or `KEY=value`) | `vendor/lib/libSNPE.so;DISABLE_CHECKELF`, `…;FIX_SONAME` |
| `\|` | content hash, then fixup hash | `path\|<sha256>\|<fixupsha>` |
| leading `-` | treat as package (APK/JAR), not a copy | `-vendor/app/Foo/Foo.apk` |

Two consequences that a source-path-only check gets **wrong**:

1. **A remapped blob legitimately does not exist under its source name.**
   `fingerprint.goodix_fod.so` must land as
   `fingerprint.goodix_fod.sdm845.so`. Checking for the *source* basename
   reports a false "MISSING", and creating a file under the source name hides a
   real extraction failure.
2. **`FIX_SONAME` mutates the installed ELF after copying.**
   `extract_utils/module.py` calls `blob_fixup().fix_soname()` on the installed
   path when the argument is present. A file can be at the right path with the
   right name and still be wrong, because its `DT_SONAME` was never rewritten.
   The loader then fails to resolve it.

Installed location is always
`vendor/<vendor>/<device>/proprietary/<File.dst>` — the `proprietary` segment
comes from `ExtractUtilsModule(vendor_rel_sub_path='proprietary')`.

### 5.1 The verifier that gets this right

`scripts/verify_blobs.py` re-implements the parser and validates the **final
output**, not the input list:

```bash
python3 scripts/verify_blobs.py /path/to/pixelos15
python3 scripts/verify_blobs.py /path/to/pixelos15 --json blob-report.json
```

It reports, per device tree:

* every entry resolved at `proprietary/<dst>` (**not** `<src>`);
* which entries use a destination remap, and whether the remapped file exists;
* for each `FIX_SONAME` entry, whether the installed file is ELF at all, and its
  actual `DT_SONAME` versus the installed basename (a mismatch means the fixup
  did not run);
* unknown `;`-arguments (a typo in the list would otherwise pass silently);
* counts of `|hash`-pinned entries.

**Limits, stated plainly:** it reads ELF dynamic sections directly (no
`pyelftools`) and therefore cannot *replay* `patchelf`; it verifies the fixup's
target is present and coherent. It does not validate APK signatures, and it
cannot prove a blob came from the declared firmware version unless that line
carries a `|hash`.

---

## 6. Required post-processing (do not hand-copy instead)

`extract-utils` applies these automatically; a manual `cp` does not.

| Blob | Fixup | Symptom if skipped |
| --- | --- | --- |
| `vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so` | `FIX_SONAME` | FOD HAL loads, enrolled prints never persist |
| `vendor/lib/libarcsoft_dualcam_refocus_{front,rear_t,rear_w}.so` | clear symbol versions for `remote_handle_{open,invoke,close}` | camera service aborts entering portrait mode |
| `vendor/lib/libmmcamera_faceproc.so` | clear `__aeabi_memcpy`, `__aeabi_memset`, `__gnu_Unwind_Find_exidx` | `libmmcamera_faceproc` fails ELF check; camera HAL refuses to start |
| `vendor/lib/camera/components/com.qti.node.watermark.so` | add `libpiex_shim.so` | watermark node fails to link |
| `system_ext/lib64/libwfdnative.so` | add `libbinder_shim`, `libinput_shim` | Wi-Fi Display crashes |
| `system_ext/bin/wfdservice` | add `libwfdservice_shim.so` | Wi-Fi Display crashes |
| `system_ext/lib64/lib-imsvideocodec.so` | add `libgui_shim.so` | VoLTE video call crashes |
| `vendor/bin/pm-service` | add `libutils-v33.so` | power manager service crashes |
| `vendor/lib64/libwvhidl.so`, `…/mediadrm/libwvdrmengine.so` | add `libcrypto_shim.so` | Widevine fails; DRM video black-screens |
| `system_ext/lib/libwfdmmsrc_system.so` | add `libgui_shim.so` | Wi-Fi Display crashes |
| `system_ext/etc/permissions/qti_libpermissions.xml` | regex rewrite of `android.hidl.manager-V1.0-java` | permission parse error at boot |
| `system_ext/etc/permissions/qcrilhook.xml` | `/product/framework/` → `/system_ext/framework/` | RIL hook permission path broken |

All shim libraries named above live in `LineageOS/android_hardware_lineage_compat`
(all 7 module names verified in its `Android.bp`), checked out at
`hardware/lineage/compat` by PixelOS fifteen.

---

## 7. Expected output

| Path | Producer |
| --- | --- |
| `vendor/xiaomi/equuleus/BoardConfigVendor.mk` | `setup-makefiles.py` |
| `vendor/xiaomi/equuleus/equuleus-vendor.mk` | `setup-makefiles.py` |
| `vendor/xiaomi/equuleus/Android.bp` | `extract-files.py` |
| `vendor/xiaomi/equuleus/proprietary/**` | `extract-files.py` |
| `vendor/xiaomi/sdm845-common/BoardConfigVendor.mk` | `setup-makefiles.py` |
| `vendor/xiaomi/sdm845-common/sdm845-common-vendor.mk` | `setup-makefiles.py` |
| `vendor/xiaomi/sdm845-common/Android.bp` | `extract-files.py` |
| `vendor/xiaomi/sdm845-common/proprietary/**` | `extract-files.py` + manual groups |

Verify with the authoritative tool, not a basename loop:

```bash
python3 scripts/verify_blobs.py "$TREE"          # must exit 0
scripts/build-preflight.sh "$TREE"               # must exit 0
```

---

## 8. Two non-blob files that also live under `vendor/xiaomi/`

`BoardConfig.mk` / `BoardConfigCommon.mk` reference
`vendor/xiaomi/equuleus.config` and `vendor/xiaomi/mi845_defconfig`, but these
are **kernel configuration inputs**, resolved inside
`kernel/xiaomi/sdm845/arch/arm64/configs/`. Both exist at the pinned kernel
commit. See B-05. Creating them under `vendor/` would break the kernel build.

---

## 9. What was NOT done, and why

| Step | Reason |
| --- | --- |
| Downloading MIUI firmware | Not present on this machine; a 2–4 GiB image per source (five sources) from a mirror would be unverifiable without the phone |
| Running `extract-files.py` | Requires a fully synced tree (hundreds of GB) plus the firmware |
| Creating any `vendor/xiaomi/**` file | Would be a fabricated binary or a stub that hides a real dependency |
| Using a third-party `vendor/xiaomi` repo | Unverifiable provenance; forbidden |

Honest state: **the source and verification tooling side is complete and
reviewable; the blob side needs the physical phone and five firmware images.**
