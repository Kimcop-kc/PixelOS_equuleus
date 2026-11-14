# IR_FACE_UNLOCK_DEPENDENCIES — what IR unlock needs, and what is verified

Scope: the dependency chain for infrared face unlock on `equuleus` under PixelOS
fifteen with ParanoidSense. Everything below is derived from files in this
project or from the md5-verified MIUI firmware.

**Status of every runtime claim in this document: NOT VERIFIED.**
No ROM has been built, nothing has been flashed, and no IR frame has ever been
captured on a device by this project.

---

## 1. The chain, end to end

```
ParanoidSense (co.aospa.sense)
   │  asks CameraUtil.getCameraId()
   │     ├─ ro.face.sense_service.camera_id   ← device tree must set this
   │     └─ fallback: first LENS_FACING_FRONT  ← the RGB selfie camera (WRONG)
   ▼
framework Camera.shouldExposeAuxCamera()
   │  requires the caller in vendor.camera.aux.packagelist   ← device tree must list it
   ▼
camera.qcom.so  (32-bit CAMX HAL, from the vendor blob set)
   │  loads sensor modules from /vendor/lib/camera/
   ▼
com.qti.sensor.ov9282.so   ← the IR sensor driver (ELF32, ARM)
   │  + com.qti.sensormodule.ov9282.bin   (slot/module descriptor)
   │  + com.qti.tuned.ofilm_ov9282.bin    (tuning data)
   ▼
OV9282 hardware ──── IR illuminator (driven by the sensor module, not by a sysfs node)
   │
   ▼
Megvii matching libraries (shipped inside the ParanoidSense app)
   libMegviiUnlock.so, libMegviiUnlock-jni-1.2.so, libmegface.so, libFaceDetectCA.so
   ▼
BiometricPrompt / Keyguard integration (framework)
```

Each link is checked statically by `scripts/verify_ir_face_unlock.py` (10/10 pass
in this tree). A static pass means the *configuration* is self-consistent. It is
not evidence that a single frame of IR ever reached the matcher.

## 2. Reuse verdict — can ParanoidSense use the existing LineageOS OV9282 driver?

**Yes, and no MIUI component needs to be added.** This is not an inference from
filenames; it is a byte-level result:

| File | MIUI vs LineageOS |
| --- | --- |
| `lib/camera/com.qti.sensor.ov9282.so` | **byte-identical** (28,288 B) |
| `lib/camera/com.qti.sensormodule.ov9282.bin` | **byte-identical** (39,101 B) |
| `lib/camera/com.qti.tuned.ofilm_ov9282.bin` | **byte-identical** (379,825 B) |
| `lib/hw/camera.qcom.so` | **byte-identical** (3,275,248 B) |
| `etc/camera/camxoverridesettings.txt` | **byte-identical** (856 B) |

Architecture, `DT_SONAME` and `DT_NEEDED` also match exactly:

```
com.qti.sensor.ov9282.so : ELF32, machine=40 (EM_ARM)
                           SONAME=com.qti.sensor.ov9282.so
                           NEEDED=[libc++.so, libcutils.so, liblog.so,
                                   libc.so, libm.so, libdl.so]
camera.qcom.so           : ELF32, machine=40 (EM_ARM)
                           SONAME=camera.qcom.so
```

The explanation is mundane and worth stating: LineageOS extracted these blobs
**from this very firmware**. There is no second version of the OV9282 driver in
circulation for this device.

## 3. Why no blob patch was emitted

The task asks for a patch only if an MIUI component is genuinely required. It
isn't, and the two candidates that looked like gaps are explained:

| Candidate | Verdict |
| --- | --- |
| `lib64/libmmcamera_faceproc.so` | **not needed.** The camera HAL is 32-bit, so the loader resolves `lib/libmmcamera_faceproc.so`. The 64-bit copy is unreferenced; adding it would be dead weight. |
| `bin/hw/android.hardware.camera.provider@2.4-service` | **not needed.** PixelOS builds this from `hardware/interfaces` (`sdm845.mk:105`). Shipping MIUI's prebuilt binary would shadow the source-built one. |
| `lib/libmmcamera_faceproc.so` (3 bytes differ) | **must not be replaced.** The difference is LineageOS's own `clear_symbol_version` fixup. Reverting to MIUI's bytes would reintroduce the exact symbol-version defect that fixup exists to fix. |

Emitting a patch that overwrote any of these with MIUI bytes would be an active
regression, not an improvement. The device-side patches that *are* needed
(0007, 0008) were already written in the previous round and are unrelated to
blob content.

## 4. What MIUI does, and why it cannot be transplanted

MIUI's IR face unlock is not a reusable component. Its call chain is:

```
com.android.keyguard / com.android.systemui
        │
        ├── vendor.camera aux access granted because those packages appear in
        │   MIUI's own camera_aux_package_list
        │
        ▼
com.miui.face  (MIUI app)
        │
        ▼
com.xiaomi.biometric  (MIUI vendor service)
        │
        ▼
libstfaceunlockoclqcom.so / libFaceGrade.so / libscveFaceRecognition.so
```

MIUI's allow-list, from `etc/device_features/equuleus.xml`:

```xml
<string-array name="camera_aux_package_list">
    <item>org.codeaurora.snapcam</item>
    <item>com.android.camera</item>
    <item>com.miui.cit</item>
    <item>com.qualcomm.qti.qmmi</item>
    <item>com.android.keyguard</item>
    <item>com.android.systemui</item>
    <item>com.xiaomi.biometric</item>
    <item>com.xiaomi.biometric.haldemo</item>
    <item>com.phonetest.application</item>
    <item>com.phonetest.application.test</item>
    <item>com.miui.face</item>
    <item>com.miui.cameratest</item>
</string-array>
```

Two things follow, and they matter:

1. **The mechanism is the same idea, implemented differently.** MIUI uses an XML
   string-array consumed by MIUI's framework; AOSP/PixelOS uses the
   `vendor.camera.aux.packagelist` system property consumed by
   `Camera.shouldExposeAuxCamera()`. That is why the PixelOS adaptation is a
   property (patch 0008), not an XML edit.
2. **The MIUI services are not portable.** `com.xiaomi.biometric` and
   `com.miui.face` are MIUI framework components. They do not exist in PixelOS,
   are not open source, and their authentication protocol is undocumented. Per the
   task constraints they are **not** declared PixelOS-compatible, and no SELinux
   policy is loosened to make them load. ParanoidSense replaces them wholesale.

## 5. The camera id question — unchanged, still NOT VERIFIED

MIUI's `device_features/equuleus.xml` (87 feature entries) contains **no**
explicit IR camera id. MIUI reaches the IR camera through its own service, which
resolves the device internally. So the factory firmware does **not** corroborate
`camera_id=5`.

That leaves the evidence for 5 exactly where the previous round left it:

| Evidence | Strength |
| --- | --- |
| OV9282 is the only monochrome/IR sensor module shipped | strong (identifies the part) |
| Aperture overlay ignores aux ids 3 and 4 | moderate (bounds the enumeration) |
| Established sdm845 custom-ROM adaptation for this device uses 5 | moderate (works elsewhere) |
| **Direct enumeration on a booted build of this tree** | **absent** |

**`ro.face.sense_service.camera_id=5` remains NOT VERIFIED ON DEVICE.** This
round's MIUI analysis did not change that, and it must not be reported as
confirmed. If a booted build reports a different index, the fix is that one
property — no code or blob change.

How to settle it on hardware:

```bash
adb shell 'getprop ro.face.sense_service.camera_id'
adb shell dumpsys media.camera | grep -E "Camera [0-9]+ information|Facing|RESOLUTION"
'''

## 6. IR illuminator control — NOT VERIFIED

**The mechanism by which the face-unlock illuminator is switched on is unknown.**
Static inspection of the vendor partition did not determine it, and no claim is
made here.

### 6.1 Two different "IR" things, not to be confused

| | IR blaster (consumer IR) | IR illuminator (face unlock) |
| --- | --- | --- |
| Purpose | TV / appliance remote control | lights the face so the monochrome sensor can image it |
| Android interface | `ConsumerIr` HAL | none standard |
| On equuleus | **absent** — no consumer-ir reference in the device tree, no consumerir HAL in vendor | hardware present (the OV9282 is the IR camera); control path **unknown** |

The absence of a blaster is established and irrelevant here. The illuminator's
control path is simply not established.

### 6.2 What was searched, and what that means

| Search | Scope | Result |
| --- | --- | --- |
| `leds`/`ir_led`/`ir_illum`/`illuminat` | MIUI `vendor/etc` | no match |
| `flood`/`duty`/`pwm` | MIUI `vendor/etc/camera` | no match |
| consumer-ir HAL | MIUI vendor dump | not present |

No match in the vendor partition is **not** proof that no control exists. A
kernel driver or a device-tree `leds`/GPIO node would live outside the file sets
examined (kernel image, DTB), and an implicit "emitter is on whenever the IR
stream is open" design would need no userspace knob at all.

### 6.3 What remains unresolved

Whether the illuminator is (a) implicit in opening the OV9282 stream, (b) driven
by a kernel/DTB node, or (c) driven through a CAMX vendor tag. **NOT VERIFIED.**

If IR frames come out dark, the cause could be any of: the wrong camera id (the
RGB sensor has no emitter at all), the sensor not opened in the IR configuration,
an undriven emitter, or a control path outside the vendor partition. No cause is
ranked as more likely than another.

### 6.4 How to settle it on a device

```bash
ls -l /sys/class/leds/
cat /sys/kernel/debug/gpio | grep -i ir
dmesg | grep -iE "ir_|ov9282|flood"
```

and, decisively: **block the illuminator with opaque tape and retry unlock in
complete darkness.** If unlock still succeeds, the pipeline is not using IR —
that is `IR_FACE_UNLOCK_DEPENDENCIES.md` §8 test 5, and it is the only reliable
discriminator regardless of what the control mechanism turns out to be.

## 7. SELinux

No device-specific SELinux rule was added for IR unlock, and none is bypassed.
ParanoidSense is a platform-signed `priv_app` and inherits the standard camera
access that `priv_app` already has.

If the camera fails to open at runtime with an `avc: denied` for a camera-related
class, that is the first thing to inspect — but adding a permissive rule to work
around it would violate the task constraints, and would also be the wrong fix for
what is more likely a camera-id or aux-list problem.

## 8. Acceptance plan — device side, NOT RUN

Nothing below has been executed by this project. No build exists to flash.

**Prerequisites:** a built ROM, unlocked bootloader, a dark room, a printed photo
of your own face.

| # | Test | Command / method | Pass criterion |
| --- | --- | --- | --- |
| 1 | Camera id present | `adb shell 'getprop ro.face.sense_service.camera_id'` | prints a value; non-empty |
| 2 | Id is the IR device | `adb shell dumpsys media.camera \| grep -A2 "Camera [0-9]"`; compare the entry for that id | the id is **not** the `LENS_FACING_FRONT` RGB camera |
| 3 | Aux access not clamped | logcat during enrol, grep `CameraAccessException`, `IllegalArgument`, `getNumberOfCameras` | no access exception |
| 4 | **IR image is really IR** | in a pitch-dark room, enrol and observe the preview (or `adb shell dumpsys media.camera` while enrolled) | a visible image in **0 lux** — RGB cannot do this; this is the discriminator |
| 5 | **Emitter fires** | cover the IR illuminator with tape, retry in the dark | unlock **fails**. If it still succeeds with the emitter blocked, the pipeline is not using IR |
| 6 | Enrolment | Settings → Security → Face unlock, normal light | completes without Megvii errors in logcat |
| 7 | Daylight unlock | 10 attempts, ~300 lux | ≥ 9/10 |
| 8 | Dim light | 10 attempts, ~5 lux | ≥ 8/10 |
| 9 | **Complete darkness** | 10 attempts, 0 lux, screen off | ≥ 8/10 |
| 10 | Reboot persistence | `adb reboot`, unlock without re-enrolling, 5 attempts | ≥ 4/5, enrolment survives |
| 11 | Wrong person | another person's face, 10 attempts | 0/10 unlock |
| 12 | **Photo spoof** | printed photo + phone-screen photo of the enrolled face | both rejected. `config_face_intro_show_require_eyes` is `false` in the app overlay, so eyes-closed images may be accepted — if a photo unlocks, that is a **security defect**, record it as such |
| 13 | Failure and retry | eyes closed, face partly covered, > 1 m distance | fails without unlocking; offers retry; no spurious lockout |

**Tests 4 and 5 together are what prove the feature is genuinely infrared.**
Without them, "face unlock works" is an unsupported claim — a daylight-only pass
is precisely the signature of the RGB fallback.

## 9. Recording results

For every run record: `ro.build.fingerprint`, the camera id in effect, lux
estimate, attempt counts, and the relevant logcat excerpt. Until that exists,
IR face unlock stays **NOT VERIFIED**, and `camera_id=5` stays **NOT VERIFIED ON
DEVICE**.

## 10. Summary of what this round established

| Question | Answer |
| --- | --- |
| Is the firmware authentic? | **Yes** — `vendor.img` md5 matches Xiaomi's own manifest |
| Does MIUI have an OV9282 IR driver? | Yes, 3 files |
| Does LineageOS already have it? | **Yes — byte-identical, same arch/SONAME/deps** |
| Can ParanoidSense reuse it? | **Yes, directly** |
| Must any MIUI component be added? | **No** |
| Is the camera id confirmed by MIUI? | **No** — MIUI does not declare it; id 5 stays NOT VERIFIED ON DEVICE |
| Does IR unlock work? | **UNKNOWN — NOT VERIFIED.** No ROM built, no device test run |
