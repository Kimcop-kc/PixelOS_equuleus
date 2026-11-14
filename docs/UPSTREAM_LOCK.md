# UPSTREAM_LOCK — PixelOS fifteen / equuleus

Audit date: **2026-11-12**. Every SHA below was read from the live remote with
`git ls-remote` (not from a wiki or a blog post). Where a file's contents are
relevant, the file was fetched and inspected; the claim is marked **[read]**.
Where only existence was confirmed, it is marked **[exists]**.

Nothing in this document claims a successful build, a successful `repo sync`,
or any device test. See `TEST_REPORT.md` for what was actually executed.

---

## 1. ROM baseline

| Field | Value | Evidence |
| --- | --- | --- |
| Manifest repo | `PixelOS-AOSP/manifest` | [exists] |
| Branch | `fifteen` (Android 15) | [exists] |
| Head commit | `0334d5e468a86ab0aefa6d3a40bc2abd11bf4035` | `git ls-remote` |
| Head subject | `manifest: Add revision_lock.xml` | GitHub API |
| Head date | 2025-06-18T11:36:27Z | GitHub API |
| Archived | **Yes** — read-only, no further security patches | PixelOS announced archival; branch head has not moved since 2025-06-18 |
| License | Apache-2.0 (manifest repo itself) | [read] |

`repo init -u https://github.com/PixelOS-AOSP/manifest.git -b fifteen --git-lfs`,
`lunch aosp_<device>-<release>-<variant>`, `mka bacon`. The README documents
`aosp_target_release` = **bp1a** (April ASB) [read].

**Risk:** this branch is archived on Android 15 / 2025-07 security level.
It is a porting prototype, not a maintained daily-driver base.

### Future branch (research only — do not mix)

| Field | Value |
| --- | --- |
| Repo | `PixelOS-AOSP/android_manifest` |
| Branch | `seventeen` (Android 17) |
| Head commit | `29f6010bcd2bd4742502ea7ccee763c64f02a3c1` |
| Head date | 2026-11-05 |
| Build commands | `breakfast <codename>` + `m pixelos` — **incompatible with fifteen** |

An Android 15 device tree cannot be dropped onto `seventeen`. Nothing in this
deliverable targets it.

---

## 2. Manifest structure of PixelOS fifteen (what the device tree actually sees)

`default.xml` declares 1,033 AOSP projects pinned to
`refs/tags/android-15.0.0_r32`, then includes three snippets:

| Snippet | Content | Count |
| --- | --- | --- |
| `snippets/remove.xml` | `<remove-project>` entries | **127** |
| `snippets/custom.xml` | PixelOS forks of bionic/build/soong/frameworks/… | **20** |
| `snippets/lineage.xml` | LineageOS-shared projects (build helpers, QCOM CAF, Lineage HALs) | **169** |

Arithmetic: `1033 + 20 + 169 − 127 = 1095`. That matches the de-duplicated
project count independently computed by `verify_deliverables.py`
(`no overlap with 1095 upstream project paths`), and no path appears twice.

After applying removals: **1,095 projects**, **no duplicate paths** (verified
by parsing all three files and de-duplicating by `<remove-project name>`).

`revision_lock.xml` is a **flattened lock file**: 1,092 `<extend-project>`
entries with full SHAs. **`repo` does not read it automatically** — verified by
reading `GerritCodeReview/git-repo`: `manifest_xml.py` and `subcmds/*.py`
contain no reference to `revision_lock`; only `repo init -m <file>` selects a
non-default manifest. A plain `repo init -b fifteen` therefore resolves branch
heads, which move. This is why `.repo/local_manifests/equuleus.xml` pins the
four device-side repositories itself, and why the one platform repository that
must differ from the lock file is pinned with `<extend-project>`.

### 2.1 Paths the device tree needs, and what PixelOS provides

| Path needed by the device tree | PixelOS fifteen | Verdict |
| --- | --- | --- |
| `hardware/qcom-caf/common` | `LineageOS/android_hardware_qcom-caf_common` | present |
| `hardware/qcom-caf/sdm845/{audio,display,media}` | `LineageOS/android_hardware_qcom_{audio,display,media}` @ `lineage-22.2-caf-sdm845` | present |
| `hardware/qcom-caf/wlan` | `LineageOS/android_hardware_qcom_wlan` @ `lineage-22.2-caf` | present |
| `device/qcom/sepolicy_vndr` (linkfile) | created by `hardware/qcom-caf/common` linkfile | present |
| `device/qcom/sepolicy_vndr/legacy-um` | `LineageOS/android_device_qcom_sepolicy_vndr` @ `lineage-22.2-legacy-um` | present |
| `device/lineage/sepolicy` | `PixelOS-AOSP/device_lineage_sepolicy` @ `fifteen` | present |
| `hardware/lineage/interfaces` | `LineageOS/android_hardware_lineage_interfaces` | present, **wrong revision** — see §4 |
| `hardware/lineage/compat` | `LineageOS/android_hardware_lineage_compat` | present |
| `hardware/interfaces` | `LineageOS/android_hardware_interfaces` @ `lineage-22.2` | present |
| `external/avb` | `LineageOS/android_external_avb` @ `lineage-22.2` | present (`test/data/testkey_rsa4096.pem` confirmed 200) |
| `tools/extract-utils` | `LineageOS/android_tools_extract-utils` | present |
| `kernel/configs` | `LineageOS/android_kernel_configs` | present |
| `vendor/qcom/opensource/{display,commonsys/display,commonsys-intf/display,dataservices,usb}` | LineageOS forks | present |
| **`vendor/lineage`** | **absent** | replaced by `vendor/aosp` — see §3 |
| **`hardware/xiaomi`** | **absent** | supplied by local manifest |
| **`kernel/xiaomi/sdm845`** | **absent** | supplied by local manifest |
| **`device/xiaomi/*`** | **absent** | supplied by local manifest |
| **`vendor/xiaomi/*`** | **absent** | proprietary blobs — `BLOB_EXTRACTION.md`, **BLOCKED** |

---

## 3. `vendor/lineage` → `vendor/aosp` (the single most important substitution)

`sdm845-common` and `equuleus` referenced four `vendor/lineage` paths. PixelOS
does not ship `vendor_lineage`; it ships `vendor_aosp`
(`PixelOS-AOSP/vendor_aosp` @ `fifteen`, head
`2887d1b7729f38560b1cb4b27317c2bf29f2325b`).

| LineageOS input | PixelOS equivalent | Identical? |
| --- | --- | --- |
| `vendor/lineage/config/common_full_phone.mk` | `vendor/aosp/config/common_full_phone.mk` | **No** — inherits PixelOS' `common_mobile_full.mk` → `common.mk` (GMS, backuptool, pixel-framework) [read] |
| `vendor/lineage/config/BoardConfigReservedSize.mk` | `vendor/aosp/config/BoardConfigReservedSize.mk` | **No** — PixelOS only sets `BOARD_PRODUCTIMAGE_MINIMAL_PARTITION_RESERVED_SIZE` for virtual A/B; LineageOS also reserves ~1.9 GiB for `product` and 90 MiB each for `system`/`system_ext` [read + diffed] |
| `vendor/lineage/config/device_framework_matrix.xml` | `vendor/aosp/config/device_framework_matrix.xml` | **No** — PixelOS' copy is dated 2021-2023 and lacks the AIDL `vendor.lineage.livedisplay` and `vendor.lineage.touch` HAL blocks that the LineageOS copy declares [diffed] |

Consequences are tracked as blockers B-06 and B-07. They are *not* cosmetic:
the reserved-size difference changes how much free space the build has inside a
fixed 4.81 GiB super partition, and the framework-matrix difference changes
which HALs the framework expects to be present.

`vendor/aosp` also appends `include vendor/aosp/config/BoardConfigCustom.mk`
from `build/make/core/config.mk`, which pulls in
`hardware/qcom-caf/common/BoardConfigQcom.mk` when `BOARD_USES_QCOM_HARDWARE`
is true — so `TARGET_USES_FOD_ZPOS := true` reaches the display HAL through
`SOONG_CONFIG_qtidisplay_udfps` even without `vendor/lineage` [read].

---

## 4. Device-side repositories (pinned by this deliverable)

| Path | Repository | Branch | Commit | License |
| --- | --- | --- | --- | --- |
| `device/xiaomi/equuleus` | `LineageOS/android_device_xiaomi_equuleus` | `lineage-22.2` | `db40750f063e86110e20db1455729c0f6621f7da` | Apache-2.0 |
| `device/xiaomi/sdm845-common` | `LineageOS/android_device_xiaomi_sdm845-common` | `lineage-22.2` | `35cf356b095e033e71261b16c7fa319faac12cb3` | Apache-2.0 |
| `kernel/xiaomi/sdm845` | `LineageOS/android_kernel_xiaomi_sdm845` | `lineage-22.2` | `aa8adfe9bf212c6e93238a86980b4024da4f819a` | GPL-2.0 |
| `hardware/xiaomi` | **`PixelOS-AOSP/hardware_xiaomi`** | `fifteen` | `281f97dbac46b75eb7b6a680624e62e807ec0689` | Apache-2.0 |
| `vendor/gms` | **`PixelOS-AOSP/vendor_gms-15`** (GitLab) | `fifteen` | `ffe5c52d947eec784a07124dfb72e95840e8f3c7` | see §4.3 |

All SHAs re-read with `git ls-remote` on 2026-11-12. The equuleus and
sdm845-common trees were also downloaded as tarballs at those exact SHAs and
the patches in `patches/` were verified to apply onto them.

### 4.1 Why `PixelOS-AOSP/hardware_xiaomi` and not the LineageOS fork

Both forks exist; **only one may be checked out at `hardware/xiaomi`**. The
two trees were diffed file-by-file:

* sdm845-common/equuleus consume exactly three things from this repo:
  `//hardware/xiaomi:xiaomifingerprint_headers` (`udfps/Android.bp`),
  `//hardware/xiaomi:libudfps_extension.xiaomi` (`device.mk`, SurfaceFlinger
  `udfps_lib` soong config), and the `hardware/xiaomi` soong namespace.
  All three are **byte-identical** in both forks.
* The PixelOS fork additionally carries Dolby `media.c2` and
  `vendor.xiaomi.hw.touchfeature` entries in
  `vintf/xiaomi_framework_compatibility_matrix.xml`, matching what PixelOS'
  framework matrix expects.
* The LineageOS fork additionally carries `aidl/touch/` and `megvii/`.
  **Nothing in either device tree references them** (grep for `megvii`,
  `HighTouchPollingRate`, `KeyDisabler`, `touchfeature` across both trees
  returns nothing), so choosing the PixelOS fork loses no referenced module.

Chosen: PixelOS fork. Trade-off and residual risk: `DEVICE_AUDIT.md` §4.

### 4.2 Why `hardware/lineage/interfaces` needs an `<extend-project>` override

PixelOS' `revision_lock.xml` pins this repo to
`f568995691b655491d1b3d309f0e6eb96ebeb248`. Tarball listing of that SHA shows
`livedisplay/2.0` and `livedisplay/2.1` (HIDL) but **no `livedisplay/aidl`
directory**. `sdm845-common/livedisplay/Android.bp` links
`vendor.lineage.livedisplay-V1-ndk` and includes the generated header
`aidl/vendor/lineage/livedisplay/BnSunlightEnhancement.h`, both of which only
exist once the AIDL interface is present.

At `lineage-22.2` head `3466aa530ace6de0760c12a68cf81b31e8d3807b`,
`livedisplay/aidl/Android.bp` and `aidl_api/vendor.lineage.livedisplay/1/...`
**are** present (94 entries under `livedisplay/aidl/`). The override pins that
SHA. Because it is an `<extend-project>` on a path PixelOS already owns, it is
compatible with both a plain sync and a revision-locked sync.

Residual risk: PixelOS pinned the older SHA deliberately (their build does not
use the AIDL livedisplay HAL). Using the newer interfaces repo also upgrades
`health`, `light`, `power-libperfmgr` and `touch` module definitions for every
other device in the same tree — irrelevant for a single-device build, but it
means this is a *tree-wide* change, not an equuleus-only one. Tracked as B-07.

### 4.3 Why `vendor/gms` had to be repointed

`vendor/aosp/config/common.mk:5` performs

```
$(call inherit-product, vendor/gms/products/gms.mk)
```

with `inherit-product`, not `inherit-product-if-exists` — so GMS is an
**unconditional** dependency of every product inheriting `common.mk`, including
`aosp_equuleus` via `common_full_phone.mk → common_mobile_full.mk →
common_mobile.mk → common.mk`.

Upstream `snippets/custom.xml` declares that project as
`name="vendor_gms"` on the `PixelOS-Gitlab` remote, which resolves to
`https://gitlab.com/PixelOS-AOSP/vendor_gms`. That repository has **only** a
`sixteen` branch, so `repo sync` cannot check it out at `fifteen`.

`PixelOS-AOSP/vendor_gms-15` is the fifteen-compatible repository: branch
`fifteen` = `ffe5c52d947eec784a07124dfb72e95840e8f3c7`, and at that commit
`products/gms.mk` exists with real GMS product content. Both the manifest patch
(0005) and the local manifest repoint `vendor/gms` to it, pinned to that SHA.
Full analysis: `KNOWN_BLOCKERS.md` B-14.

---

## 5. HAL versions the device tree requires (present in `hardware/interfaces`)

Every directory below was confirmed to return HTTP 200 from
`LineageOS/android_hardware_interfaces@lineage-22.2`:

`graphics/composer/2.3`, `audio/6.0`, `camera/provider/2.4`, `gnss/2.0`,
`keymaster/3.0`, `secure_element/1.0`, `sensors/1.0`, `drm/1.3`,
`soundtrigger/2.2`, `neuralnetworks/1.2`, `tetheroffload/config/1.0`,
`tetheroffload/control/1.1`, `radio/1.4`, `radio/config/1.1`.

The NFC AIDL service `android.hardware.nfc-service.nxp` is defined at
`snxxx/Android.bp:195` of `LineageOS/android_hardware_nxp_nfc@lineage-22.2`
with its `.rc` starting `/vendor/bin/hw/android.hardware.nfc-service.nxp`
[read]. PixelOS fifteen checks out `platform/hardware/nxp/nfc` at
`android-15.0.0_r32`, which is the same AOSP tree.

---

## 6. Kernel

| Field | Value | Evidence |
| --- | --- | --- |
| Repo | `LineageOS/android_kernel_xiaomi_sdm845` | [exists] |
| Commit | `aa8adfe9bf212c6e93238a86980b4024da4f819a` | `git ls-remote` |
| Version | 4.9.337 | `Makefile` [read] |
| Base config | `arch/arm64/configs/vendor/xiaomi/mi845_defconfig` (16,053 B) | [read] |
| Device fragment | `arch/arm64/configs/vendor/xiaomi/equuleus.config` (361 B) | [read] |
| Fragment contents | `CONFIG_BCM_GPS_SPI_DRIVER`, `CONFIG_FINGERPRINT_GOODIX_TA`, `CONFIG_INPUT_PRESS_NDT`, `CONFIG_LEDS_LM3644`, `CONFIG_MACH_XIAOMI_E1S`, `CONFIG_TOUCHSCREEN_ST_FTS_V521`, … | [read] |

`sdm845-common/BoardConfigCommon.mk` sets
`TARGET_KERNEL_CONFIG := vendor/xiaomi/mi845_defconfig`; `equuleus/BoardConfig.mk`
*appends* `vendor/xiaomi/equuleus.config` via `TARGET_KERNEL_CONFIG +=`. PixelOS'
`build/tasks/kernel.mk` treats `TARGET_KERNEL_CONFIG` as a **list**, with the
first entry as base and the rest merged as fragments [read]. The two settings
compose correctly.

Kernel toolchain: PixelOS `config/BoardConfigKernel.mk` defaults
`KERNEL_CLANG_VERSION := clang-r536225` and
`TARGET_KERNEL_CLANG_PATH ?= $(BUILD_TOP)/prebuilts/clang/host/$(HOST_PREBUILT_TAG)/$(KERNEL_CLANG_VERSION)`
[read]. The LineageOS tree for this device does not override it.

**Full tree obtained.** A 174,356,433-byte tarball of this exact commit was
downloaded and extracted, so the tree is no longer an audit gap (B-04 closed).
The fragment is **load-bearing**: `CONFIG_FINGERPRINT_GOODIX_TA`,
`CONFIG_TOUCHSCREEN_ST_FTS_V521` and `CONFIG_MACH_XIAOMI_E1S` appear **only** in
`equuleus.config` and are absent from `mi845_defconfig`. Dropping the fragment
would yield a kernel with no fingerprint TEE interface and no touch driver.

---

## 7. Proprietary blobs (blocked, not stubbed)

| Path | Source declared by the device tree | Status |
| --- | --- | --- |
| `vendor/xiaomi/equuleus` | MIUI **V12.5.2.0.QECCNXM** CN stable (`proprietary-files.txt` line 1) | **BLOCKED — not generated** |
| `vendor/xiaomi/sdm845-common` | beryllium MIUI **V12.0.3.0.QEJMIXM** global stable unless pinned | **BLOCKED — not generated** |

`equuleus/proprietary-files.txt` has 277 lines, `sdm845-common/proprietary-files.txt`
has 724. No binary was created, copied, or fabricated anywhere in this
deliverable. Extraction procedure, version checks and the exact gap list:
`BLOB_EXTRACTION.md`. Severity and current status: `KNOWN_BLOCKERS.md` B-01/B-02.

---

## 8. Licences

| Component | Licence |
| --- | --- |
| PixelOS `manifest`, `vendor_aosp`, `device_lineage_sepolicy`, `hardware_xiaomi` | Apache-2.0 |
| LineageOS device trees, `hardware_xiaomi`, `hardware_lineage_*`, `device_qcom_sepolicy*` | Apache-2.0 |
| `android_kernel_xiaomi_sdm845` | GPL-2.0 |
| AOSP (`android-15.0.0_r32`) | mostly Apache-2.0, mixed (see `NOTICE` files) |
| MIUI proprietary blobs | **not redistributable**; must be extracted from a legally obtained firmware image by the device owner |

This deliverable contains **no** proprietary binaries and **no** credentials.

---

## 9. Real git clones — the pins are commit objects, not copied strings

A tarball proves a tree existed at a URL. Only a **git checkout** proves the SHA
is a real commit object with reachable history. Both were done.

Nine repositories were cloned with `git clone` and their `HEAD` compared
character-by-character against the pins above:

| Clone (in `clones/`) | Branch | HEAD = pin? | History |
| --- | --- | --- | --- |
| `device-xiaomi-equuleus` | `lineage-22.2` | ✅ `db40750f…` | 167 commits |
| `device-xiaomi-sdm845-common` | `lineage-22.2` | ✅ `35cf356b…` | 1,098 commits |
| `hardware-xiaomi-pixelos` | `fifteen` | ✅ `281f97db…` | 252 commits |
| `hardware-lineage-interfaces` | `lineage-22.2` | ✅ `3466aa53…` | 464 commits |
| `pixelos-manifest` | `fifteen` | ✅ `0334d5e4…` | 663 commits |
| `vendor-aosp-pixelos` | `fifteen` | ✅ `2887d1b7…` | 4,556 commits |
| `hw-qcom-caf-common` | `lineage-22.2` | ✅ `cd600d76…` | 110 commits |
| `device-lineage-sepolicy-pixelos` | `fifteen` | ✅ `b6b52ebb…` | 323 commits |
| `vendor-gms-15` | `fifteen` | ✅ `ffe5c52d…` | metadata clone (`--filter=blob:none`) |

For every one of these, `git cat-file -e <sha>^{commit}` succeeds — i.e. the
object is present and is a commit, not merely a string that appeared in a URL.

Provenance is recorded in [`clones/CLONE_MANIFEST.tsv`](clones/CLONE_MANIFEST.tsv),
and `scripts/verify_deliverables.py` re-checks all of it on every run (check
"pins verified against real git clones").

**Patches apply to the real clones, not just to extracted tarballs.** All four
patches were re-verified with `git apply --check` **and** `git apply` against
fresh copies of `clones/device-xiaomi-equuleus` and
`clones/device-xiaomi-sdm845-common`; the resulting `git status` showed exactly
the intended modifications.

### 9.1 Two repositories resisted cloning

`LineageOS/android` (the LineageOS manifest, which is the repo whose tarball
extracts to `android-lineage-22.2/`) and
`LineageOS/android_kernel_xiaomi_sdm845` both failed repeated `git clone`
attempts with `Failed to connect to github.com:443` / `Recv failure: Connection
was reset`. Both were instead verified as existing at the pinned revision:

* kernel: `codeload.github.com/.../tar.gz/aa8adfe9…` → **HTTP 200**, and the
  174 MB tree was downloaded and inspected (see §6).
* LineageOS manifest: `codeload.github.com/LineageOS/android/tar.gz/refs/heads/lineage-22.2`
  → **HTTP 200**; the fetched `default.xml` and `snippets/lineage.xml` are
  **byte-identical** to the snapshot in `src/lineage-manifest/`, which
  independently confirms the earlier snapshot was not tampered with.

These two are therefore verified by content hash and by tarball availability,
not by a working git checkout. That distinction is recorded rather than hidden.

---

## 10. Everything in this lock is reproducible with

```bash
# git-protocol check (works when GitHub is reachable)
git ls-remote https://github.com/LineageOS/android_device_xiaomi_equuleus refs/heads/lineage-22.2

# full-clone check (what was actually done for the eight repos in §9)
git clone --branch lineage-22.2 https://github.com/LineageOS/android_device_xiaomi_equuleus
git -C android_device_xiaomi_equuleus rev-parse HEAD        # db40750f063e86110e20db1455729c0f6621f7da
git -C android_device_xiaomi_equuleus cat-file -e HEAD^{commit}   # must exit 0

# tarball fallback when git is blocked
curl -sSLo k.tgz https://codeload.github.com/LineageOS/android_kernel_xiaomi_sdm845/tar.gz/aa8adfe9bf212c6e93238a86980b4024da4f819a
```

See `logs/sha_table.txt` for the original `git ls-remote` captures and
`clones/CLONE_MANIFEST.tsv` for the clone results.

