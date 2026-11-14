# DEVICE_AUDIT — Xiaomi Mi 8 Pro (`equuleus`)

Audit date: 2026-11-12. Scope: **static source analysis only.** No build was
produced, no image was flashed, no phone was touched.

> **Read this first.** Everything below is "the code/config for X exists and is
> wired like this". That is a completely different claim from "X works on the
> device". Each section therefore ends with an explicit *verification status*
> that is **NOT VERIFIED ON DEVICE** unless stated otherwise. No item in this
> document has been verified on hardware.

---

## 0. Device facts recovered from the trees

| Property | Value | Where |
| --- | --- | --- |
| Codename | `equuleus` | `BoardConfig.mk`: `TARGET_OTA_ASSERT_DEVICE := equuleus` |
| SoC | Qualcomm SDM845 | `BoardConfigCommon.mk`: `TARGET_BOARD_PLATFORM := sdm845` |
| CPU | 4× Kryo 385 Gold + 4× Silver | `TARGET_CPU_VARIANT_RUNTIME := kryo385` |
| Display | 1080×2248, 440 dpi | `TARGET_SCREEN_{WIDTH,HEIGHT}`, `TARGET_SCREEN_DENSITY := 440` |
| A/B | **no** | `AB_OTA_UPDATER := false` |
| Dynamic partitions | **yes**, `qti_dynamic_partitions` | see §5 |
| Encryption | `fileencryption=ice` on `/data` | `init/fstab.qcom` |
| Kernel | 4.9.337, `mi845_defconfig` + `equuleus.config` | see `UPSTREAM_LOCK.md` §6 |
| Android baseline | shipped 8.1 (MIUI 9.6); fingerprint override still 8.1 | `PRODUCT_BUILD_PROP_OVERRIDES` |

The stock fingerprint in `aosp_equuleus.mk` is
`Xiaomi/equuleus/equuleus:8.1.0/OPM1.171019.026/V9.6.6.0.OECCNFD:user/release-keys`.
That is not a PixelOS 15 fingerprint; it is kept because it matches the
`vendor/xiaomi` blob set declared in `proprietary-files.txt`
(`V12.5.2.0.QECCNXM`). Mismatch consequences: `KNOWN_BLOCKERS.md` B-09.

---

## 1. Fingerprint on display (FOD) — Goodix GF9118, optical, under AMOLED

### 1.1 HAL type

Two HIDL HALs, both **vendor** partition, both declared in
`equuleus/manifest.xml`:

| HAL | Version | Interfaces | Package |
| --- | --- | --- | --- |
| `vendor.goodix.hardware.biometrics.fingerprint` | 2.1 | `IGoodixFingerprintDaemon`, `…Ext`, `…Fido`, `…Hbd` | `hardware/xiaomi/interfaces/goodix/hardware/biometrics/fingerprint/2.1` |
| `vendor.goodix.hardware.fingerprintextension` | 1.0 | `IGoodixBiometricsFingerprint` | `hardware/xiaomi/interfaces/goodix/hardware/fingerprintextension/1.0` |

Additionally `sdm845-common/manifest.xml` declares the standard
`com.fingerprints.extension@1.0` interfaces (`IFingerprintAuthenticator`,
`…Calibration`, `…Engineering`, `…Navigation`, `…Recalibration`,
`…SenseTouch`, `…SensorTest`) — all seven exist as `.hal` files in the same
tree, so the declaration is consistent with the source.

### 1.2 Service registration

There are **two** fingerprint service families in `hardware_xiaomi`:

* HIDL 2.3: `hidl/biometrics/fingerprint/Android.bp` →
  `android.hardware.biometrics.fingerprint@2.3-service.xiaomi`
* AIDL: `aidl/fingerprint/Android.bp` →
  `android.hardware.biometrics.fingerprint-service.xiaomi`

`sdm845-common/sdm845.mk:148-151` selects the **AIDL** service:

```
# Fingerprint
PRODUCT_PACKAGES += \
    android.hardware.biometrics.fingerprint-service.xiaomi
```

The **HIDL 2.3** service (`hidl/biometrics/fingerprint/Android.bp`) is *not*
added by either device tree. The AIDL service statically links
`libudfpshandlerfactory`, which is where the vendor-specific UDFPS tap handling
lives; `libudfpshandler` itself is added by `equuleus/device.mk:72`.

### 1.3 UDFPS framework integration

| Piece | File | Note |
| --- | --- | --- |
| `TARGET_USES_FOD_ZPOS := true` | `equuleus/BoardConfig.mk:35` | consumed by `hardware/qcom-caf/common/BoardConfigQcom.mk:190` → `SOONG_CONFIG_qtidisplay_udfps := true` (read at the PixelOS-pinned SHA `7d3f8e2c…`) |
| Display HAL Z-order handling | `hardware/qcom-caf/sdm845/display` `sdm/libs/{core,hwc2}` `-DFOD_ZPOS` | the flag gates real `setLayerZOrder` behaviour in `hwc_layers.cpp`/`hw_device_drm.cpp` (read in the sdm845 branch) |
| SurfaceFlinger extension | `//hardware/xiaomi:libudfps_extension.xiaomi` via `soong_config_set,surfaceflinger,udfps_lib` | PixelOS' `frameworks_native` (CompositionEngine `Android.bp:98-105`) honours the `surfaceflinger:udfps_lib` variable and defaults to `surfaceflinger_udfps_lib` when unset (verified in PixelOS fork) |
| Handler | `sdm845-common/udfps/UdfpsHandler.cpp` → `libudfpshandler` | referenced by `PRODUCT_PACKAGES` in `equuleus/device.mk` |
| Sensor HAL | `//hardware/xiaomi:sensors.udfps` | present in the **PixelOS** fork (`sensors/v1/Android.bp`) |
| Colour | `overlay-lineage/frameworks/base/packages/SystemUI/…/config.xml` → `config_udfpsColor #00ffff` | target exists: PixelOS defines it in `SystemUI/res/values/custom_config.xml` |
| Enroll UI radius | `overlay/packages/apps/Settings/…/config.xml` → `config_udfpsEnrollProgressBar = 87` | target exists in PixelOS `packages_apps_Settings/fifteen` (`res/values/config.xml:756`) |
| Coordinates | `vendor.prop`: `persist.vendor.fingerprint.sensor_location=540|1727|87` | `system_ext.prop`: `…udfps.location.X_Y=453,1640`, `…size.width_height=173,173` |
| Sunlight/HBM boost | `sdm845-common/livedisplay/SunlightEnhancement.cpp` | writes `disp_param` values `0x20000` (HBM+FOD on), `0xE0000` (HBM+FOD off), `0x10000`/`0xF0000` (HBM on/off without FOD) and reads `hbm_status`; gated on `ro.product.device` — `hasFingerprintOnDisplay()` is true only for `{equuleus, ursa}` (`SunlightEnhancement.cpp:28-39`) |

### 1.4 Blobs

```
vendor/lib64/hw/fingerprint.goodix_fod.so:vendor/lib64/hw/fingerprint.goodix_fod.sdm845.so;FIX_SONAME
vendor/lib64/libgf_ca_gf9118.so
vendor/lib64/libgf_hal_gf9118.so
vendor/lib64/libgoodixhwfingerprint_gf9118.so
```

`FIX_SONAME` means `extract-utils` must rewrite the `DT_SONAME` entry so the
loader finds the renamed `fingerprint.goodix_fod.sdm845.so`. If the fixup is
skipped the HAL loads and then fails to resolve — a classic "enrolled prints
disappear after reboot" symptom. The extraction tooling handles this
automatically; hand-copying the blob does not.

Kernel side: `CONFIG_FINGERPRINT_GOODIX_TA=y` in `equuleus.config`, i.e. the
TrustZone app interface is compiled in. Without that config the vendor HAL
cannot talk to the TEE and FOD silently degrades to nothing.

### 1.5 SELinux

`sdm845-common/sepolicy/vendor/hal_fingerprint_default.te` exists; the AIDL
service runs as `hal_fingerprint_default`. No `permissive` domain and no
SELinux-disabling command anywhere in the trees (grep-verified: the strings
`setenforce`, `permissive` and `androidboot.selinux=` do not appear in any
`.te`, `.rc` or `.mk` file of either device tree).

### 1.6 Verification status

| Claim | Status |
| --- | --- |
| HAL declarations present and self-consistent | **static: confirmed** |
| AIDL service selected by the product makefiles | **static: confirmed** |
| `TARGET_USES_FOD_ZPOS` reaches the display HAL | **static: confirmed** (two-hop read) |
| SurfaceFlinger accepts `udfps_lib` | **static: confirmed** in PixelOS fork |
| Overlay targets exist in PixelOS | **static: confirmed** |
| Blobs obtainable and complete | **BLOCKED** — not extracted (`BLOB_EXTRACTION.md`) |
| FOD enrols and unlocks on the device | **NOT VERIFIED ON DEVICE** |

---

## 2. Camera — dual 12 MP (IMX363 + S5K3M3), ArcSoft/MIUI post-processing

### 2.1 HAL type and registration

`sdm845-common/sdm845.mk`:

```
PRODUCT_PACKAGES += \
    android.hardware.camera.provider@2.4-impl:32 \
    android.hardware.camera.provider@2.4-service
```

`sdm845-common/manifest.xml` declares `android.hardware.camera.provider` (2.4).
`hardware/interfaces` at `lineage-22.2` contains `camera/provider/2.4`
(verified 200). So the HIDL provider matches the declared interface version.

`TARGET_USES_ION := true` is set, and the device relies on the CAF display/media
stack (`hardware/qcom-caf/sdm845/{display,media}`).

### 2.2 Camera blobs — the largest and riskiest block

91 lines of `equuleus/proprietary-files.txt` are camera-related. They fall into
four categories, and only the first is a plain blob:

1. **QTI/CAF camera stack** — `vendor/lib/libmmcamera_*.so`,
   `vendor/lib64/camera/components/*`, `vendor/bin/remosaic_daemon`.
2. **ArcSoft proprietary nodes** — `com.arcsoft.node.{capturebokeh,capturefusion,hdr,
   hdrchecker,realtimebokeh,skinbeautifier,smoothtransition,superlowlight}.so`
   plus `libarcsoft_dualcam_refocus_{front,rear_t,rear_w}.so`. These are the
   portrait/beauty features. They reference `remote_handle_{open,invoke,close}`
   from `libcdsprpc`, and `extract-files.py` therefore applies
   `.clear_symbol_version(...)` to all three refocus libraries.
3. **MIUI AI/beauty assets** — face rank models, gender/age models, watermark
   fonts, `.png` masks under `vendor/etc/camera/`.
4. **DSP skeletons** — `vendor/lib/rfsa/adsp/libarcsoft_dualcam_refocus_skel.so`
   and `libSNPE`-adjacent pieces.

`equuleus/extract-files.py` also patches
`vendor/lib/camera/components/com.qti.node.watermark.so` to add
`libpiex_shim.so`, and `vendor/lib/libmmcamera_faceproc.so` to clear
`__aeabi_memcpy` / `__aeabi_memset` / `__gnu_Unwind_Find_exidx` symbol versions.
Both shims (`libpiex_shim`) are provided by `hardware/lineage/compat`, which
PixelOS fifteen checks out (verified).

### 2.3 Camera app

PixelOS ships **Aperture** (LineageOS camera) via
`vendor/aosp/config/common_mobile_full.mk`, gated by `PRODUCT_NO_CAMERA`.
`equuleus/overlay-lineage/packages/apps/Aperture/…/config.xml` sets
`config_enableAuxCameras = true` and ignores aux camera IDs 3 and 4 — those IDs
exist in the target app (verified: `LineageOS/android_packages_apps_Aperture`
`app/src/main/res/values/config.xml` contains both resources).

So the *camera app* is Aperture, not MIUI Camera. The ArcSoft blobs above are
consumed by the **HAL** (post-processing nodes), not by Aperture. ArcSoft
features therefore still work only to the extent the HAL invokes them.

### 2.4 SELinux

`sepolicy/vendor/hal_camera_default.te` and `remosaic_daemon.te` exist. The
`remosaic_daemon` service is defined in `equuleus/init/init.target.rc` and runs
as `user camera / group camera`.

### 2.5 Verification status

| Claim | Status |
| --- | --- |
| Provider 2.4 declared, implemented, and available | **static: confirmed** |
| Aperture overlay targets exist | **static: confirmed** |
| ArcSoft symbol fixups scripted | **static: confirmed** (`extract-files.py`) |
| Blob set complete | **BLOCKED** — not extracted |
| Camera preview / photo / video / portrait on device | **NOT VERIFIED ON DEVICE** |

Known risk: this is the single most likely subsystem to differ between
LineageOS 22.2 (where it is known to work) and PixelOS fifteen, because the
media/display CAF branches and `frameworks_av` are PixelOS forks. Recorded as
B-08.

---

## 3. NFC — NXP PN553 (with eSE for secure element)

### 3.1 HAL type and registration

* Service module: `android.hardware.nfc-service.nxp`, defined at
  `snxxx/Android.bp:195` of `LineageOS/android_hardware_nxp_nfc@lineage-22.2`,
  installed at `/vendor/bin/hw/android.hardware.nfc-service.nxp`
  (`.rc` read). PixelOS fifteen checks out `platform/hardware/nxp/nfc` at
  `android-15.0.0_r32`, the same AOSP tree.
* `equuleus/device.mk` adds `android.hardware.nfc-service.nxp`,
  `com.android.nfc_extras`, `Tag`.
* Permission XMLs copied to `/vendor/etc/permissions/`:
  `android.hardware.nfc.xml`, `android.hardware.nfc.hce.xml`,
  `android.hardware.nfc.hcef.xml`, `com.android.nfc_extras.xml`,
  `com.nxp.mifare.xml`.
* Configs: `nfc/libnfc-nci.conf` → `/product/etc/`, `nfc/libnfc-nxp.conf` →
  `/vendor/etc/`.
* Secure element: `vendor.qti.secure_element@1.0-service` (+ `.rc`,
  `android.hardware.secure_element@1.0-impl.so`), declared in
  `equuleus/manifest.xml` with instances `SIM1` and `eSE1`.

### 3.2 Blobs

```
vendor/firmware/libpn553_rec.so
vendor/lib/libpn553_fw.so
vendor/bin/hw/vendor.qti.secure_element@1.0-service
vendor/etc/init/vendor.qti.secure_element@1.0-service.rc
vendor/lib64/hw/android.hardware.secure_element@1.0-impl.so
```

### 3.3 SELinux

**Gap found.** `sdm845-common/sepolicy/` contains no `hal_nfc*` file and no
`file_contexts` line for `android.hardware.nfc-service.nxp` or for
`vendor.qti.secure_element@1.0-service`. Checked all three sepolicy
directories (`vendor/`, `private/`, `public/`) and grep for `nfc`,
`secure_element`: no match. The NFC service therefore relies on generic
`hal_*_default` attribution from the AOSP/Lineage base policy. LineageOS ships
this device the same way, so it evidently works there, but it is an
**unverified assumption** for PixelOS. Tracked as B-11 (low severity,
build succeeds either way; at runtime a denial would show as NFC switching
itself off at boot).

### 3.4 Verification status

| Claim | Status |
| --- | --- |
| NFC service module resolvable and installed | **static: confirmed** |
| Permission XMLs and configs wired | **static: confirmed** |
| eSE service and HIDL impl present in blob list | **static: confirmed (list only)** |
| Device-specific NFC SELinux policy | **absent** — relies on base policy (B-11) |
| NFC read/write, HCE, transit cards on device | **NOT VERIFIED ON DEVICE** |

---

## 4. `hardware/xiaomi` fork choice — trade-off

Chosen: `PixelOS-AOSP/hardware_xiaomi@fifteen`
(`281f97dbac46b75eb7b6a680624e62e807ec0689`).

* **Gained:** Dolby `media.c2` + three `vendor.dolby*.dms*` VINTF entries,
  `vendor.xiaomi.hw.touchfeature` VINTF entry, `DSPVolumeSynchronizer`, `dolby`
  app, `aidl/ir` (IR blaster service — relevant: this phone has an IR blaster
  and `equuleus/init.target.rc` writes
  `/sys/class/leds/ir/max_brightness`).
* **Lost:** `aidl/touch/` (`HighTouchPollingRate`, `KeyDisabler`,
  `KeySwapper`) and `megvii/`.
* **Why that is acceptable:** grep across both device trees for `megvii`,
  `HighTouchPollingRate`, `KeyDisabler`, `KeySwapper`, `touchfeature` returns
  **no references**. The firmware's touch gestures are handled by the kernel
  (`CONFIG_TOUCHSCREEN_ST_FTS_V521`) and by PixelOS' own
  `packages/apps/TouchGestures` (checked out by `snippets/custom.xml`), not by
  the LineageOS touch AIDL HAL.
* **Residual risk:** if a future change wants `HighTouchPollingRate` (e.g. a
  120 Hz-style touch sampling toggle — not applicable here, the panel is 60 Hz),
  the LineageOS fork would need to be vendored under a different path. Do not
  map both repositories to `hardware/xiaomi`; `repo` would reject it.

---

## 5. Static hardware configuration (do not "fix" these numbers without device evidence)

All values are from `sdm845-common/BoardConfigCommon.mk` and `equuleus/`.

| Item | Value | Notes |
| --- | --- | --- |
| `AB_OTA_UPDATER` | `false` | non-A/B; recovery-based OTA |
| `BOARD_BOOT_HEADER_VERSION` | `1` | boot image v1 |
| `BOARD_KERNEL_IMAGE_NAME` | `Image.gz-dtb` | appended DTB |
| `BOARD_KERNEL_PAGESIZE` | `4096` | |
| `BOARD_KERNEL_BASE` | `0x00000000` | |
| `BOARD_BOOTIMAGE_PARTITION_SIZE` | 67,092,480 B | |
| `BOARD_RECOVERYIMAGE_PARTITION_SIZE` | 67,108,864 B | equuleus-specific |
| `BOARD_CACHEIMAGE_PARTITION_SIZE` | 268,435,456 B | |
| `BOARD_USERDATAIMAGE_PARTITION_SIZE` | 57,453,555,712 B | |
| `BOARD_SUPER_PARTITION_SIZE` | 5,167,382,528 B | 4.81 GiB |
| `BOARD_SUPER_PARTITION_BLOCK_DEVICES` | `system vendor cust` | |
| `BOARD_SUPER_PARTITION_{SYSTEM,VENDOR,CUST}_DEVICE_SIZE` | 3,221,225,472 / 1,073,741,824 / 872,415,232 | |
| `BOARD_SUPER_PARTITION_GROUPS` | `qti_dynamic_partitions` | |
| `BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST` | `odm product system system_ext vendor` | |
| `BOARD_QTI_DYNAMIC_PARTITIONS_SIZE` | 5,163,188,224 | super − 4 MiB |
| Filesystem types | ext4 for cache/odm/product/system/system_ext/vendor; ext4 **or** f2fs for userdata | `TARGET_USERIMAGES_USE_{EXT4,F2FS}` |
| `/data` | `latemount,wait,check,fileencryption=ice,quota,formattable` | `init/fstab.qcom` |
| `BOARD_AVB_ENABLE` | `true` | |
| AVB recovery | `SHA256_RSA4096`, key `external/avb/test/data/testkey_rsa4096.pem`, rollback index 1 @ location 1 | test key — see B-10 |
| `VENDOR_SECURITY_PATCH` | `2020-12-01` | vendor blobs are from MIUI 12.5, i.e. a 2020/2021 vendor patch level |
| `TARGET_OTA_ASSERT_DEVICE` | `equuleus` | |
| `board-info.txt` | `require board=sdm845|equuleus`, `require version-trustzone=XF.5.0.1-00161` | |
| Recovery fstab | `TARGET_RECOVERY_FSTAB := init/fstab.qcom` | shared fstab |

`BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --set_hashtree_disabled_flag` and
`--flags 2` are set, i.e. **vbmeta carries the "verification disabled" flag**.
That is normal for an unsigned custom ROM but must be understood before
flashing: the bootloader must already be unlocked, and `fastboot --disable-verity
--disable-verification` semantics apply.

---

---

## 7. IR face unlock (ParanoidSense) — static analysis, NOT VERIFIED

**Status: NOT VERIFIED.** Every statement below is derived from files in this
repository. Nothing has been run on a device; the camera id in particular has
not been confirmed by enumerating cameras on a booted build.

### 7.1 The hardware

Four camera sensor modules ship for this device
(`vendor/xiaomi/equuleus/proprietary/vendor/lib/camera/`):

| Module | Part | Role |
| --- | --- | --- |
| `com.qti.sensor.imx363.so` | Sony IMX363, 12 MP | primary rear RGB |
| `com.qti.sensor.s5k3m3.so` | Samsung S5K3M3, 12 MP | rear telephoto RGB |
| `com.qti.sensor.s5k3t1.so` | Samsung S5K3T1, 20 MP | front RGB (the selfie camera) |
| `com.qti.sensor.ov9282.so` | **OmniVision OV9282, 1 MP global-shutter monochrome** | **the IR camera** |

The OV9282 is the only monochrome part, and it is the sensor used for IR face
unlock on this platform. Its module data and tuning data are also present
(`com.qti.sensormodule.ov9282.bin`, `com.qti.tuned.ofilm_ov9282.bin`), so the
HAL can actually drive it.

**This is the reason an RGB camera cannot substitute.** The S5K3T1 front camera
needs visible light; in a dark room it returns noise. A face matcher fed that
stream either fails or, worse, is trivially defeated by a photo lit by the
screen. IR illumination is what makes dark-environment unlock work at all.

### 7.2 How ParanoidSense chooses a camera

`src/co/aospa/sense/camera/CameraUtil.kt` (upstream, unmodified):

```kotlin
fun getCameraId(context: Context?): Int {
    val cameraIdProp = SystemProperties.get("ro.face.sense_service.camera_id")
    if (cameraIdProp != null && cameraIdProp != "") {
        return cameraIdProp.toInt()          // <-- explicit id wins
    }
    ...
    cameraManager.cameraIdList?.forEach { cameraId ->
        val orientation = characteristics.get(CameraCharacteristics.LENS_FACING)
        if (orientation == CameraCharacteristics.LENS_FACING_FRONT) {
            return cameraId.toInt()          // <-- RGB FALLBACK
        }
    }
    return -1
}
```

The fallback is the trap: without the property, ParanoidSense opens the *front
RGB* camera. It would appear to work in daylight and fail in the dark — the
exact failure mode this project must not ship.

### 7.3 Why the property alone is not enough

`frameworks/base` `Camera.shouldExposeAuxCamera()`:

```java
String packageName = ActivityThread.currentOpPackageName();
List<String> packageList = Arrays.asList(
    SystemProperties.get("vendor.camera.aux.packagelist", packageName).split(","));
...
return packageList.contains(packageName) && !packageExcludelist.contains(packageName);
```

`Camera.getNumberOfCameras()` clamps to 2 unless this returns true, so any camera
with an id above 1 is invisible to a package that is not listed. The IR camera is
an auxiliary device, so **both** changes are required.

### 7.4 Camera id 5 — the evidence and its limits

| Evidence | Result |
| --- | --- |
| OV9282 is the IR part | confirmed from the shipped sensor modules |
| Aperture overlay already ignores aux ids | `3`, `4` (`device/xiaomi/equuleus/overlay-lineage/.../Aperture/config.xml`) |
| next free aux slot | 5 |
| established sdm845 adaptation for this device | sets `ro.face.sense_service.camera_id=5` |

**The value 5 is a provisional default, not a confirmed measurement.** It is set so
the pipeline has a concrete aux id to open; it has not been confirmed by
enumerating cameras on a booted build of this tree, and the factory MIUI
firmware does not declare it either (MIUI resolves the IR device inside its own
`com.xiaomi.biometric` service). Treat `camera_id=5` as **NOT VERIFIED ON DEVICE**.

**Limits, stated plainly.** The id was not obtained by enumerating cameras on
this build. The Aperture ignore-list is evidence about *which* ids are ordinary
auxiliary cameras, not a measurement of the IR device. If a booted build reports
a different id, changing the property is the whole fix — no code change.

To check on a device:
```bash
adb shell dumpsys media.camera | grep -E "Camera [0-9]+ information|Facing|static_camera_characteristics"
adb shell 'getprop ro.face.sense_service.camera_id'
adb shell 'getprop vendor.camera.aux.packagelist'
```

### 7.5 Vendor-side dependencies

| Item | State |
| --- | --- |
| `vendor/lib/hw/camera.qcom.so` (camera HAL) | present |
| OV9282 sensor module + tuning | present |
| `libcamxfdengine.so` / `libcamxfdalgov7.so` (face detect) | present |
| Megvii matching libraries (`libMegviiUnlock*`, `libmegface`, `libFaceDetectCA`) | shipped by ParanoidSense itself (prebuilt in the app repo) |
| `ParanoidSense` in `PRODUCT_PACKAGES` | yes, via `vendor/aosp/config/common.mk:95` — no extra packaging needed |
| SELinux policy for the IR camera | no device-specific rule added; the app inherits the standard `priv_app` camera access. **If the camera is denied at runtime this is the first place to look** |

### 7.6 What was changed

Device-side only, as two reviewable patches:

| Patch | Change |
| --- | --- |
| `0007-equuleus-ir-face-unlock-camera-id.patch` | `ro.face.sense_service.camera_id=5` in `system_ext.prop` |
| `0008-sdm845-common-ir-face-unlock-aux-camera.patch` | append `co.aospa.sense` to `vendor.camera.aux.packagelist` |

The packagelist is **appended**, not rewritten. A widely-copied adaptation of
this change replaces `org.lineageos.aperture.dev` with `co.aospa.sense`; doing
that would silently remove Aperture's aux-camera access, so all four original
entries are preserved.

No file under `packages/apps/ParanoidSense` is modified — verified by
`verify_ir_face_unlock.py`, which asserts the clone is clean.

---

## 6. Things that are *not* covered by this audit

* Any runtime behaviour: boot, touch, display calibration, modem, Wi-Fi, BT,
  audio, charging, thermal, battery life.
* IR face unlock (section 7): the configuration is in place and statically
  checked, but enrolment, daylight unlock, dark unlock and anti-spoofing are
  all unverified on hardware.
* Vendor blob completeness beyond the file lists (no blob was downloaded).
* TrustZone/firmware version compatibility (`version-trustzone=XF.5.0.1-00161`
  is only an assertion string; the phone's actual TZ version was not read —
  `fastboot getvar` on the real device would be required).
* Widevine / DRM level, SafetyNet/Play Integrity.
* Payment, transit-card and access-card flows (require real cards).

Every one of these is listed in `TEST_REPORT.md` under "not executed".
