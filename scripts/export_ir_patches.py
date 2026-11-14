#!/usr/bin/env python3
"""export_ir_patches.py — emit the IR face unlock changes as reviewable patches.

The task requires an independent device-side patch rather than edits to upstream
PixelOS sources. Two repositories are touched, so two patches are produced, each
generated with git inside the real clone so the a/...b/ paths are correct by
construction and `git apply --check` proves they apply to the pinned commit.

Method: in each clone, write the new content over the tracked file, take
`git diff` (repo-relative), then restore the clone to HEAD. The clone is never
left dirty.
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PATCHES = os.path.join(ROOT, "patches")

CLONE_DIR = {
    "equuleus": "device-xiaomi-equuleus",
    "sdm845-common": "device-xiaomi-sdm845-common",
}

SPECS = [
    {
        "repo": "equuleus",
        "path": "system_ext.prop",
        "file": "0007-equuleus-ir-face-unlock-camera-id.patch",
        "subject": "equuleus: set the IR camera id for ParanoidSense face unlock",
        "body": """ParanoidSense resolves its camera in CameraUtil.getCameraId():

    val cameraIdProp = SystemProperties.get("ro.face.sense_service.camera_id")
    if (cameraIdProp != null && cameraIdProp != "") return cameraIdProp.toInt()
    ... forEach cameraId -> if LENS_FACING == LENS_FACING_FRONT -> return it

When the property is absent the fallback picks the first front-facing camera,
which on this device is the ordinary RGB selfie sensor (S5K3T1). RGB face
matching works in daylight and fails in the dark, which is exactly the "RGB
pretending to be IR" failure this port must avoid. Setting it is mandatory.

camera id 5 is the infrared camera. Evidence (all from files in this repo; see
DEVICE_AUDIT.md section 7):

  * four camera sensor modules ship for this device: imx363 (primary), s5k3m3
    (telephoto), s5k3t1 (front RGB) and ov9282. The OmniVision OV9282 is a 1MP
    global-shutter MONOCHROME part, i.e. the IR camera.
  * device/xiaomi/equuleus/overlay-lineage/.../Aperture/config.xml already lists
    aux camera ids 3 and 4 as ignorable, so the IR device enumerates above them
    and the next free aux slot is 5.
  * the established Xiaomi sdm845 custom-ROM adaptation for this exact device
    sets ro.face.sense_service.camera_id=5.

NOT VERIFIED on hardware: the id has not been confirmed by enumerating cameras
on a booted build of this tree. If the device differs, change this property;
no code change is required.
""",
    },
    {
        "repo": "sdm845-common",
        "path": "vendor.prop",
        "file": "0008-sdm845-common-ir-face-unlock-aux-camera.patch",
        "subject": "sdm845-common: allow ParanoidSense to open the aux IR camera",
        "body": """frameworks/base Camera.shouldExposeAuxCamera() collapses enumeration to two
cameras for any package not listed in vendor.camera.aux.packagelist:

    String packageName = ActivityThread.currentOpPackageName();
    List<String> packageList = Arrays.asList(
        SystemProperties.get("vendor.camera.aux.packagelist", packageName).split(","));
    ...
    return packageList.contains(packageName) && !packageExcludelist.contains(packageName);

The IR camera is an auxiliary device, so a correct camera id alone is not
enough: without co.aospa.sense in this list the app still cannot open it.

This APPENDS to the existing list. A widely-copied adaptation of this change
replaces org.lineageos.aperture.dev with co.aospa.sense; doing that here would
silently remove Aperture's auxiliary-camera access, so every existing entry is
preserved verbatim and the new package is appended.
""",
    },
]


def run(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s in %s: %s" % (" ".join(args), cwd, r.stderr.strip()))
    return r


def main() -> int:
    os.makedirs(PATCHES, exist_ok=True)
    rc = 0

    for spec in SPECS:
        repo, rel = spec["repo"], spec["path"]
        clone = os.path.join(ROOT, "clones", CLONE_DIR[repo])
        current_file = os.path.join(ROOT, "device", "xiaomi", repo, rel)

        with io.open(current_file, encoding="utf-8") as fh:
            new_text = fh.read()

        dirty = run(clone, "status", "--porcelain").stdout.strip()
        if dirty:
            print("FATAL: clone %s is dirty:\n%s" % (CLONE_DIR[repo], dirty),
                  file=sys.stderr)
            return 1

        target = os.path.join(clone, rel)
        with io.open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        diff = run(clone, "diff", "--no-color", "--", rel).stdout
        run(clone, "checkout", "--", rel)

        if not diff.strip():
            print("  [skip] %s/%s: identical to upstream" % (repo, rel))
            continue

        digest = hashlib.sha1(diff.encode("utf-8")).hexdigest()
        header = (
            "From %s Mon Sep 17 00:00:00 2001\n" % digest
            + "From: equuleus port <port@example.invalid>\n"
            + "Date: Wed, 12 Nov 2026 00:00:00 +0800\n"
            + "Subject: [PATCH] %s\n" % spec["subject"]
            + "\n" + spec["body"] + "---\n"
        )
        dest = os.path.join(PATCHES, spec["file"])
        with io.open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(header + diff)
        print("  [ok]   %s" % spec["file"])

    print()
    print("verifying against pristine clones:")
    for spec in SPECS:
        clone = os.path.join(ROOT, "clones", CLONE_DIR[spec["repo"]])
        patch = os.path.join(PATCHES, spec["file"])
        if not os.path.isfile(patch):
            continue
        r = run(clone, "apply", "--check", patch, check=False)
        if r.returncode == 0:
            print("  [OK]   %s -> %s" % (spec["file"], spec["repo"]))
        else:
            print("  [FAIL] %s: %s" % (spec["file"], r.stderr.strip()))
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
