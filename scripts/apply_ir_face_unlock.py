#!/usr/bin/env python3
"""apply_ir_face_unlock.py — add IR face unlock to the equuleus device tree.

Everything this touches is DEVICE-side:
  device/xiaomi/equuleus/system_ext.prop     (camera id for ParanoidSense)
  device/xiaomi/sdm845-common/vendor.prop    (aux camera allow-list)

No file under packages/apps/ParanoidSense is modified: the app already reads
`ro.face.sense_service.camera_id` and the framework already gates aux cameras on
`vendor.camera.aux.packagelist`. Both are configuration, so the port is purely
additive on the device side.

Why each change is needed (all verified against the sources we have):

  ro.face.sense_service.camera_id
      CameraUtil.getCameraId() reads it first; if empty it falls back to the
      FIRST camera whose LENS_FACING is FRONT (CameraUtil.kt lines 31-53). That
      fallback is the ordinary RGB selfie camera, which is exactly the "RGB
      pretending to be IR" failure this task forbids. So the property must be
      set explicitly.

  vendor.camera.aux.packagelist
      frameworks/base Camera.shouldExposeAuxCamera() hides every camera beyond
      index 1 unless the calling package is in this list. The IR camera is an
      aux device, so without `co.aospa.sense` here the app cannot open it even
      with the right id.

The packagelist is APPENDED to, not rewritten: the task requires keeping the
existing entries, and dropping org.lineageos.aperture.dev (as an upstream
reference commit does) would regress Aperture's aux access.
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT)

SYSTEM_EXT_PROP = os.path.join(ROOT, "device", "xiaomi", "equuleus",
                               "system_ext.prop")
VENDOR_PROP = os.path.join(ROOT, "device", "xiaomi", "sdm845-common",
                           "vendor.prop")

CAMERA_ID = "5"          # see DEVICE_AUDIT.md §7 for the evidence chain
SENSE_PACKAGE = "co.aospa.sense"


def patch_system_ext_prop() -> bool:
    with io.open(SYSTEM_EXT_PROP, encoding="utf-8") as fh:
        text = fh.read()
    if "ro.face.sense_service.camera_id" in text:
        print("  [skip] camera_id already present in system_ext.prop")
        return False
    block = (
        "\n"
        "# IR face unlock (ParanoidSense)\n"
        "# The app reads this first; without it, CameraUtil falls back to the\n"
        "# first LENS_FACING_FRONT camera, i.e. the RGB selfie sensor.\n"
        f"ro.face.sense_service.camera_id={CAMERA_ID}\n"
    )
    if not text.endswith("\n"):
        text += "\n"
    with io.open(SYSTEM_EXT_PROP, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + block)
    print(f"  [ok]   camera_id={CAMERA_ID} added to system_ext.prop")
    return True


def patch_vendor_prop() -> bool:
    with io.open(VENDOR_PROP, encoding="utf-8") as fh:
        lines = fh.readlines()
    key = "vendor.camera.aux.packagelist"
    changed = False
    for i, line in enumerate(lines):
        if not line.startswith(key + "="):
            continue
        current = line.rstrip("\n").split("=", 1)[1]
        entries = [e.strip() for e in current.split(",") if e.strip()]
        if SENSE_PACKAGE in entries:
            print("  [skip] co.aospa.sense already in aux packagelist")
            return False
        entries.append(SENSE_PACKAGE)
        lines[i] = f"{key}={','.join(entries)}\n"
        changed = True
        print(f"  [ok]   appended {SENSE_PACKAGE} to {key}")
        print(f"         now: {','.join(entries)}")
        break
    if not changed:
        raise SystemExit(f"FATAL: {key} not found in {VENDOR_PROP}")
    with io.open(VENDOR_PROP, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
    return True


def main() -> int:
    for path in (SYSTEM_EXT_PROP, VENDOR_PROP):
        if not os.path.isfile(path):
            print(f"FATAL: missing {path}", file=sys.stderr)
            return 2
    print("Applying IR face unlock device configuration")
    a = patch_system_ext_prop()
    b = patch_vendor_prop()
    print()
    if a or b:
        print("changes applied")
    else:
        print("nothing to do (already configured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
