# KNOWN_BLOCKERS — PixelOS fifteen / equuleus

Every blocker states **severity**, **evidence**, **how to reproduce the
finding**, **suggested fix**, and **current status**. Status vocabulary:

* `OPEN` — unsolved, blocks a usable ROM.
* `MITIGATED` — a workaround is in this deliverable, risk remains.
* `ACCEPTED` — known and deliberately accepted for a first bring-up.
* `INFO` — no action needed, recorded so nobody re-discovers it as a surprise.
* `CLOSED` — was open, now resolved with evidence; kept for the audit trail.

Severity: **S1** = cannot produce a bootable ROM. **S2** = builds but a listed
feature is expected to fail. **S3** = maintainability / supply-chain risk.
**S4** = cosmetic or documentation.

---

## B-01 — Proprietary blobs: EXTRACTED, but the ROM is still unbuilt and untested

**Severity:** S1 for shipping, **no longer blocking extraction** · **Status:** MITIGATED — trees generated and strictly verified; ROM not compiled

### What was actually done (2026-11-12)

One official LineageOS 22.2 equuleus OTA was downloaded in full, verified, and
turned into both proprietary trees. Nothing was fabricated.

| Step | Result |
| --- | --- |
| OTA download | `lineage-22.2-20261110-nightly-equuleus-signed.zip`, 1,223,204,572 bytes |
| SHA256 | `2ebd3d4bb7168135353c8b543bb79da4e53a1efccf32fd91c498e9fa9fe365ee` — **matches** the published digest |
| Device assertion | `pre-device=equuleus`, `ota-type=BLOCK` |
| Block extraction | 5 partitions → valid ext4 images (vendor 631 MiB, product 2.4 GiB, system_ext 504 MiB, system 1.1 GiB, odm 1.5 MiB) |
| Partition dump | 8,268 files via `debugfs` (read-only, no root, original images untouched) |
| List resolution | **862 entries: 862 found, 0 missing** |
| Trees generated | `vendor/xiaomi/equuleus` (240 files, 248 MiB), `vendor/xiaomi/sdm845-common` (632 files, 277 MiB) |
| Strict verification | **PASS** — `FAIL=0`, 862/862 present |

### The two problems that had to be solved

**1. 35 entries whose source path does not exist but whose destination does.**
All 35 are the same class: the list names `product/…` or `system/…`, while
LineageOS ships the file under `system_ext/…` (the Android 11+ system_ext
migration). The bytes are present; only the path differs. They are installed at
the list's `dst`, with the actual source recorded per file.

**2. `vendor/lib/libpn553_fw.so` does not exist as a 32-bit library.**
Measured on the OTA:

| | |
| --- | --- |
| List requests | `vendor/lib/libpn553_fw.so` (32-bit path) |
| OTA contains | **only** `vendor/lib64/libpn553_fw.so` |
| Size | 37,490 bytes |
| ELF class | **ELF64**, machine **183** (`EM_AARCH64`) |
| `DT_SONAME` | **none** |
| `DT_NEEDED` | **none** |
| Referenced by | `libnfc-nxp.conf`: `NXP_FW_NAME="libpn553_fw.so"` |
| Sibling | `vendor/firmware/libpn553_rec.so`, byte-identical size |

It is **NXP PN553 NFC firmware in an ELF container**, consumed by filename — not
a loadable shared object, so no 32-bit ABI is involved. Substituting a 64-bit ELF
at the `lib/` path (or inventing a 32-bit file) was rejected. The list is
corrected by `patches/0006-equuleus-fix-pn553-fw-path.patch`, verified with
`git apply --check`, and the file is installed at `lib64/`.

### Fixups were NOT re-applied

The OTA already carries upstream's fixups. Verified example:
`vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so` already has
`DT_SONAME == fingerprint.goodix_fod.sdm845.so`, i.e. the rename is done. Running
`FIX_SONAME` again would double-patch. `verify_blobs.py` was corrected for this:
a declared `fixup_hash` with no fixup function now passes **only** when the hash
actually matches (the ROM already applied it), and fails otherwise.

### Architecture audit

| Check | Result |
| --- | --- |
| ELF32 files | 273, all under `lib/` |
| ELF64 files | 351, all under `lib64/` |
| 32/64-in-wrong-directory | **0** |
| `DT_SONAME` matching installed basename | 538 |
| `DT_SONAME` mismatching | **0** |

### 5 APKs are re-signed

`dpmserviceapp`, `PowerOffAlarm`, `WfdService`, and two
`HotwordEnrollment*WCD9340` APKs hash differently from the pinned values because
LineageOS re-signs platform APKs. They are reported as **RESIGNED**, not as
passes and not as defects, with both hashes recorded. This is a provenance
difference; it is also not proof the APKs are correct.

### What is still NOT true

* The ROM has **not** been compiled. `repo sync`, `lunch`, Soong and `mka bacon`
  have never run.
* Nothing has been flashed; there is no device evidence.
* **Screen fingerprint, camera and NFC are unverified on hardware.**
* The generated trees were produced by a purpose-built block-OTA extractor
  (`scripts/ota_extract.py` + `make_vendor_trees.py`), **not** by upstream
  `extract-files.py`, because that needs a synced tree for Soong name
  resolution. The result is verified against the same lists, but it is a
  different code path and should be cross-checked by running `extract-files.py`
  on a real synced tree.

### Reproduce

```bash
scripts/extract_vendor_full.sh --ota lineage-22.2-20261110-*.zip --tree /data/pixelos15
```

Full record: `B01_EXTRACTION_REPORT.json`.

---

## B-02 — `XiaomiParts` is built but never exercised; `XiaomiPocketMode` is dead code

**Severity:** S2 · **Status:** OPEN (compile risk in `XiaomiParts`) · **Owner:** first successful build

**Evidence (corrected — an earlier draft of this document wrongly said
`XiaomiParts` was not packaged; it *is*).**

* `sdm845-common/sdm845.mk:132-134` **does** add `XiaomiParts` to
  `PRODUCT_PACKAGES`. So this app is on the build's critical path.
* `sdm845-common/parts/Android.bp` declares `android_app { name: "XiaomiParts"
  … system_ext_specific: true, privileged: true, platform_apis: true,
  static_libs: ["org.lineageos.settings.resources"] }`.
* `org.lineageos.settings.resources` is provided by
  `LineageOS/android_packages_resources_devicesettings`, which PixelOS fifteen
  **does** check out at `packages/resources/devicesettings`
  (`snippets/lineage.xml:79`). Its `Android.bp` uses the `SettingsLibDefaults`
  default, and `SettingsLibDefaults` **does** exist in PixelOS'
  `frameworks_base@fifteen` (`packages/SettingsLib/Android.bp:92`).
* `XiaomiParts` sources import
  `com.android.settingslib.collapsingtoolbar.CollapsingToolbarBaseActivity`,
  `.R.id.content_frame`, and `com.android.settingslib.widget.MainSwitchPreference`.
  In PixelOS fifteen the module is named
  **`SettingsLibCollapsingToolbarBaseActivity`** and lives at
  `packages/SettingsLib/CollapsingToolbarBaseActivity/` (verified: `Android.bp`
  + 8 java files under `src/com/android/settingslib/collapsingtoolbar/`).
  The **Java package name is unchanged**, so the imports still resolve — the
  module *path* and *Soong name* moved, which matters only if something
  `static_libs` it by name. `XiaomiParts` does not; it inherits the class
  transitively through `Settings`-family defaults. **This is the one genuinely
  unproven step** and it is a *compile* risk, not a runtime risk.
* `XiaomiPocketMode` (`sdm845-common/pocketmode/Android.bp:7`) is **not**
  referenced by any `*.mk` in either device tree
  (`grep -rn PocketMode *.mk` → no match). It is dead code: declared, never
  installed.

**Reproduce.**
```bash
grep -n -A2 'Device-specific settings' device/xiaomi/sdm845-common/sdm845.mk
grep -rn 'PocketMode' device/xiaomi/*/*.mk          # no output
grep -n 'SettingsLibDefaults' packages/SettingsLib/Android.bp
```

**Suggested fix.** Build and read the error. Two likely outcomes:
1. It compiles — then delete `pocketmode/` and this blocker closes.
2. `CollapsingToolbarBaseActivity` is unresolved — add
   `static_libs: ["SettingsLibCollapsingToolbarBaseActivity"]` to
   `parts/Android.bp`. That is a one-line, upstream-safe change; do **not**
   vendor a SettingsLib copy.

**Why nothing was changed here.** Adding a `static_libs` entry that may be
unnecessary would be an unverified edit to the build graph. The honest state is
"probably compiles, unproven".

**Second-order risk.** `XiaomiParts` is `system_ext_specific: true` and
`privileged: true`. If `SYSTEMEXT_SEPARATE_PARTITION` sizing is tight (see
B-06), this app lands in `system_ext` inside the 4.81 GiB super — worth watching
on the first build.

---

## B-03 — PixelOS fifteen is archived and on a 2025 security level

**Severity:** S3 (security) · **Status:** ACCEPTED for prototyping

**Evidence.** `PixelOS-AOSP/manifest@fifteen` head is
`0334d5e4…` dated **2025-06-18**, and the branch is archived (read-only).
This deliverable's `UPSTREAM_LOCK.md` §1 records it.

**Reproduce.** `git ls-remote https://github.com/PixelOS-AOSP/manifest refs/heads/fifteen`
and compare the date with today; the branch never moves.

**Suggested fix.** Treat this ROM as a bring-up prototype. For daily use, port
the finished device tree to `PixelOS-AOSP/android_manifest@seventeen`
(`29f6010b…`). That is a *different* Android generation: do not
`repo init` seventeen and drop this tree in — `breakfast` + `m pixelos` replace
`lunch` + `mka bacon`, and the HIDL HALs here would need AIDL replacements.

**Honest note.** Do not tell the user this ROM is "current". It is not.

---

## B-04 — Kernel source obtained in full; fragment dependency confirmed

**Severity:** S3 (informational) · **Status:** CLOSED

**Evidence (was: audit gap; now resolved).** The full tree at
`LineageOS/android_kernel_xiaomi_sdm845@aa8adfe9bf212c6e93238a86980b4024da4f819a`
was downloaded as a 174,356,433-byte tarball and extracted (earlier attempts had
stalled at 7.8-10 MB). Verified from the extracted tree:

* `Makefile`: `VERSION = 4`, `PATCHLEVEL = 9`, `SUBLEVEL = 337`
* `arch/arm64/configs/vendor/xiaomi/` contains `mi845_defconfig` (16,053 B),
  `equuleus.config` (361 B) plus `beryllium`, `dipper`, `perseus`, `polaris`,
  `ursa` fragments — i.e. the whole sdm845 family ships from this one repo.

**The fragment is load-bearing, not cosmetic.** Every device-specific option
lives *only* in `equuleus.config`; the shared base defconfig has none of them:

| Config | in `mi845_defconfig` | in `equuleus.config` |
| --- | --- | --- |
| `CONFIG_FINGERPRINT_GOODIX_TA` | **absent** | `=y` |
| `CONFIG_TOUCHSCREEN_ST_FTS_V521` | **absent** | `=y` |
| `CONFIG_MACH_XIAOMI_E1S` | **absent** | `=y` |
| `CONFIG_BCM_GPS_SPI_DRIVER` | absent | `=y` |
| `CONFIG_LEDS_LM3644` | absent | `=y` |
| `CONFIG_INPUT_PRESS_NDT` (+`_F60`, `_M65`) | absent | `=y` |

**Consequence.** If `equuleus.config` were dropped (e.g. by treating
`TARGET_KERNEL_CONFIG +=` as an overwrite instead of a list append), the kernel
would build without the Goodix TEE interface and without the FTS touch
controller — a device that boots but has no fingerprint and no touch. See B-05
for why the *path* of these files is confusing.

**Reproduce.**
```bash
curl -sSL -o k.tgz https://codeload.github.com/LineageOS/android_kernel_xiaomi_sdm845/tar.gz/aa8adfe9bf212c6e93238a86980b4024da4f819a
mkdir k && tar xzf k.tgz -C k
grep -E "GOODIX|ST_FTS|MACH_XIAOMI" k/*/arch/arm64/configs/vendor/xiaomi/equuleus.config
grep -c "CONFIG_FINGERPRINT_GOODIX_TA" k/*/arch/arm64/configs/vendor/xiaomi/mi845_defconfig   # 0
```

---

## B-05 — `vendor/xiaomi/{mi845_defconfig,equuleus.config}` look like blobs but are kernel configs

**Severity:** S3 (misdiagnosis trap) · **Status:** MITIGATED (documented)

**Evidence.** `BoardConfigCommon.mk:38` sets
`TARGET_KERNEL_CONFIG := vendor/xiaomi/mi845_defconfig` and
`equuleus/BoardConfig.mk:21` appends `vendor/xiaomi/equuleus.config`, but
`TARGET_KERNEL_SOURCE := kernel/xiaomi/sdm845` means the build resolves them
inside the kernel tree at `arch/arm64/configs/<name>`. Both files exist there
in the pinned kernel commit (16,053 B and 361 B, verified).

**Reproduce.**
```bash
ls kernel/xiaomi/sdm845/arch/arm64/configs/vendor/xiaomi/
# mi845_defconfig  equuleus.config  dipper.config  beryllium.config …
ls vendor/xiaomi/            # must not contain these two files
```

**Suggested fix.** None needed. If a future error says
`vendor/xiaomi/mi845_defconfig` is missing, the kernel checkout is broken — do
**not** create that file under `vendor/`.

---

## B-06 — PixelOS reserves no product/system space; super is only 4.81 GiB

**Severity:** S2 · **Status:** OPEN (sizing risk) · **Owner:** first successful build

**Evidence.** Super partition is `5,167,382,528` B with a
`qti_dynamic_partitions` group of `5,163,188,224` B
(`BoardConfigCommon.mk:87-94`). The LineageOS
`BoardConfigReservedSize.mk` reserves ~1.90 GiB for `product` and 90 MiB each
for `system`/`system_ext`; **PixelOS' replacement file only sets
`BOARD_PRODUCTIMAGE_MINIMAL_PARTITION_RESERVED_SIZE ?= true` for virtual A/B**
(read in full: 7 lines, no other content). This device is `AB_OTA_UPDATER :=
false`, so even that one line is inert.

**Reproduce.** diff the two files:
```bash
curl -s https://raw.githubusercontent.com/LineageOS/android_vendor_lineage/lineage-22.2/config/BoardConfigReservedSize.mk \
  | diff - vendor/aosp/config/BoardConfigReservedSize.mk
```
The delivered patch `0003-sdm845-common-use-vendor-aosp.patch` does exactly this
substitution and carries a warning comment at the call site.

**Suggested fix.** Two options, both requiring a real build to choose:
1. Let the first build reveal the real image sizes; if
   `BOARD_QTI_DYNAMIC_PARTITIONS_SIZE` overflows, add explicit
   `BOARD_{PRODUCT,SYSTEM,SYSTEM_EXT}IMAGE_PARTITION_RESERVED_SIZE` values.
2. Add a local `BoardConfigReservedSize` equivalent to the device tree instead
   of relying on `vendor/aosp/config/…`.

Do **not** change `BOARD_SUPER_PARTITION_*` or the block-device sizes: those are
physical layout facts of the phone and were not verified against the device.

---

## B-07 — `hardware/lineage/interfaces` pin, and PixelOS' framework matrix is older

**Severity:** S2 · **Status:** MITIGATED by pin, residual risk OPEN

**Evidence (two separate facts).**

1. *The interfaces pin is required.* `sdm845-common/livedisplay/Android.bp`
   links `vendor.lineage.livedisplay-V1-ndk` and includes
   `aidl/vendor/lineage/livedisplay/BnSunlightEnhancement.h`. At PixelOS'
   locked revision `f5689956…` there is **no `livedisplay/aidl` directory**
   (tarball listing: only `2.0/` and `2.1/`). The AIDL tree exists at
   `3466aa53…`. `UPSTREAM_LOCK.md` §4.2 pins the latter via
   `<extend-project>`.
2. *PixelOS' framework matrix is older.*
   `vendor/aosp/config/device_framework_matrix.xml` is dated 2021-2023 and
   **lacks** the AIDL `vendor.lineage.livedisplay` (10 interfaces, incl.
   `ISunlightEnhancement`) and `vendor.lineage.touch` (6 interfaces) blocks that
   the LineageOS copy declares. Patch 0003 swaps in the PixelOS file.

**Reproduce.**
```bash
tar tzf <interfaces tarball>@f5689956 | grep livedisplay/aidl   # nothing
tar tzf <interfaces tarball>@3466aa53 | grep livedisplay/aidl   # Android.bp + aidl_api/
diff <(curl -s .../vendor_lineage/lineage-22.2/config/device_framework_matrix.xml) \
     vendor/aosp/config/device_framework_matrix.xml
```

**Suggested fix.** Ship the AIDL interface fragment with the device instead of
editing `vendor/aosp`: the HAL already declares itself via
`vintf_fragments: ["vendor.lineage.livedisplay-service.xiaomi_sdm845.xml"]`
in its `Android.bp`, which is the device-side, upstream-safe way to declare a
HAL. If VINTF checking still fails after a real build, add the missing
`<hal format="aidl">` blocks to a device-local framework matrix and list it in
`DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE` — do not patch `vendor/aosp`.

**Verification duty.** The first build that gets past `soong_build` must be
checked for VINTF compatibility errors mentioning `vendor.lineage.livedisplay`.

---

## B-08 — Camera is the highest-risk subsystem on a PixelOS base

**Severity:** S2 · **Status:** OPEN (cannot be resolved statically)

**Evidence.** 91 camera-related blob lines; the HAL depends on CAF media/display
branches that PixelOS swaps for its own `frameworks_av` fork; ArcSoft nodes need
`remote_handle_*` symbol-version stripping; two Soong-visible shims
(`libpiex_shim`) come from `hardware/lineage/compat`.

**Reproduce.** `grep -c camera device/xiaomi/equuleus/proprietary-files.txt` → 91.

**Suggested fix.** After a successful build, camera triage order:
`logcat -b all | grep -iE 'camx|chi|mm-camera|provider'`, then verify
`/vendor/lib64/camera/components/` exists and `libmmcamera_faceproc.so` passes
`readelf -d`. If the provider fails to start, it is almost always a missing
ArcSoft/`libcdsprpc` dependency, not a PixelOS framework issue.

---

## B-09 — Build fingerprint is an Android 8.1 MIUI value

**Severity:** S3 · **Status:** ACCEPTED (deliberate)

**Evidence.** `aosp_equuleus.mk` sets
`BuildFingerprint=Xiaomi/equuleus/equuleus:8.1.0/OPM1.171019.026/V9.6.6.0.OECCNFD`.
That is inherited from the LineageOS tree and matches the MIUI blob generation,
not Android 15.

**Suggested fix.** Keep it. Changing the fingerprint without matching blobs
breaks Play Integrity *and* can break camera/modem features that key off it.
If a "Pixel-like" fingerprint is wanted, that is a separate, deliberate
decision with its own test matrix.

---

## B-10 — Recovery/AVB uses the AOSP *test* key, and vbmeta flags verification off

**Severity:** S3 (security) · **Status:** ACCEPTED for prototyping

**Evidence.** `BoardConfigCommon.mk`: `BOARD_AVB_ENABLE := true`,
`BOARD_AVB_RECOVERY_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem`,
`BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --set_hashtree_disabled_flag` and
`--flags 2`. `external/avb` is present in PixelOS fifteen at
`android-15.0.0_r32` via `LineageOS/android_external_avb` (the key file returns
HTTP 200).

**Suggested fix.** For personal use, acceptable. For anything distributed,
generate real keys and document the rollback index. Never flash someone else's
build signed with a public test key.

---

## B-11 — No device-specific SELinux policy for the NFC / secure-element services

**Severity:** S2 (runtime only) · **Status:** OPEN · **Owner:** device testing

**Evidence.** `grep -rn 'nfc\|secure_element' device/xiaomi/sdm845-common/sepolicy/`
returns **nothing**, while `device.mk` adds
`android.hardware.nfc-service.nxp` and `proprietary-files.txt` ships
`vendor.qti.secure_element@1.0-service`. No `file_contexts` entry for either
binary exists in the device tree.

**Reproduce.**
```bash
grep -rn 'nfc' device/xiaomi/sdm845-common/sepolicy/ ; echo "rc=$?"   # rc=1
```

**Suggested fix.** First attempt: do nothing — AOSP/Lineage base policy may
already attribute both services correctly, which is presumably how LineageOS
ships it. If NFC turns itself off at boot, capture
`adb logcat -b all | grep -i avc` and add the minimal `.te` +
`file_contexts` files. Do not "fix" this by disabling SELinux or by marking a
domain permissive; the scripts and this repository contain no such shortcut by
design.

---

## B-12 — `git-repo` does not read `revision_lock.xml`; a plain sync is not reproducible

**Severity:** S3 (supply chain) · **Status:** MITIGATED

**Evidence.** Read `GerritCodeReview/git-repo`: `manifest_xml.py`,
`subcmds/init.py`, `subcmds/sync.py` contain no reference to
`revision_lock`. `docs/manifest-format.md` mentions "revision locked manifests"
only in the context of `-c` and manifest selection, and `repo init -m <file>` is
the only selector. Therefore PixelOS' 1,092-entry lock file is inert unless
explicitly selected.

**Reproduce.** `grep -rn revision_lock <git-repo checkout>` → no code hits.

**Suggested fix.** Already applied: `.repo/local_manifests/equuleus.xml` pins
the four device-side repositories to full SHAs, plus one `<extend-project>` for
the interfaces repair. The remaining ~1,090 platform projects still float on
branch heads during a plain sync. For a fully reproducible build, run
`repo init -m revision_lock.xml` (after copying it next to `default.xml`) and
then apply this local manifest; `sync.sh` records the manifest HEAD it used.

---

## B-13 — Kernel toolchain default is `clang-r536225`

**Severity:** S3 · **Status:** INFO

**Evidence.** `vendor/aosp/config/BoardConfigKernel.mk:112`:
`KERNEL_CLANG_VERSION := clang-r536225` unless
`TARGET_KERNEL_CLANG_VERSION` is set. The device tree does not set it. Linux
4.9 needs a clang that still supports `-mno-fp-ret-in-387`-era flags;
r536225 is the version LineageOS' own builds use, so this should hold, but it
was **not** exercised.

**Suggested fix.** If the kernel build fails with unknown clang flags, set
`TARGET_KERNEL_CLANG_VERSION := <older>` in `BoardConfigCommon.mk`. Do not
switch to GCC wholesale.

---

## B-14 — `vendor/gms` is a HARD dependency, and upstream points it at a repo with no `fifteen` branch

**Severity:** S1 if unfixed (nothing configures) · **Status:** MITIGATED by patch 0005 + local-manifest override · **Owner:** verified below

### B-14.1 — GMS is unconditional, not optional (correcting an earlier error)

An earlier revision of this document claimed the `aosp_`-prefixed product was
"unaffected by GMS". **That was wrong.** The inheritance chain was read file by
file in `PixelOS-AOSP/vendor_aosp@2887d1b7`:

```
device/xiaomi/equuleus/aosp_equuleus.mk
  -> vendor/aosp/config/common_full_phone.mk
       -> vendor/aosp/config/common_mobile_full.mk
            -> vendor/aosp/config/common_mobile.mk
                 -> vendor/aosp/config/common.mk
                      line 5: $(call inherit-product, vendor/gms/products/gms.mk)
```

`vendor/aosp/config/common.mk:5` uses `inherit-product`, **not**
`inherit-product-if-exists`. There is no conditional guard, no
`PRODUCT_NO_GMS`-style switch. GMS is therefore a hard configure-time
dependency of `aosp_equuleus`, exactly as it is for every PixelOS product.

**Reproduce.**
```bash
cd vendor/aosp && sed -n '1,12p' config/common.mk
grep -n "inherit-product" config/common_full_phone.mk config/common_mobile_full.mk \
                           config/common_mobile.mk
```

### B-14.2 — the repository the manifest names has no `fifteen` branch

`snippets/custom.xml` declares 20 projects: 19 on `remote="PixelOS"`
(`https://github.com/PixelOS-AOSP`) and **1** on `remote="PixelOS-Gitlab"`
(`https://gitlab.com/PixelOS-AOSP`), namely:

```xml
<project path="vendor/gms" name="vendor_gms" clone-depth="1" remote="PixelOS-Gitlab" />
```

The remote carries `revision="refs/heads/fifteen"`, so this resolves to
`https://gitlab.com/PixelOS-AOSP/vendor_gms`. Observed refs:

| Repository | Branches | Verdict |
| --- | --- | --- |
| `PixelOS-AOSP/vendor_gms` | **`sixteen` only** (`68298e26d926ef6cee83822d5c01e1792dd32bc6`) | ✗ cannot check out at `fifteen` |
| `PixelOS-AOSP/vendor_gms-15` | **`fifteen`** + `sixteen`, `fifteen` = `ffe5c52d947eec784a07124dfb72e95840e8f3c7` | ✓ the fifteen-compatible repo |

**Reproduce.**
```bash
git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms
#   refs/heads/sixteen
git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms-15
#   refs/heads/fifteen   ffe5c52d947eec784a07124dfb72e95840e8f3c7
#   refs/heads/sixteen
```

### B-14.3 — the fix, and the evidence it is the right repo

Two coordinated changes, both in this package:

1. **`patches/0005-manifest-gms-repo.patch`** — edits
   `snippets/custom.xml` in the manifest repository so
   `vendor/gms` names `vendor_gms-15` at the pinned SHA. Verified with
   `git apply --check` against a pristine clone of
   `PixelOS-AOSP/manifest@0334d5e4`.
2. **`.repo/local_manifests/equuleus.xml`** — performs the same repoint without
   touching upstream files, using the supported repo idiom:

   ```xml
   <remove-project name="vendor_gms" />
   <project path="vendor/gms" name="vendor_gms-15"
            revision="ffe5c52d947eec784a07124dfb72e95840e8f3c7"
            remote="PixelOS-Gitlab" clone-depth="1" />
   ```

   A `<remote name="PixelOS-Gitlab">` declaration was added with attributes
   copied **verbatim** from `snippets/custom.xml`
   (`fetch="https://gitlab.com/PixelOS-AOSP"`,
   `revision="refs/heads/fifteen"`), because git-repo raises
   `remote … already exists with different attributes` otherwise.

**Why `vendor_gms-15` is the fifteen-compatible source, not a guess.** A
metadata clone at the pinned SHA was inspected:

| Check | Result |
| --- | --- |
| `HEAD` | `ffe5c52d947eec784a07124dfb72e95840e8f3c7` (branch `fifteen`) |
| HEAD subject | `gms: rro-utils: Move removal of empty xmls to beautify_rro` |
| `products/gms.mk` present | **yes** — this is the exact file `common.mk:5` inherits |
| `products/board.mk` present | yes |
| also present | `proprietary-files.txt`, `proprietary-files_cellular.txt`, `common/`, `rro-utils/`, `rro_overlay/`, `overlay-template.txt`, `extract-files.sh`, `setup-makefiles.sh` |
| `gms.mk` content sanity | sets `ro.config.notification_sound`, `ro.com.google.ime.*`, `ro.opa.eligible_device=true`, and adds `GoogleSettingsOverlay` to `PRODUCT_PACKAGES` — i.e. a real GMS product fragment, not a stub |

### B-14.4 — what was explicitly NOT done

* **Android 16 GMS was not substituted.** `vendor_gms`'s `sixteen` branch and
  `vendor_gms-15`'s `sixteen` branch were both rejected. Mixing a sixteen GMS
  payload into a fifteen framework is exactly the "unverified change" the task
  forbids.
* **Deleting `vendor/gms` was not treated as a fix.** With
  `common.mk:5` being an unconditional `inherit-product`, removing the project
  converts a sync error into a *configure* error
  (`build/make/core/product.mk` cannot include a missing file). It would not
  make anything buildable, so it is not offered as a remedy.

### B-14.5 — residual risk (still must be verified by a real build)

The repoint makes the **source available**; it does not prove the tree
compiles. Open items:

* `vendor_gms-15@ffe5c52d` is a repository *name* convention (`-15`); it is
  strong evidence but not a guarantee that every APK inside it matches this
  device's `VENDOR_SECURITY_PATCH := 2020-12-01`. First `repo sync` + configure
  will show missing-module errors if not.
* GMS brings `PRODUCT_PACKAGES` entries that increase `system`/`product` usage
  inside a 4.81 GiB super partition — see B-06.
* Nothing here says the resulting ROM passes Play Integrity; that is a separate,
  unverifiable-without-device question.

**Reproduce the whole finding:**
```bash
sed -n '1,10p' vendor/aosp/config/common.mk           # unconditional inherit
git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms      # sixteen only
git ls-remote --heads https://gitlab.com/PixelOS-AOSP/vendor_gms-15   # fifteen present
git -C clones/vendor-gms-15 rev-parse HEAD            # ffe5c52d…
git -C clones/vendor-gms-15 cat-file -e HEAD:products/gms.mk && echo present
python3 scripts/verify_deliverables.py | grep 'P0-1'  # automated re-check
```

---

---

## B-15 — Two GMS override mechanisms must never be combined

**Severity:** S1 if violated (nothing syncs) · **Status:** CLOSED (fixed + guarded) · **Found by:** independent review, round 5

**The defect.** `vendor/gms` can be repointed to the fifteen-compatible
repository in exactly two ways:

1. `.repo/local_manifests/equuleus.xml` — `<remove-project name="vendor_gms"/>`
   then re-add `vendor_gms-15`, installed **before** `repo sync`;
2. `patches/0005-manifest-gms-repo.patch` — rewrites the upstream
   `snippets/custom.xml` in place.

The previous `sync.sh` did **both**: it installed the local manifest *and* ran
`apply_patch .repo/manifests 0005` after the sync. That leaves the local
manifest's `<remove-project>` pointing at a project that no longer exists.

**Evidence — from the real git-repo parser, not an emulation.**

```
$ python scripts/verify_manifest_parse.py --repo-src <git-repo> --manifests <manifest clone>

CASE 2  REGRESSION: local manifest AND patch 0005 both applied
  [PASS] real git-repo rejected it as predicted:
         ManifestParseError: remove-project element specifies non-existent
         project: <remove-project name="vendor_gms"/>
```

`manifest_xml.py` states the rule directly:

```python
if not removed_project and not XmlBool(node, "optional", False):
    raise error.ManifestParseError(
        "remove-project element specifies non-existent project: %s" % node.toxml())
```

**Reproduce.**
```bash
python scripts/verify_manifest_parse.py     --repo-src /path/to/git-repo-source     --manifests /path/to/PixelOS-AOSP/manifest@fifteen
# CASE 1 must pass (1099 projects, vendor/gms -> vendor_gms-15 @ ffe5c52d…)
# CASE 2 must raise ManifestParseError
```

**Fix (adopted the review's option 1).**

* the local manifest remains the single override mechanism;
* `sync.sh` no longer applies 0005 at all;
* `sync.sh` now *refuses to run* if it detects 0005 already applied
  (`git apply --reverse --check`), with an explicit message;
* `patches/0005` is retained in `patches/` as a documentation artefact for the
  alternative flow, and is excluded from the build path;
* the acceptance suite fails if both mechanisms are ever enabled together.

**Regression guard.** Check `GMS overrides are mutually exclusive (P0-2)` plus
mutation seed *"0005 is applied again on top of the local override"*, which
must and does turn the check red.

**Residual risk.** The fix makes exactly one mechanism active. It does not prove
that `vendor_gms-15@ffe5c52d` is the right GMS payload for this device — that
still needs a real `repo sync` + configuration.

---

---

## B-16 — `verify_blobs.py` reported success on a SONAME mismatch

**Severity:** S1 (silent false pass) · **Status:** CLOSED · **Found by:** independent review, round 6

**The defect.** The verifier collected a `soname_suspect` record when an
installed library's `DT_SONAME` did not match its installed basename — the exact
signature of a `FIX_SONAME` that never ran — but never folded that into the exit
status. Only *missing files* could fail the run. Pinned hashes were merely
counted (`info["hashed"] += 1`), never computed.

A blob tree could therefore be broken in the two most important ways
(unpatched SONAME, wrong content) and still be reported as verified.

**Reproduce (before the fix).**
```bash
python scripts/verify_blobs.py <tree-with-wrong-soname>
# printed "1 with a non-matching DT_SONAME" ... then
# RESULT: blob tree consistent ...      exit 0
```

**Fix.**

* SONAME mismatch, unreadable ELF, missing `.dynamic`, and non-ELF with
  `FIX_SONAME` are all **FAIL → exit 1**.
* Hashes are actually computed (`sha1`), following
  `extract_utils/module.py::process_pinned_file`:
  `hash` pins the **pre-fixup** bytes, `fixup_hash` the **post-fixup** bytes.
  A fixup hash declared with no fixup function is `BAD_FIXUP` (FAIL).
* A pre-fixup hash that cannot be re-derived from the installed file is
  **UNVERIFIABLE → exit 3**, never success. `--strict` promotes that to 1.
* `build.sh` runs with `--strict` and dies on 1, 3 and 2, reading the status
  inside `if`/`else` because `set -e` makes a bare `RC=$?` unreachable.

**Evidence.**
```
$ python scripts/test_verify_blobs.py
  [PASS] wrong SONAME   rc=1        <- the reported bug: was rc=0
  ... 9/9 cases behaved as required
```
`scripts/verify_deliverables.py` runs that suite on every invocation and asserts
all four required cases (missing / wrong SONAME / wrong hash / correct) appear,
plus five hash-semantics cases.

**Residual risk.** The verifier still cannot prove a blob came from the declared
firmware version unless the list pins a hash, and it cannot prove the blob runs.
Those remain B-01/B-08.

---

---

## B-17 — Build could report a stale or foreign artifact as this run's result

**Severity:** S1 (false success) · **Status:** CLOSED · **Found by:** independent review, round 7

**The defect.** `build.sh` verified artifacts by asking whether a
`PixelOS_*.zip` *existed*. Three ways that reports success wrongly:

1. a zip left over from a previous attempt satisfies it (no freshness check);
2. `ROM_ZIPS[0]` came from `sort` by **filename**, so an older `PixelOS_aaa.zip`
   outranked a newer `PixelOS_zzz.zip`;
3. the device assertion was a `[WARN]`, so a zip asserting `dipper` — which
   would flash the wrong sdm845 phone — still exited 0.

**Reproduce (before the fix).**
```bash
python scripts/test_build_artifacts.py
# [FAIL] stale zip only -> reject          exit=0 accepted=True
# [FAIL] fresh zip asserting different device  exit=0 accepted=True
```

**Fix.** Build start time is recorded before `mka`; the gate now requires the
zip to be newer than that, picks the newest by **mtime**, runs `unzip -t`, and
requires a real `pre-device=equuleus` (or a legacy `assert(...)`), with exit 3
if the assertion is missing, wrong, or unreadable. `recovery.img` must be
present and fresh.

**Evidence.**
```
$ python scripts/test_build_artifacts.py
all 8 cases behaved as required
```
Covers: stale-only, fresh-good, wrong device, no assertion, corrupt archive,
missing recovery, stale-sorts-first, legacy assert.

**Residual risk.** The gate proves the *artifacts are consistent with this run
and this device*. It says nothing about whether the ROM boots — see B-01, B-08.

---

## B-18 — Documentation claimed a patch count the scripts do not perform

**Severity:** S2 (misleading docs) · **Status:** CLOSED · **Found by:** independent review, round 7

**The defect.** At the time, `sync.sh` applied only the first four device
patches, while `CLOUD_READINESS.md` and the generated `REPRODUCE.md` claimed
one more than were applied. (Round 12 later raised the real count to 7, and
the check now asserts the current number rather than a literal.) A reader following
the docs would look for a fifth applied patch that is deliberately never
applied (0005 is archived).

**Why the existing check missed it.** The round-6 check
`GMS/0005 policy documented uniformly` searched for the *word* "0005" and for
phrases like "archived". It never compared a **number** against the actual
`apply_patch` invocations, so a stale count passed.

**Fix.** New check `docs match the real patch count (P2)`:

1. counts the non-0005 `apply_patch` lines in `sync.sh` (currently 4);
2. scans every shipped document for `<n> patches` and rejects any count that
   differs, unless the same line marks it archived/not-applied;
3. also checks the REPRODUCE generator's own text.

**It immediately found a third stale line** in `TEST_REPORT.md` that neither the
reviewer nor I had spotted.

**Evidence.** Mutation *"a document reintroduces a stale patch count"*
turns the check red; 45/45 mutations caught.

**Residual risk.** This checks *counts and the archived marker*. It cannot
detect a document that describes the right number of patches but the wrong
patch *content*; that remains a human review responsibility.

---

---

## B-19 — Artifact gate accepted a stale `recovery.img` and a substring device match

**Severity:** S1 (false success) · **Status:** CLOSED · **Found by:** independent review, round 8

Two independent false-pass paths in `build.sh`, both reproduced.

### B-19.1 — stale recovery accepted

The freshness test ANDed two conditions, one of which compared against
`build/envsetup.sh`. `envsetup.sh` ships with the sync, so any recovery image
built afterwards is "newer than envsetup.sh"; that made the first test false and
the AND short-circuited, accepting an image older than the build start.

```
recovery mtime=1794457016  started=1794458816  envsetup=1794455216
  OLD: ACCEPTED   <-- stale, but newer than envsetup.sh
  NEW: REJECTED
```

**Fix.** Only `BUILD_STARTED_EPOCH` decides. The envsetup comparison is gone.

### B-19.2 — substring device match

The legacy fallback used `grep -qE 'assert.*equuleus'`, which matches
`assert(... == "not_equuleus")`.

```
script: assert(getprop("ro.product.device") == "not_equuleus");
  OLD: ACCEPTED   <-- substring hit
  NEW: REJECTED
```

**Fix.** `META-INF/com/android/metadata` is now mandatory and `pre-device` must
equal `equuleus` exactly. Any legacy assertion is parsed into full device
literals and each compared for equality, so `not_equuleus` and `equuleus_pro`
both fail. A legacy assertion contradicting correct metadata also fails.

### B-19.3 — evidence

```
$ python scripts/test_build_artifacts.py
all 14 cases behaved as required
```

And the reverse check — the same suite against the reconstructed old logic:

```
  [FAIL] fresh zip + STALE recovery -> reject     exit=0 accepted=True expected=reject
  [FAIL] legacy assert not_equuleus -> reject     exit=0 accepted=True expected=reject
  [FAIL] legacy assert equuleus_pro -> reject     exit=0 accepted=True expected=reject
  ... 8 CASE(S) REGRESSED
```

**Residual risk.** The gate proves the artifacts are this run's and this
device's. It says nothing about whether the ROM boots (B-01, B-08).

---

---

## B-20 — IR face unlock: configured, entirely unverified on hardware

**Severity:** S2 (a feature that can look like it works) · **Status:** OPEN (blocked on device testing) · **Owner:** whoever has the phone

### What is done

The device-side configuration exists, as two patches that apply cleanly to the
pinned upstream commits:

| Patch | Effect |
| --- | --- |
| `0007-equuleus-ir-face-unlock-camera-id.patch` | `ro.face.sense_service.camera_id=5` |
| `0008-sdm845-common-ir-face-unlock-aux-camera.patch` | `co.aospa.sense` appended to `vendor.camera.aux.packagelist` |

`ParanoidSense` is already in `PRODUCT_PACKAGES` via
`vendor/aosp/config/common.mk:95`, so nothing needs to be added to the product.
The upstream app source is **not** modified.

`scripts/verify_ir_face_unlock.py` asserts the whole chain statically: the app
still reads the property, the property is set to an aux id, the package is in
the allow-list with the original entries preserved, the OV9282 IR sensor stack
is present, and the ParanoidSense clone is clean. 9/9 pass.

### Why it is still OPEN

**Nothing about this feature has been observed working.** The specific unknowns:

1. **The camera id is inferred, not measured.** Evidence is that OV9282 is the
   monochrome IR part and that Aperture's overlay already ignores aux ids 3 and
   4, so 5 is the next aux slot — plus the established sdm845 adaptation for
   this exact device uses 5. If the real id differs, the feature silently uses
   the RGB front camera.
2. **The RGB fallback is the dangerous case.** With the property missing,
   `CameraUtil` picks `LENS_FACING_FRONT`. That is the S5K3T1 RGB sensor. It
   would appear to work in daylight and fail in the dark, and nobody would
   notice without an explicit dark-room test.
3. **SELinux is untested.** No device-specific rule was added; the app relies on
   standard `priv_app` camera access. A denial would show as the camera failing
   to open.
4. **Megvii matching quality is unknown.** The libraries are prebuilt blobs from
   the ParanoidSense repo; whether they perform acceptably on OV9282 output at
   this device's IR illumination is untested.
5. **Anti-spoofing is unverified.** `config_face_intro_show_require_eyes` is
   `false` in the app's overlay, which suggests eyes-open checking is off. A
   photo may be sufficient. That is a security property, not a cosmetic one.

### How to close it

The test plan is `TEST_REPORT.md` §12. Minimum bar to call it done: enrolment,
daylight unlock, dark-room unlock, reboot persistence, retry behaviour, and a
spoof attempt with a printed photo. Any of those failing keeps this OPEN.

### Explicitly not claimed

A static pass is **not** evidence that IR unlock works. The reporter must not be
written up as "IR face unlock supported" until §12 has real device results.

---

---

## B-21 — Patches 0006-0008 were never applied by a normal sync

**Severity:** S1 (silent wrong build) · **Status:** CLOSED · **Found by:** third-party review, round 12

**The defect.** `sync.sh` applied only 0001-0004. Patches 0006 (NFC firmware
path), 0007 (IR camera id) and 0008 (aux camera allow-list) existed in
`patches/` but no normal build applied them. A build from an unmodified
`sync.sh` would therefore have:

* looked for `vendor/lib/libpn553_fw.so`, which does not exist — the NFC
  firmware actually ships at `lib64/`, so the NFC service would fail to load;
* run ParanoidSense without `ro.face.sense_service.camera_id`, so
  `CameraUtil.getCameraId()` would fall back to `LENS_FACING_FRONT` — the RGB
  selfie camera. Daylight "works", darkness fails.

Both are the kind of defect that produces a build which flashes and boots and
then behaves wrongly in one specific situation.

**Fix.**

* `sync.sh` applies all **7** build patches. Each is idempotent (a second run
  reports "already applied" via a reverse-apply check) and a patch that applies
  neither way aborts the sync.
* After applying, `sync.sh` greps the tree for the three properties those
  patches exist to produce. A hunk landing in the wrong place fails the sync
  instead of silently producing a wrong tree.
* `build-preflight.sh` verifies all 7 patches **and** the resulting content:
  the NFC path, the absence of the stale 32-bit path, the camera id, the aux
  allow-list and all four original package names.
* `build.sh` runs the IR static acceptance before the expensive phase.

**Evidence.**

```
=== PASS 1 (fresh tree) ===   7 × [APPLIED]   rc=0
=== PASS 2 (same tree) ===    7 × [SKIP]      rc=0
```

and, with the patches on disk but the device tree unpatched:

```
[FAIL] device tree reflects the patches (not just the files)
6/10 checks passed
```

**Residual risk.** Applying a patch correctly does not prove the *value* is
right: `camera_id=5` remains NOT VERIFIED ON DEVICE (B-20). No ROM has been
compiled with the corrected pipeline.

---

---

## B-22 — MIUI IR driver analysis: reuse confirmed, hardware still unverified

**Severity:** S3 (informational for the build; does not block) · **Status:** CLOSED for the analysis, **NOT VERIFIED** for runtime

### What was done

The factory firmware `V12.5.2.0.QECCNXM` was obtained, integrity-checked and
compared byte-for-byte against the LineageOS 22.2 extraction.

| Step | Evidence |
| --- | --- |
| gzip integrity | `gzip -t` rc=0 over the full 2.98 GB stream |
| Firmware authenticity | `vendor.img` md5 `d6f41fa1d7303393b5a7760a02064160` **matches Xiaomi's own `md5sum.xml`** |
| Extraction | sparse → raw (`simg2img.py`), then `debugfs`, 2,070 files, read-only |
| Comparison | 18 IR-relevant paths, SHA256 + ELF class/machine/SONAME/NEEDED |

### The result that matters

**The entire OV9282 IR driver stack is byte-identical to LineageOS**, including
the camera HAL, with matching architecture (ELF32/EM_ARM), SONAME and `NEEDED`:

```
com.qti.sensor.ov9282.so              28,288 B   identical
com.qti.sensormodule.ov9282.bin       39,101 B   identical
com.qti.tuned.ofilm_ov9282.bin       379,825 B   identical
lib/hw/camera.qcom.so              3,275,248 B   identical
etc/camera/camxoverridesettings.txt      856 B   identical
```

That is expected in hindsight — LineageOS extracted these blobs from this
firmware — but it is now measured rather than assumed.

### Why no blob patch was emitted

| Candidate gap | Verdict |
| --- | --- |
| `lib64/libmmcamera_faceproc.so` (MIUI-only) | not needed — the camera HAL is 32-bit, so the 32-bit copy is what loads |
| `bin/hw/android.hardware.camera.provider@2.4-service` (MIUI-only) | not needed — PixelOS builds it from `hardware/interfaces` |
| `lib/libmmcamera_faceproc.so` (3 bytes differ) | **must not be replaced** — the difference is LineageOS's own `clear_symbol_version` fixup (`0x03→0x01` at `0x7FE0/0x7FE2/0x7FE4`, exactly 3 symbols). Installing MIUI's raw bytes reverts that fix. |

Emitting a patch here would have been an active regression, which the task
explicitly forbids.

### What did NOT get resolved

**The camera id.** MIUI's `etc/device_features/equuleus.xml` (87 feature entries)
contains **no** explicit IR camera id — MIUI reaches the IR camera through its
own `com.xiaomi.biometric` service, which resolves it internally. So the factory
firmware does **not** corroborate `camera_id=5`.

`ro.face.sense_service.camera_id=5` therefore remains **NOT VERIFIED ON DEVICE**.
The evidence is unchanged from B-20: OV9282 is the only monochrome sensor,
Aperture ignores aux ids 3 and 4, and the established sdm845 adaptation uses 5.

### MIUI components that are deliberately NOT transplantable

MIUI's face stack (`com.miui.face`, `com.xiaomi.biometric`,
`libstfaceunlockoclqcom.so`, `libFaceGrade.so`, SCVE libraries) is MIUI
framework code with an undocumented authentication protocol. It is **not**
declared PixelOS-compatible, and no SELinux rule was loosened to make it load.
ParanoidSense replaces it wholesale.

---

## B-23 — First ROM build not attempted on this host (needs a Linux build machine)

**Severity:** S1 for shipping · **Status:** OPEN · **Blocked on:** hardware/environment, not on knowledge

### The concrete blockage

| Requirement | This host | Needed |
| --- | --- | --- |
| free disk | 16 GiB | ~165 GiB for a full sync |
| `repo` | absent | repo tool |
| `android.googlesource.com` | unreachable | reachable endpoint |

No amount of local work closes this. The sequence to run on a rented Ubuntu
22.04 instance is written out in `FIRST_BUILD_RUNBOOK.md`; an earlier standing
constraint prohibits renting one without the user's decision, so none was
created.

### What is ready

All of it verified statically or by extraction: the 7-patch pipeline, both blob
trees (872 files, `FAIL=0`), the shippable archive with per-file SHA256, the
transfer rehearsal, and the gate chain in `build.sh` (9 steps, abort on any
failure).

### What is honestly unknown

Whether the tree compiles at all. Expect 2-4 failed builds. The `m nothing`
sanity pass in the runbook catches configuration errors without a full compile.

---

## B-24 — `receive` could declare BUILD READY without verifying (P0, CLOSED)

**Severity:** S1 (silent acceptance of unverified blobs) · **Status:** CLOSED · **Found by:** review round 9

**The defect.** The receive step looked for `verify_blobs.py` inside the *target*
tree. When absent it printed `[SKIP]` and still reported
"The tree is ready for scripts/build.sh" with exit 0. A tree with no verification
at all therefore reported ready.

**Fix.** The verifier is always resolved from `${SCRIPT_DIR}` — it belongs to this
project, not the Android tree. Missing verifier, missing device trees, a non-zero
exit, an UNVERIFIABLE exit, or a JSON report showing `FAIL>0` all exit non-zero.
`BUILD READY` prints only after transfer hash + per-file manifest + strict blob
verification all pass. No SKIP path exists.

**Regression cover.** Seven fault-injection cases assert the exit codes
(`scripts/test_first_build_flow.py`), and two acceptance checks read the script to
require the project-relative verifier, the absence of the SKIP fallback, and the
ordering of the `die` guards before `BUILD READY`.

**Lesson worth keeping.** Both original acceptance assertions for this area were
too weak — one matched a flag anywhere in a document, the other matched a variable
name that the broken variant still contained. Both were tightened and re-verified
against the seeds that exposed them.

---

## Summary

| ID | Severity | Status | One-line |
| --- | --- | --- | --- |
| B-01 | S1 | MITIGATED | Both vendor trees extracted from one official LineageOS OTA and strictly verified (862/862); ROM still unbuilt |
| B-02 | S2 | OPEN | `XiaomiParts` is built (SettingsLib module renamed in PixelOS); `XiaomiPocketMode` is dead code |
| B-03 | S3 | ACCEPTED | PixelOS fifteen archived, 2025-06 security level |
| B-04 | S3 | CLOSED | Kernel tree obtained in full; `equuleus.config` fragment proven load-bearing |
| B-05 | S3 | MITIGATED | kernel configs live under `vendor/` in the variable name only |
| B-06 | S2 | OPEN | No product/system reservation in a 4.81 GiB super |
| B-07 | S2 | MITIGATED | interfaces pinned forward; PixelOS matrix is older |
| B-08 | S2 | OPEN | Camera most likely feature failure |
| B-09 | S3 | ACCEPTED | 8.1 MIUI fingerprint retained |
| B-10 | S3 | ACCEPTED | Test AVB key, verification flags off |
| B-11 | S2 | OPEN | No device NFC SELinux policy |
| B-12 | S3 | MITIGATED | revision_lock is not auto-applied; local pins instead |
| B-13 | S3 | INFO | Kernel clang default unexercised |
| B-14 | S1 | MITIGATED | `vendor/gms` is an unconditional dependency; repointed to `vendor_gms-15@ffe5c52d` |
| B-15 | S1 | CLOSED | the two GMS override mechanisms were combined; now mutually exclusive and guarded |
| B-16 | S1 | CLOSED | `verify_blobs.py` exited 0 on a SONAME mismatch; now fails, with fault-injection tests |
| B-17 | S1 | CLOSED | build could report a stale/foreign artifact as success; now freshness+integrity+device enforced |
| B-18 | S2 | CLOSED | docs claimed 5 applied patches where `sync.sh` applies 4; negative test added |
| B-19 | S1 | CLOSED | stale recovery + substring device match both accepted; single marker + exact parse |
| B-20 | S2 | OPEN | IR face unlock configured (camera id 5 + aux allow-list); unverified on hardware |
| B-21 | S1 | CLOSED | patches 0006-0008 were never applied by sync.sh; now 7 patches, with content verification |
| B-22 | S3 | CLOSED (analysis) | MIUI IR blobs byte-identical to LineageOS; no blob patch needed; camera id still NOT VERIFIED ON DEVICE |
| B-23 | S1 | OPEN | first ROM build not attempted: needs ~165 GiB, repo, and Google source access |
| B-24 | S1 | CLOSED | receive could print BUILD READY without running the verifier; now unconditional |

**Nothing here is buildable until B-01 closes.** Everything else is either
already mitigated or requires the first build / first boot to investigate.
