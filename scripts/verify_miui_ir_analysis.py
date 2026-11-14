#!/usr/bin/env python3
"""verify_miui_ir_analysis.py — static acceptance for the MIUI IR comparison.

What this proves: the MIUI-derived claims in MIUI_IR_BLOB_INVENTORY.md,
MIUI_VS_LINEAGE_IR_DIFF.md and IR_FACE_UNLOCK_DEPENDENCIES.md are backed by
files that exist and bytes that were actually compared — not by prose.

What this does NOT prove: that IR face unlock works. Nothing here touches
hardware.

The MIUI dump is large and optional; when it is absent (e.g. in the review
archive, which does not ship 2 GB of MIUI firmware) the checks that need it are
reported as skipped rather than passed or failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The mutation sandbox copies only authored files; the MIUI dump (2 GB of firmware
# extraction) and the vendor blobs live in the real project. Honour the override.
ROOT = (os.environ.get("EQUULEUS_PROJECT_ROOT")
        or os.path.dirname(HERE))
ROOT = os.path.abspath(ROOT)
sys.path.insert(0, HERE)

MIUI_DUMP = os.path.join(ROOT, "work", "miui", "dump", "vendor_miui")
COMPARE_JSON = os.path.join(ROOT, "logs", "miui-ir-compare.json")

CHECKS = []
SKIPPED = []


class _Skip(Exception):
    """Raised when a check needs the MIUI dump, which may be absent."""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def check(name, fn):
    try:
        detail = fn()
        CHECKS.append((name, True, detail))
    except AssertionError as exc:
        CHECKS.append((name, False, str(exc)))
    except Exception as exc:                                     # noqa: BLE001
        CHECKS.append((name, False, "%s: %s" % (type(exc).__name__, exc)))


def skip(name, reason):
    SKIPPED.append((name, reason))


def main() -> int:
    def los(rel):
        for tree in ("equuleus", "sdm845-common"):
            p = os.path.join(ROOT, "vendor", "xiaomi", tree, "proprietary",
                             "vendor", rel)
            if os.path.isfile(p):
                return p
        return None

    def miui(rel):
        p = os.path.join(MIUI_DUMP, rel)
        return p if os.path.isfile(p) else None

    have_miui = os.path.isdir(MIUI_DUMP)

    # ------------------------------------------------------------------ docs
    def documents_exist():
        for name in ("MIUI_IR_BLOB_INVENTORY.md", "MIUI_VS_LINEAGE_IR_DIFF.md",
                     "IR_FACE_UNLOCK_DEPENDENCIES.md"):
            p = os.path.join(ROOT, name)
            assert os.path.isfile(p), "missing deliverable: " + name
            assert os.path.getsize(p) > 2000, "deliverable is a stub: " + name
        return "all three MIUI analysis documents present and substantive"

    # ------------------------------------------------- LineageOS side present
    def lineage_ir_stack_present():
        wanted = [
            "lib/camera/com.qti.sensor.ov9282.so",
            "lib/camera/com.qti.sensormodule.ov9282.bin",
            "lib/camera/com.qti.tuned.ofilm_ov9282.bin",
            "lib/hw/camera.qcom.so",
        ]
        for rel in wanted:
            assert los(rel), "LineageOS tree is missing " + rel
        return "OV9282 driver, module data, tuning and camera HAL all present"

    # ---------------------------------------- OV9282 driver is the IR part
    def ov9282_is_elf32_arm():
        p = los("lib/camera/com.qti.sensor.ov9282.so")
        with open(p, "rb") as fh:
            hdr = fh.read(20)
        assert hdr[:4] == b"\x7fELF", "ov9282 driver is not an ELF"
        assert hdr[4] == 1, "ov9282 driver is not ELF32 (got class %d)" % hdr[4]
        machine = int.from_bytes(hdr[18:20], "little")
        assert machine == 40, "ov9282 driver machine is %d, expected 40 (EM_ARM)" % machine
        return "OV9282 sensor driver is ELF32/EM_ARM as expected"

    # ------------------- live re-verification of the IDENTICAL claim -------
    def lineage_hashes_match_miui_live():
        """Recompute now. A cached JSON must not be the only evidence."""
        if not have_miui:
            raise _Skip("MIUI dump not present")
        pairs = [
            "lib/camera/com.qti.sensor.ov9282.so",
            "lib/camera/com.qti.sensormodule.ov9282.bin",
            "lib/camera/com.qti.tuned.ofilm_ov9282.bin",
            "lib/hw/camera.qcom.so",
            "etc/camera/camxoverridesettings.txt",
        ]
        for rel in pairs:
            m, l = miui(rel), los(rel)
            assert m and l, "one side missing for " + rel
            a, b = sha256(m), sha256(l)
            assert a == b, (
                "%s is no longer byte-identical: MIUI=%s LineageOS=%s. If the "
                "LineageOS copy was replaced with MIUI bytes, that is a "
                "regression (LineageOS applies fixups MIUI does not)."
                % (rel, a[:16], b[:16]))
        return ("%d IR-critical files re-hashed live and still IDENTICAL"
                % len(pairs))

    def lineage_blob_not_tampered():
        """The LineageOS faceproc must still carry its symbol-version fixup."""
        l = los("lib/libmmcamera_faceproc.so")
        assert l, "LineageOS libmmcamera_faceproc.so is missing"
        with open(l, "rb") as fh:
            data = fh.read()
        assert len(data) > 0x7FE5, "faceproc is truncated"
        got = [data[0x7FE0], data[0x7FE2], data[0x7FE4]]
        assert got == [1, 1, 1], (
            "LineageOS libmmcamera_faceproc.so no longer has the cleared symbol "
            "versions at 0x7FE0/0x7FE2/0x7FE4 (found %s, expected [1,1,1]). A "
            "raw MIUI copy has [3,3,3] - that means the fixup was reverted."
            % got)
        return "faceproc still carries the cleared symbol versions (fixup intact)"

    # ------------------------------- comparison JSON exists and is coherent
    def comparison_recorded():
        assert os.path.isfile(COMPARE_JSON), (
            "logs/miui-ir-compare.json missing; run scripts/compare_ir_blobs.py")
        with open(COMPARE_JSON, encoding="utf-8") as fh:
            d = json.load(fh)
        rows = d["rows"]
        assert len(rows) >= 15, "comparison has only %d rows" % len(rows)
        by = {r["rel"]: r for r in rows}
        # the three OV9282 components must be recorded as identical
        for rel in ("lib/camera/com.qti.sensor.ov9282.so",
                    "lib/camera/com.qti.sensormodule.ov9282.bin",
                    "lib/camera/com.qti.tuned.ofilm_ov9282.bin"):
            assert rel in by, "comparison does not cover " + rel
            v = by[rel]["verdict"]
            assert v == "IDENTICAL", "%s is %s, not IDENTICAL" % (rel, v)
        # the faceproc difference must be recorded, not hidden
        fp = by.get("lib/libmmcamera_faceproc.so", {}).get("verdict")
        assert fp == "DIFFERS", (
            "libmmcamera_faceproc.so should be recorded as DIFFERS (LineageOS "
            "applies a symbol-version fixup); got %s" % fp)
        return ("%d paths compared; OV9282 stack IDENTICAL; faceproc DIFFERS "
                "as documented" % len(rows))

    # ---------------------------------------- the 3-byte claim is accurate
    def faceproc_three_bytes():
        if not have_miui:
            raise _Skip("MIUI dump not present")
        m = miui("lib/libmmcamera_faceproc.so")
        l = los("lib/libmmcamera_faceproc.so")
        with open(m, "rb") as fh:
            a = fh.read()
        with open(l, "rb") as fh:
            b = fh.read()
        assert len(a) == len(b), "sizes differ: %d vs %d" % (len(a), len(b))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        assert len(diff) == 3, (
            "documented as 3 differing bytes, measured %d" % len(diff))
        assert diff == [0x7FE0, 0x7FE2, 0x7FE4], (
            "differing offsets are %s, documentation says 0x7FE0/0x7FE2/0x7FE4"
            % [hex(x) for x in diff])
        assert all(a[i] == 3 and b[i] == 1 for i in diff), (
            "byte values are not the documented 0x03 -> 0x01")
        return "faceproc differs by exactly 3 bytes at 0x7FE0/0x7FE2/0x7FE4 (0x03->0x01)"

    # -------------------------- the fixup that explains those bytes is real
    def fixup_declared_upstream():
        p = os.path.join(ROOT, "clones", "device-xiaomi-equuleus", "extract-files.py")
        if not os.path.isfile(p):
            raise _Skip("extract-files.py not present")
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        assert "libmmcamera_faceproc.so" in txt, (
            "extract-files.py does not mention libmmcamera_faceproc.so")
        for sym in ("__aeabi_memcpy", "__aeabi_memset", "__gnu_Unwind_Find_exidx"):
            assert sym in txt, "extract-files.py does not clear " + sym
        return "upstream declares clear_symbol_version for exactly 3 symbols"

    # ------------------------------- MIUI only declares aux via its own XML
    def miui_aux_mechanism_documented():
        if not have_miui:
            raise _Skip("MIUI dump not present")
        p = os.path.join(MIUI_DUMP, "etc", "device_features", "equuleus.xml")
        assert os.path.isfile(p), "MIUI device_features/equuleus.xml missing"
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        assert "camera_aux_package_list" in txt, (
            "MIUI does not use camera_aux_package_list as documented")
        for pkg in ("com.xiaomi.biometric", "com.miui.face",
                    "com.android.keyguard"):
            assert pkg in txt, "MIUI aux list does not contain " + pkg
        # and it must NOT be an AOSP property, which is what patch 0008 uses
        assert "vendor.camera.aux.packagelist" not in txt, (
            "MIUI unexpectedly uses the AOSP property; documentation is wrong")
        return "MIUI uses an XML aux list with the keyguard/biometric packages"

    # ------------------------------------- no MIUI blob was force-installed
    def no_miui_blob_overwrote_lineage():
        """0006-0008 must not carry binary content; they are prop/list edits."""
        patch_dir = os.path.join(ROOT, "patches")
        for name in sorted(os.listdir(patch_dir)):
            if not name.endswith(".patch"):
                continue
            with open(os.path.join(patch_dir, name), encoding="utf-8",
                      errors="replace") as fh:
                txt = fh.read()
            assert "GIT binary patch" not in txt, (
                "%s carries binary blob content; the task forbids overwriting "
                "the working LineageOS blobs" % name)
            # git binary literals look like "literal 1234" on its own line
            import re as _re
            assert not _re.search(r"^literal \d+$", txt, _re.M), (
                "%s appears to carry a git binary literal" % name)
        return "no patch installs MIUI binaries over the LineageOS blobs"

    # --------------------------------------------- honest NOT VERIFIED labels
    def not_verified_labels():
        deps = os.path.join(ROOT, "IR_FACE_UNLOCK_DEPENDENCIES.md")
        with open(deps, encoding="utf-8") as fh:
            txt = fh.read()
        assert "NOT VERIFIED" in txt, (
            "IR_FACE_UNLOCK_DEPENDENCIES.md does not mark the runtime status")
        assert "camera_id=5" in txt or "camera_id" in txt, (
            "the camera id caveat is missing")
        assert "remains NOT VERIFIED ON DEVICE" in txt or \
               "NOT VERIFIED ON DEVICE" in txt, (
            "the camera id is not marked NOT VERIFIED ON DEVICE")
        diff = os.path.join(ROOT, "MIUI_VS_LINEAGE_IR_DIFF.md")
        with open(diff, encoding="utf-8") as fh:
            dtxt = fh.read()
        assert "NOT VERIFIED" in dtxt, (
            "MIUI_VS_LINEAGE_IR_DIFF.md does not mark the runtime status")
        return "documents carry the NOT VERIFIED markings"

    # -------------- every size quoted in the inventory matches the real data
    def inventory_sizes_match_data():
        """Round 14: a table row once had the 64-bit size in the 32-bit row.

        Sizes in MIUI_IR_BLOB_INVENTORY.md must equal what compare_ir_blobs.py
        measured. This parses both and compares, so a typo cannot survive.
        """
        doc = os.path.join(ROOT, "MIUI_IR_BLOB_INVENTORY.md")
        assert os.path.isfile(doc), "MIUI_IR_BLOB_INVENTORY.md missing"
        with open(doc, encoding="utf-8") as fh:
            txt = fh.read()

        assert os.path.isfile(COMPARE_JSON), "comparison JSON missing"
        with open(COMPARE_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
        real = {}
        for row in data["rows"]:
            if row.get("miui"):
                real[row["rel"]] = row["miui"]["size"]

        import re as _re
        # rows look like: | `lib/libcamxfdengine.so` | 86,480 | ELF32 |
        checked = 0
        for m in _re.finditer(r"\|\s*`([^`]+)`\s*\|\s*([0-9,]+)\s*\|", txt):
            rel = m.group(1).strip()
            claimed = int(m.group(2).replace(",", ""))
            if rel not in real:
                continue
            assert claimed == real[rel], (
                "%s: document says %s bytes, measurement says %s"
                % (rel, claimed, real[rel]))
            checked += 1
        assert checked >= 6, (
            "only %d size rows cross-checked; the table format may have changed"
            % checked)
        return "%d documented sizes match the measured data exactly" % checked

    def illuminator_control_not_claimed():
        """Round 14: the illuminator control path must not be asserted.

        Static file inspection cannot determine how the face-unlock emitter is
        switched on, and conflating it with a consumer-IR blaster is wrong.
        Reject any wording that claims the mechanism is known.
        """
        inv = os.path.join(ROOT, "MIUI_IR_BLOB_INVENTORY.md")
        deps = os.path.join(ROOT, "IR_FACE_UNLOCK_DEPENDENCIES.md")
        for path in (inv, deps):
            with open(path, encoding="utf-8") as fh:
                txt = fh.read()
            assert "illuminator" in txt.lower(), (
                "%s does not discuss the illuminator" % os.path.basename(path))
            # the section must be marked unverified
            assert "NOT VERIFIED" in txt, (
                "%s lacks a NOT VERIFIED marking" % os.path.basename(path))
            # and must distinguish a blaster from the face-unlock emitter
            assert ("blaster" in txt.lower()
                    or "consumer ir" in txt.lower()
                    or "consumerir" in txt.lower()), (
                "%s does not distinguish an IR blaster from the face-unlock "
                "illuminator" % os.path.basename(path))
        # the old, over-confident phrasing must not come back
        with open(inv, encoding="utf-8") as fh:
            itxt = fh.read()
        for bad in ("there is no `/sys/class/leds/ir/*` style control",
                    "it comes on when the sensor is opened"):
            assert bad not in itxt, (
                "MIUI_IR_BLOB_INVENTORY.md re-asserts an unverified claim: %r" % bad)
        return ("illuminator control marked NOT VERIFIED; blaster vs illuminator "
                "distinguished")

    ordered = [
        ("three MIUI analysis documents delivered", documents_exist),
        ("LineageOS IR stack present", lineage_ir_stack_present),
        ("OV9282 driver is ELF32/ARM", ov9282_is_elf32_arm),
        ("IR blobs re-verified live, not from cache",
         lineage_hashes_match_miui_live),
        ("LineageOS faceproc fixup still intact", lineage_blob_not_tampered),
        ("comparison recorded and coherent", comparison_recorded),
        ("inventory sizes match measured data", inventory_sizes_match_data),
        ("faceproc differs by exactly 3 bytes", faceproc_three_bytes),
        ("upstream fixup explains those 3 bytes", fixup_declared_upstream),
        ("MIUI aux mechanism documented", miui_aux_mechanism_documented),
        ("no MIUI blob overwrites LineageOS", no_miui_blob_overwrote_lineage),
        ("NOT VERIFIED markings present", not_verified_labels),
        ("illuminator control not overclaimed", illuminator_control_not_claimed),
    ]

    class _SkipSentinel:
        pass

    print("MIUI IR analysis — static acceptance")
    print("=" * 66)

    failures = []
    for name, fn in ordered:
        try:
            detail = fn()
            CHECKS.append((name, True, detail))
        except _Skip as exc:
            SKIPPED.append((name, str(exc)))
        except AssertionError as exc:
            CHECKS.append((name, False, str(exc)))
            failures.append(name)
        except Exception as exc:                                 # noqa: BLE001
            CHECKS.append((name, False, "%s: %s" % (type(exc).__name__, exc)))
            failures.append(name)

    for name, ok, detail in CHECKS:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        if detail:
            for line in str(detail).splitlines():
                print("       " + line)
    for name, reason in SKIPPED:
        print("[SKIP] %s" % name)
        print("       " + reason)

    total = len(CHECKS)
    passed = total - len(failures)
    print("=" * 66)
    print("%d/%d checks passed, %d skipped" % (passed, total, len(SKIPPED)))
    print()
    print("STATIC ONLY. This proves the comparison was performed on real bytes.")
    print("It does NOT prove IR face unlock works, and camera_id=5 remains")
    print("NOT VERIFIED ON DEVICE.")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
