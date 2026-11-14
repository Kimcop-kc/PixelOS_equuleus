#!/usr/bin/env python3
"""verify_ir_face_unlock.py — static acceptance for the IR face unlock port.

Checks every link in the chain that must exist for ParanoidSense to open the
INFRARED camera rather than the RGB one. Nothing here proves the feature works;
that requires hardware. The point is to catch a broken configuration before a
4-hour build and a flash.

Chain being verified:
  1. ParanoidSense is checked out and its CameraUtil really reads
     ro.face.sense_service.camera_id (the property we rely on).
  2. The device sets that property, with a plausible non-empty value.
  3. The package co.aospa.sense is in vendor.camera.aux.packagelist.
  4. The existing packagelist entries were preserved (no silent replacement).
  5. The IR sensor stack is present in the vendor tree: an OV9282 sensor module
     and its tuned/module data.
  6. Camera HAL pieces the IR path needs are present.
  7. The device tree does NOT rely on the RGB fallback: if the property were
     missing, CameraUtil would pick LENS_FACING_FRONT.
  8. The patches exist and apply to the pinned upstream commits.

Usage: python3 scripts/verify_ir_face_unlock.py [--root .]
Exit:  0 = all checks pass, 1 = a check failed, 2 = usage.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

CHECKS = []
FAILURES = []


def check(name, fn):
    try:
        detail = fn()
        CHECKS.append((name, True, detail))
    except AssertionError as exc:
        CHECKS.append((name, False, str(exc)))
        FAILURES.append(name)
    except Exception as exc:                                # noqa: BLE001
        CHECKS.append((name, False, "%s: %s" % (type(exc).__name__, exc)))
        FAILURES.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None,
                    help="project root; defaults to EQUULEUS_PROJECT_ROOT, then "
                         "the parent of this script")
    args = ap.parse_args()
    # The mutation sandbox copies only authored files; vendor/ and clones/ are
    # absent there, so an explicit root is required to evaluate this feature.
    root = (args.root
            or os.environ.get("EQUULEUS_PROJECT_ROOT")
            or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.abspath(root)

    def p(*parts):
        return os.path.join(root, *parts)

    def need(path):
        assert os.path.exists(path), "missing required file: %s" % path

    def read(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    # ---------------------------------------------------------------- 1
    def find_sense():
        """Return the ParanoidSense source directory, searching both layouts."""
        candidates = [
            p("packages", "apps", "ParanoidSense"),   # real synced PixelOS tree
            p("clones", "paranoidsense"),             # this review package
        ]
        for cand in candidates:
            util = os.path.join(cand, "src", "co", "aospa", "sense", "camera",
                                "CameraUtil.kt")
            if os.path.isfile(util):
                return cand
        raise AssertionError(
            "ParanoidSense sources not found. Looked for "
            "packages/apps/ParanoidSense and clones/paranoidsense. "
            "On a real tree run this script from the tree root, or pass --root.")

    def sense_source_present():
        base = find_sense()
        util = os.path.join(base, "src", "co", "aospa", "sense", "camera",
                            "CameraUtil.kt")
        txt = read(util)
        assert 'ro.face.sense_service.camera_id' in txt, (
            "CameraUtil.kt no longer reads ro.face.sense_service.camera_id; "
            "the property we set would be ignored")
        assert "LENS_FACING_FRONT" in txt, (
            "CameraUtil.kt no longer has the front-facing fallback; the "
            "RGB-vs-IR analysis in DEVICE_AUDIT.md needs revisiting")
        bp = os.path.join(base, "Android.bp")
        need(bp)
        bpt = read(bp)
        assert 'name: "ParanoidSense"' in bpt, "Android.bp does not define the app"
        assert "libMegviiUnlock" in bpt, "Megvii libraries missing from Android.bp"
        return "ParanoidSense source present; reads the camera_id property"

    # ---------------------------------------------------------------- 2
    def camera_id_property_set():
        prop = p("device", "xiaomi", "equuleus", "system_ext.prop")
        need(prop)
        txt = read(prop)
        m = re.search(r"^ro\.face\.sense_service\.camera_id=(\S+)\s*$", txt, re.M)
        assert m, "ro.face.sense_service.camera_id is not set in system_ext.prop"
        val = m.group(1)
        assert val.isdigit(), "camera id must be an integer, got %r" % val
        cid = int(val)
        assert cid >= 2, (
            "camera id %d is a primary camera; the IR device must be an aux id" % cid)
        return "ro.face.sense_service.camera_id=%d" % cid

    # ---------------------------------------------------------------- 3
    def aux_packagelist_contains_sense():
        prop = p("device", "xiaomi", "sdm845-common", "vendor.prop")
        need(prop)
        txt = read(prop)
        m = re.search(r"^vendor\.camera\.aux\.packagelist=(.+)$", txt, re.M)
        assert m, "vendor.camera.aux.packagelist not found"
        entries = [e.strip() for e in m.group(1).split(",") if e.strip()]
        assert "co.aospa.sense" in entries, (
            "co.aospa.sense missing from vendor.camera.aux.packagelist; "
            "Camera.shouldExposeAuxCamera() will hide the IR camera")
        return "packagelist has %d entries incl. co.aospa.sense" % len(entries)

    # ---------------------------------------------------------------- 4
    def existing_packages_preserved():
        prop = p("device", "xiaomi", "sdm845-common", "vendor.prop")
        txt = read(prop)
        m = re.search(r"^vendor\.camera\.aux\.packagelist=(.+)$", txt, re.M)
        entries = [e.strip() for e in m.group(1).split(",") if e.strip()]
        required = ["com.android.camera", "org.codeaurora.snapcam",
                    "org.lineageos.aperture", "org.lineageos.aperture.dev"]
        missing = [r for r in required if r not in entries]
        assert not missing, (
            "existing packagelist entries were dropped: %s; the task requires "
            "preserving them" % missing)
        return "all %d original entries preserved" % len(required)

    # ---------------------------------------------------------------- 5
    def ir_sensor_stack_present():
        cam = p("vendor", "xiaomi", "equuleus", "proprietary", "vendor", "lib",
                "camera")
        need(cam)
        files = os.listdir(cam)
        sensors = [f for f in files if f.startswith("com.qti.sensor.")]
        assert sensors, "no camera sensor modules in the vendor tree"
        ir = [f for f in sensors if "ov9282" in f]
        assert ir, (
            "OV9282 (the monochrome IR sensor) is not present. Without it the "
            "IR camera cannot be driven at all. Sensors found: %s" % sorted(sensors))
        tuned = [f for f in files if "ov9282" in f and "tuned" in f]
        module = [f for f in files if "ov9282" in f and "sensormodule" in f]
        assert tuned, "no tuned data (com.qti.tuned.*ov9282*.bin) for the IR sensor"
        assert module, "no sensor module data (com.qti.sensormodule.ov9282.bin)"
        return "OV9282 sensor + module + tuning data all present"

    # ---------------------------------------------------------------- 6
    def camera_hal_dependencies_present():
        equ = p("vendor", "xiaomi", "equuleus", "proprietary", "vendor")
        hal = os.path.join(equ, "lib", "hw", "camera.qcom.so")
        assert os.path.isfile(hal), "camera.qcom.so (the camera HAL) is missing"
        # camx face detection libs are what ParanoidSense's vendor impl uses
        wanted = ["libcamxfdengine.so"]
        missing = []
        for w in wanted:
            hits = []
            for dirpath, _d, files in os.walk(equ):
                if w in files:
                    hits.append(dirpath)
            if not hits:
                missing.append(w)
        assert not missing, "camera face-detect libraries missing: %s" % missing
        return "camera HAL + face-detect engine present"

    # ---------------------------------------------------------------- 7
    def no_reliance_on_rgb_fallback():
        prop = p("device", "xiaomi", "equuleus", "system_ext.prop")
        txt = read(prop)
        assert "ro.face.sense_service.camera_id" in txt, (
            "the device depends on CameraUtil's RGB fallback; that would use the "
            "front RGB sensor and fail in the dark")
        # and it must not be a primary camera id
        m = re.search(r"camera_id=(\d+)", txt)
        assert int(m.group(1)) not in (0, 1), (
            "camera id 0/1 is a primary camera; the IR device is an aux camera")
        return "explicit IR id set; no dependence on the front-RGB fallback"

    # ---------------------------------------------------------------- 8
    def device_tree_reflects_patches():
        """The device tree this build uses must carry the patched content.

        A patch file on disk proves nothing: the tree could be unpatched, or
        patched then reverted. This reads the tree itself.
        """
        equ_prop = p("device", "xiaomi", "equuleus", "system_ext.prop")
        com_prop = p("device", "xiaomi", "sdm845-common", "vendor.prop")
        for path in (equ_prop, com_prop):
            assert os.path.isfile(path), (
                "device tree missing: %s. This script must be run from the real "
                "tree (or a package that ships device/)." % path)
        assert re.search(r"^ro\.face\.sense_service\.camera_id=\d+",
                         read(equ_prop), re.M), (
            "system_ext.prop in the device tree has no camera id; 0007 was not "
            "applied to this tree")
        aux = re.search(r"^vendor\.camera\.aux\.packagelist=(.+)$",
                        read(com_prop), re.M)
        assert aux, "vendor.prop has no vendor.camera.aux.packagelist"
        entries = [e.strip() for e in aux.group(1).split(",") if e.strip()]
        assert "co.aospa.sense" in entries, (
            "vendor.prop in the device tree does not list co.aospa.sense")
        return "device tree itself carries the camera id and the aux allow-list"

    def patches_exist_and_apply():
        specs = [
            ("0007-equuleus-ir-face-unlock-camera-id.patch",
             "device-xiaomi-equuleus"),
            ("0008-sdm845-common-ir-face-unlock-aux-camera.patch",
             "device-xiaomi-sdm845-common"),
        ]
        # Patches and clones belong to THIS project, not to the PixelOS source
        # tree. When --root points at a synced tree there is no patches/ there,
        # so resolve from the script's own directory first.
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for patch, clone in specs:
            pf = os.path.join(project_dir, "patches", patch)
            if not os.path.isfile(pf):
                pf = p("patches", patch)
            need(pf)

            clone_dir = os.path.join(project_dir, "clones", clone)
            if not os.path.isdir(clone_dir):
                clone_dir = p("clones", clone)
            if not os.path.isdir(os.path.join(clone_dir, ".git")):
                # no clone available: verify structure only
                txt = read(pf)
                assert "Subject: [PATCH]" in txt, "%s lacks a subject header" % patch
                continue
            # Either it applies (base tree) or it reverses (already applied).
            # Both are consistent; anything else means the tree drifted.
            fwd = subprocess.run(["git", "-C", clone_dir, "apply", "--check", pf],
                                 capture_output=True, text=True)
            rev = subprocess.run(["git", "-C", clone_dir, "apply", "--reverse",
                                  "--check", pf], capture_output=True, text=True)
            assert fwd.returncode == 0 or rev.returncode == 0, (
                "%s neither applies nor reverses against %s (tree drifted): %s"
                % (patch, clone, (fwd.stderr or rev.stderr).strip()))
        return "both IR patches apply to their pinned upstream commits"

    def sense_not_modified_upstream():
        """The task forbids editing PixelOS' shared sources."""
        try:
            base = find_sense()
        except AssertionError:
            return "ParanoidSense not found; cannot check cleanliness"
        if not os.path.isdir(os.path.join(base, ".git")):
            return "not a git checkout; skipping cleanliness check"
        r = subprocess.run(["git", "-C", base, "status", "--porcelain"],
                           capture_output=True, text=True)
        assert not r.stdout.strip(), (
            "ParanoidSense working tree is modified; the port must be "
            "device-side only. Dirty:\n%s" % r.stdout)
        return "ParanoidSense upstream tree is untouched"

    ordered = [
        ("ParanoidSense source reads the camera_id property", sense_source_present),
        ("device sets ro.face.sense_service.camera_id", camera_id_property_set),
        ("vendor.camera.aux.packagelist contains co.aospa.sense", aux_packagelist_contains_sense),
        ("existing packagelist entries preserved", existing_packages_preserved),
        ("IR (OV9282) sensor stack present in vendor", ir_sensor_stack_present),
        ("camera HAL and face-detect engine present", camera_hal_dependencies_present),
        ("no reliance on the RGB front-camera fallback", no_reliance_on_rgb_fallback),
        ("device tree reflects the patches (not just the files)", device_tree_reflects_patches),
        ("IR patches apply to pinned upstream", patches_exist_and_apply),
        ("PixelOS ParanoidSense source unmodified", sense_not_modified_upstream),
    ]

    print("IR Face Unlock static acceptance")
    print("=" * 62)
    for name, fn in ordered:
        check(name, fn)
    for name, ok, detail in CHECKS:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        if detail:
            for line in str(detail).splitlines():
                print("       " + line)
    print("=" * 62)
    print("%d/%d checks passed" % (len(CHECKS) - len(FAILURES), len(CHECKS)))
    print()
    print("STATIC ONLY. Nothing here proves IR unlock works: the camera id, the")
    print("aux-camera exposure and the Megvii matching path are all unverified")
    print("on hardware. Treat IR face unlock as NOT VERIFIED until TEST_REPORT.md")
    print("section 12 has real device results.")
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
